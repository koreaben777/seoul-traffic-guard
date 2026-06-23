# Security Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining security risks for the PlayMCP contest deployment: request limits, user identity boundary hardening, excessive API-call protection, and OAuth token-at-rest encryption.

**Architecture:** Keep the current single-file MCP server shape. Add small stdlib guards first: request body cap, batch cap, per-user in-memory rate limits, short TTL cache, and duplicate-send guard. Use `cryptography.fernet.Fernet` only for OAuth token encryption because Python stdlib does not provide safe authenticated symmetric encryption.

**Tech Stack:** Python 3.13 stdlib, `http.server`, SQLite, `cryptography` for token encryption only, existing assert-based `test_server.py`.

---

## Scope Check

This plan intentionally does not implement a new login system. If PlayMCP in KC does not provide a trusted user identity header or an authenticated ingress path, the server cannot fully prove user identity from normal MCP calls. This plan hardens the current boundary and makes the limitation explicit.

Included:

- STG-SEC-001 user identity header hardening
- STG-SEC-002 OAuth token-at-rest encryption plan
- STG-SEC-004 request body and JSON-RPC batch caps
- API excessive request protection
- documentation and deployment checklist updates

Already handled before this plan:

- STG-SEC-003 raw `str(exc)` exposure was fixed and tested.

## File Structure

- Modify: `server.py`
  - Add small security constants and helper functions near current globals.
  - Keep rate limiter/cache state in process memory.
  - Harden `user_id_from_headers`, `do_POST`, `call_tool`, `fetch_accinfo`, and `send_kakao_self_message`.
  - Add token encryption helpers around only `save_oauth_tokens` and `load_state`.

- Modify: `test_server.py`
  - Add assert-based tests for request size cap, batch cap, required user header, header allowlist behavior, rate limiting, cache, duplicate send guard, and token encryption.
  - Keep current no-framework execution style: `python test_server.py`.

- Modify: `.env.example`
  - Add `REQUIRE_USER_ID_HEADER`, `MAX_REQUEST_BYTES`, `MAX_BATCH_REQUESTS`, `TOKEN_ENCRYPTION_KEY`.
  - Add rate limit knobs only if the implementation exposes them. Default plan keeps rate limits as constants, so no rate env vars are added.

- Create: `requirements.txt`
  - Add only `cryptography` for Fernet token encryption.

- Modify: `Dockerfile`
  - Install `requirements.txt` before copying `server.py`.

- Modify: `README.md`
  - Document the new env vars and the accepted limitation around PlayMCP user identity.

- Modify: `docs/playmcp_deployment_checklist.md`
  - Add final deployment checks for user header, request caps, token encryption key, and rate limiting.

- Modify: `docs/security_risk_review.md`
  - Mark STG-SEC-004 and excessive API-call protection as implemented after tasks pass.
  - Mark STG-SEC-001 as hardened but still dependent on PlayMCP ingress guarantee.
  - Mark STG-SEC-002 as implemented if the encryption task is approved and completed.

---

### Task 1: Add MCP Request Size And Batch Caps

**Files:**

- Modify: `server.py`
- Modify: `test_server.py`

- [ ] **Step 1: Write failing HTTP transport tests**

Add these tests inside `test_http_transport_edges()` after the successful `initialize` assertion:

```python
        huge_body = b"{" + (b'"x":' + b'"a"' * 90000) + b"}"
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", "/mcp", body=huge_body, headers={"Accept": "application/json"})
        res = conn.getresponse()
        oversized_body = res.read()
        conn.close()
        assert res.status == 413
        assert b"request too large" in oversized_body

        batch = [
            {"jsonrpc": "2.0", "id": i, "method": "ping", "params": {}}
            for i in range(21)
        ]
        status, headers, body = request(
            "POST",
            "/mcp",
            batch,
            {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        )
        assert status == 400
        assert json.loads(body)["error"]["message"] == "MCP batch request is too large."
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python test_server.py
```

Expected: FAIL because oversized requests currently return `400` parse errors or read the whole body, and oversized batch requests return `200`.

- [ ] **Step 3: Add the minimal implementation**

Add constants near `GENERIC_REQUEST_ERROR`:

```python
MAX_REQUEST_BYTES = int(os.environ.get("MAX_REQUEST_BYTES", "262144"))
MAX_BATCH_REQUESTS = int(os.environ.get("MAX_BATCH_REQUESTS", "20"))
BATCH_TOO_LARGE_ERROR = "MCP batch request is too large."
```

Modify `Handler.do_POST()` before `payload = json.loads(...)`:

```python
            length = int(self.headers.get("content-length", "0"))
            if length > MAX_REQUEST_BYTES:
                self.send_json({"error": "request too large"}, status=413)
                return
            payload = json.loads(self.rfile.read(length) or b"{}")
            if isinstance(payload, list) and len(payload) > MAX_BATCH_REQUESTS:
                self.send_json({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": BATCH_TOO_LARGE_ERROR}}, status=400)
                return
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
python test_server.py
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add server.py test_server.py
git commit -m "fix: cap mcp request size"
```

---

### Task 2: Harden User Identity Header Handling

**Files:**

- Modify: `server.py`
- Modify: `test_server.py`
- Modify: `.env.example`
- Modify: `docs/playmcp_deployment_checklist.md`

- [ ] **Step 1: Write failing identity boundary tests**

Add imports from `server` in `test_server.py`:

```python
    user_id_from_headers,
    UserIdentityRequired,
```

Add tests after `test_user_id_from_headers()`:

```python
def test_user_id_header_can_be_required():
    with patch("server.env_value", side_effect=lambda name: "true" if name == "REQUIRE_USER_ID_HEADER" else ""):
        try:
            user_id_from_headers({})
        except UserIdentityRequired:
            pass
        else:
            raise AssertionError("expected missing user id header to be rejected")


def test_configured_user_id_header_disables_default_spoof_headers():
    def fake_env(name):
        if name == "PLAYMCP_USER_ID_HEADERS":
            return "x-confirmed-playmcp-user"
        if name == "REQUIRE_USER_ID_HEADER":
            return "true"
        return ""

    with patch("server.env_value", side_effect=fake_env):
        assert user_id_from_headers({"x-confirmed-playmcp-user": "user-a"}) == "user-a"
        try:
            user_id_from_headers({"x-playmcp-user-id": "spoofed"})
        except UserIdentityRequired:
            pass
        else:
            raise AssertionError("expected default spoof header to be ignored when a configured header exists")
```

Add both tests to the `if __name__ == "__main__":` list.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python test_server.py
```

Expected: FAIL because `UserIdentityRequired` does not exist and default headers are still accepted even when a configured header exists.

- [ ] **Step 3: Add minimal user identity helpers**

Add near globals in `server.py`:

```python
class UserIdentityRequired(ValueError):
    pass


def env_bool(name: str) -> bool:
    return env_value(name).strip().lower() in {"1", "true", "yes", "on"}
```

Replace `user_id_from_headers()` with:

```python
def user_id_from_headers(headers: Any) -> str:
    configured = tuple(name.strip().lower() for name in env_value("PLAYMCP_USER_ID_HEADERS").split(",") if name.strip())
    header_names = configured or USER_ID_HEADERS
    for name in header_names:
        value = headers.get(name)
        if value:
            return normalize_user_id(value)
    if env_bool("REQUIRE_USER_ID_HEADER"):
        raise UserIdentityRequired("user identity header is required")
    return DEFAULT_USER_ID
```

Modify `do_POST()` around `user_id = user_id_from_headers(self.headers)`:

```python
            try:
                user_id = user_id_from_headers(self.headers)
            except UserIdentityRequired:
                self.send_json({"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": "User identity is required."}}, status=401)
                return
```

Keep `GET /auth/kakao/start` fallback unchanged for local OAuth start unless later testing shows PlayMCP also starts OAuth through headers.

- [ ] **Step 4: Update `.env.example`**

Add:

```env
REQUIRE_USER_ID_HEADER=
MAX_REQUEST_BYTES=262144
MAX_BATCH_REQUESTS=20
```

- [ ] **Step 5: Update deployment checklist**

Add to `docs/playmcp_deployment_checklist.md` under PlayMCP In KC:

```markdown
- [ ] Confirm the real PlayMCP user identity header name.
- [ ] Set `PLAYMCP_USER_ID_HEADERS` to only that confirmed header.
- [ ] Set `REQUIRE_USER_ID_HEADER=true` after PlayMCP header behavior is confirmed.
- [ ] Verify a direct request with a fake default `X-PlayMCP-User-Id` does not access another user's state when a confirmed custom header is configured.
```

- [ ] **Step 6: Run tests to verify pass**

Run:

```bash
python test_server.py
```

Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add server.py test_server.py .env.example docs/playmcp_deployment_checklist.md
git commit -m "fix: harden user identity header handling"
```

---

### Task 3: Add Per-User Tool Rate Limit

**Files:**

- Modify: `server.py`
- Modify: `test_server.py`

- [ ] **Step 1: Write failing rate-limit test**

Add import from `server`:

```python
    RATE_LIMITS,
```

Add test after `test_rpc_flow()`:

```python
def test_tool_rate_limit_blocks_excessive_calls():
    RATE_LIMITS.clear()
    ALERT_AREAS.clear()
    areas("heavy-user")["work"] = {
        "label": "work",
        "address": "x",
        "radius_m": 100,
        "tm_x": 198000.0,
        "tm_y": 451000.0,
    }

    with patch("server.fetch_accinfo", return_value=[]):
        results = [
            rpc("tools/call", {"name": "check_traffic_issues", "arguments": {"label": "work"}}, request_id=i, user_id="heavy-user")
            for i in range(11)
        ]

    assert "등록 지역 주변" in results[0]["result"]["content"][0]["text"]
    assert "요청이 많습니다" in results[-1]["result"]["content"][0]["text"]
```

Add the test to the `__main__` list.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python test_server.py
```

Expected: FAIL because no rate limiter exists.

- [ ] **Step 3: Add minimal in-memory limiter**

Add near global state:

```python
RATE_LIMITS: dict[tuple[str, str], list[float]] = {}
RATE_LIMIT_WINDOW_SECONDS = 60
SEND_SELF_ALERT_RATE_LIMIT = 6
OTHER_TOOL_CALL_RATE_LIMIT = 60
OTHER_TOOL_RATE_KEY = "__other_tools__"
RATE_LIMIT_MESSAGE = "요청이 많습니다. 잠시 후 다시 시도해 주세요."
```

Add helper:

```python
def rate_limited(user_id: str, tool_name: str, now: float | None = None) -> bool:
    now = now or time_module.time()
    bucket = "send_self_alert" if tool_name == "send_self_alert" else OTHER_TOOL_RATE_KEY
    limit = SEND_SELF_ALERT_RATE_LIMIT if tool_name == "send_self_alert" else OTHER_TOOL_CALL_RATE_LIMIT
    key = (user_id, bucket)
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    recent = [stamp for stamp in RATE_LIMITS.get(key, []) if stamp > cutoff]
    if len(recent) >= limit:
        RATE_LIMITS[key] = recent
        return True
    recent.append(now)
    RATE_LIMITS[key] = recent
    return False
```

Modify `call_tool()` at the start:

```python
    if rate_limited(user_id, name):
        return text_result(RATE_LIMIT_MESSAGE)
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
python test_server.py
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add server.py test_server.py
git commit -m "fix: rate limit mcp tool calls"
```

---

### Task 4: Cache Seoul Traffic API Briefly

**Files:**

- Modify: `server.py`
- Modify: `test_server.py`

- [ ] **Step 1: Write failing cache test**

Add import from `server`:

```python
    ACCINFO_CACHE,
    fetch_accinfo_cached,
```

Add test near existing `fetch_accinfo` tests:

```python
def test_fetch_accinfo_cached_reuses_recent_result():
    ACCINFO_CACHE.clear()

    with patch("server.fetch_accinfo", return_value=[{"acc_info": "cached"}]) as fetch:
        first = fetch_accinfo_cached()
        second = fetch_accinfo_cached()

    assert first == [{"acc_info": "cached"}]
    assert second == [{"acc_info": "cached"}]
    assert fetch.call_count == 1
```

Add the test to the `__main__` list.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python test_server.py
```

Expected: FAIL because `ACCINFO_CACHE` and `fetch_accinfo_cached` do not exist.

- [ ] **Step 3: Add minimal TTL cache**

Add global state:

```python
ACCINFO_CACHE: dict[str, Any] = {}
ACCINFO_CACHE_TTL_SECONDS = 30
```

Add helper after `fetch_accinfo()`:

```python
def fetch_accinfo_cached(limit: int = 1000) -> list[dict[str, Any]]:
    now = time_module.time()
    cached_at = float(ACCINFO_CACHE.get("cached_at") or 0)
    if ACCINFO_CACHE.get("limit") == limit and now - cached_at <= ACCINFO_CACHE_TTL_SECONDS:
        return list(ACCINFO_CACHE["rows"])
    rows = fetch_accinfo(limit)
    ACCINFO_CACHE.update({"limit": limit, "cached_at": now, "rows": rows})
    return rows
```

Change `fetch_accinfo_retry()`:

```python
            return fetch_accinfo_cached(limit), attempt
```

Keep `run_due_alerts()` as-is if it calls `fetch_accinfo()` directly, or change it to `fetch_accinfo_cached()` only if duplicate scheduled checks become expensive in tests. The first implementation should avoid changing scheduler semantics.

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
python test_server.py
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add server.py test_server.py
git commit -m "fix: cache traffic api briefly"
```

---

### Task 5: Add Duplicate KakaoTalk Send Guard

**Files:**

- Modify: `server.py`
- Modify: `test_server.py`

- [ ] **Step 1: Write failing duplicate-send test**

Add import from `server`:

```python
    SENT_MESSAGE_GUARD,
```

Add test after `test_send_self_alert_posts_kakao_message_when_connected()`:

```python
def test_send_self_alert_blocks_duplicate_message_for_one_minute():
    OAUTH_TOKENS.clear()
    SENT_MESSAGE_GUARD.clear()
    tokens()["access_token"] = "access-1"

    with patch("server.post_kakao_api", return_value={"result_code": 0}) as post:
        first = rpc(
            "tools/call",
            {"name": "send_self_alert", "arguments": {"message": "중복 테스트", "dry_run": False}},
        )["result"]["content"][0]["text"]
        second = rpc(
            "tools/call",
            {"name": "send_self_alert", "arguments": {"message": "중복 테스트", "dry_run": False}},
        )["result"]["content"][0]["text"]

    assert "Sent alert" in first
    assert "이미 같은 알림" in second
    assert post.call_count == 1
```

Add the test to the `__main__` list.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python test_server.py
```

Expected: FAIL because duplicate sends are not blocked.

- [ ] **Step 3: Add minimal duplicate-send guard**

Add globals:

```python
SENT_MESSAGE_GUARD: dict[tuple[str, str], float] = {}
DUPLICATE_SEND_WINDOW_SECONDS = 60
DUPLICATE_SEND_MESSAGE = "이미 같은 알림을 방금 보냈습니다. 잠시 후 다시 시도해 주세요."
```

Add helper:

```python
def duplicate_send_blocked(user_id: str, message: str, now: float | None = None) -> bool:
    now = now or time_module.time()
    digest = sha256(message.encode("utf-8")).hexdigest()
    key = (user_id, digest)
    last_sent = SENT_MESSAGE_GUARD.get(key)
    if last_sent and now - last_sent <= DUPLICATE_SEND_WINDOW_SECONDS:
        return True
    SENT_MESSAGE_GUARD[key] = now
    return False
```

Modify `send_self_alert` inside `call_tool()` before `send_kakao_self_message(...)`:

```python
        if duplicate_send_blocked(user_id, message):
            return text_result(DUPLICATE_SEND_MESSAGE)
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
python test_server.py
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add server.py test_server.py
git commit -m "fix: prevent duplicate kakao sends"
```

---

### Task 6: Encrypt OAuth Tokens At Rest

**Files:**

- Create: `requirements.txt`
- Modify: `Dockerfile`
- Modify: `server.py`
- Modify: `test_server.py`
- Modify: `.env.example`

- [ ] **Step 1: Add dependency declaration**

Create `requirements.txt`:

```text
cryptography>=42.0.0,<51.0.0
```

Modify `Dockerfile`:

```dockerfile
FROM python:3.13-slim

ENV HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py ./

EXPOSE 8000
CMD ["python", "server.py"]
```

- [ ] **Step 2: Write failing encryption tests**

Add import:

```python
    db_connect,
```

Add tests after `test_sqlite_persists_alert_area_schedule_and_tokens()`:

```python
def test_oauth_tokens_are_encrypted_when_key_is_configured():
    from cryptography.fernet import Fernet

    OAUTH_TOKENS.clear()
    key = Fernet.generate_key().decode()

    with patch("server.env_value", side_effect=lambda name: key if name == "TOKEN_ENCRYPTION_KEY" else os.environ.get(name, "")):
        save_oauth_tokens({"access_token": "access-secret", "refresh_token": "refresh-secret"}, "encrypted-user")
        with db_connect() as conn:
            stored = conn.execute("SELECT data FROM oauth_tokens WHERE user_id = ?", ("encrypted-user",)).fetchone()[0]

        assert stored.startswith("fernet:")
        assert "access-secret" not in stored
        assert "refresh-secret" not in stored

        OAUTH_TOKENS.clear()
        load_state()
        assert tokens("encrypted-user")["access_token"] == "access-secret"
        assert tokens("encrypted-user")["refresh_token"] == "refresh-secret"


def test_legacy_plaintext_oauth_tokens_still_load_without_key():
    OAUTH_TOKENS.clear()
    with db_connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO oauth_tokens(user_id, data) VALUES (?, ?)",
            ("legacy-user", json.dumps({"access_token": "legacy-access"}, ensure_ascii=False)),
        )

    load_state()
    assert tokens("legacy-user")["access_token"] == "legacy-access"
```

Add both tests to the `__main__` list.

- [ ] **Step 3: Run test to verify it fails**

Run:

```bash
python test_server.py
```

Expected: FAIL because token rows are still saved as plaintext JSON.

- [ ] **Step 4: Add token encryption helpers**

No new stdlib import is needed for this step. Keep the `cryptography` import lazy inside `token_cipher()` so local development without token encryption can still start before dependencies are installed.

Add helpers near DB functions:

```python
def token_cipher():
    key = env_value("TOKEN_ENCRYPTION_KEY")
    if not key:
        return None
    from cryptography.fernet import Fernet

    return Fernet(key.encode("utf-8"))


def encode_oauth_data(tokens: dict[str, Any]) -> str:
    raw = json.dumps(tokens, ensure_ascii=False)
    cipher = token_cipher()
    if not cipher:
        return raw
    return "fernet:" + cipher.encrypt(raw.encode("utf-8")).decode("utf-8")


def decode_oauth_data(data: str) -> dict[str, Any]:
    if not data.startswith("fernet:"):
        return json.loads(data)
    cipher = token_cipher()
    if not cipher:
        raise ValueError("TOKEN_ENCRYPTION_KEY is required to read OAuth tokens")
    return json.loads(cipher.decrypt(data.removeprefix("fernet:").encode("utf-8")).decode("utf-8"))
```

Modify `save_oauth_tokens()`:

```python
            (user_id, encode_oauth_data(tokens)),
```

Modify `load_state()` OAuth loop:

```python
        for user_id, data in conn.execute("SELECT user_id, data FROM oauth_tokens"):
            OAUTH_TOKENS[user_id] = decode_oauth_data(data)
```

- [ ] **Step 5: Update `.env.example`**

Add:

```env
TOKEN_ENCRYPTION_KEY=
```

- [ ] **Step 6: Run tests to verify pass**

Run:

```bash
python test_server.py
```

Expected: `ok`

- [ ] **Step 7: Verify Docker build still works**

Run:

```bash
docker build -t seoul-traffic-guard:local .
```

Expected: image builds successfully.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt Dockerfile server.py test_server.py .env.example
git commit -m "fix: encrypt oauth tokens at rest"
```

---

### Task 7: Update Docs And Security Review Status

**Files:**

- Modify: `README.md`
- Modify: `docs/playmcp_deployment_checklist.md`
- Modify: `docs/security_risk_review.md`
- Modify: `docs/agentic_player_10_submission_plan.md`

- [ ] **Step 1: Update README environment section**

Add these variables to the README environment block:

```env
REQUIRE_USER_ID_HEADER=true
MAX_REQUEST_BYTES=262144
MAX_BATCH_REQUESTS=20
TOKEN_ENCRYPTION_KEY=
```

Add this note:

```markdown
For public PlayMCP deployment, set `PLAYMCP_USER_ID_HEADERS` to the confirmed platform user identity header and set `REQUIRE_USER_ID_HEADER=true`. If PlayMCP cannot guarantee that the header is injected by a trusted ingress and cannot be spoofed by direct callers, this server cannot fully guarantee cross-user isolation without an additional ingress secret or signed user identity.
```

- [ ] **Step 2: Update deployment checklist**

Add under Review Request:

```markdown
- [ ] Oversized MCP request bodies return 413.
- [ ] JSON-RPC batches above `MAX_BATCH_REQUESTS` are rejected.
- [ ] Per-user/tool rate limiting returns a short retry-later message.
- [ ] Duplicate KakaoTalk sends within 60 seconds are blocked.
- [ ] `TOKEN_ENCRYPTION_KEY` is set in deployed environments that persist OAuth tokens.
- [ ] SQLite token rows do not contain raw `access_token` or `refresh_token` values when `TOKEN_ENCRYPTION_KEY` is set.
```

- [ ] **Step 3: Update security review statuses**

Edit `docs/security_risk_review.md`:

```markdown
- STG-SEC-001: Hardened with required user header option; still depends on PlayMCP ingress guarantee.
- STG-SEC-002: Implemented when `TOKEN_ENCRYPTION_KEY` is configured; local plaintext fallback remains for development.
- STG-SEC-004: Implemented with request body and batch caps.
- API 과다 요청 방어: Implemented with an in-memory per-user `send_self_alert` rate limit, an in-memory per-user shared rate limit for all other tools, short Seoul API TTL cache, and duplicate-send guard.
```

- [ ] **Step 4: Run documentation sanity check**

Run:

```bash
rg -n "TBD|TODO|fill in|implement later" README.md docs/security_risk_review.md docs/playmcp_deployment_checklist.md docs/agentic_player_10_submission_plan.md
```

Expected: no output for this plan's new content.

- [ ] **Step 5: Run full local verification**

Run:

```bash
python test_server.py
git diff --check
```

Expected:

- `python test_server.py` prints `ok`
- `git diff --check` prints nothing

- [ ] **Step 6: Commit**

```bash
git add README.md docs/playmcp_deployment_checklist.md docs/security_risk_review.md docs/agentic_player_10_submission_plan.md
git commit -m "docs: update security deployment guidance"
```

---

## Approval Gates

Before implementation, confirm these choices:

1. Token encryption dependency: approve adding `cryptography>=42.0.0,<51.0.0`.
2. Body cap: approve default `MAX_REQUEST_BYTES=262144`.
3. Batch cap: approve default `MAX_BATCH_REQUESTS=20`.
4. Rate limits: use the approved per-minute defaults:
   - `send_self_alert`: 6 calls per user
   - all other tools combined: 60 calls per user
5. User identity: approve the limited fix of requiring a confirmed user ID header, while accepting that true anti-spoofing still depends on PlayMCP/ingress behavior.

## Self-Review

Spec coverage:

- STG-SEC-001 covered by Task 2 and Task 7.
- STG-SEC-002 covered by Task 6 and Task 7.
- STG-SEC-004 covered by Task 1 and Task 7.
- API excessive requests covered by Tasks 3, 4, 5, and Task 7.
- STG-SEC-003 remains covered by the previous fix and tests.

Placeholder scan:

- The plan uses concrete files, code snippets, commands, and expected outputs instead of unresolved placeholder language.

Type consistency:

- New global names used in tests are defined in the matching implementation tasks: `RATE_LIMITS`, `ACCINFO_CACHE`, `SENT_MESSAGE_GUARD`, `UserIdentityRequired`.
- The planned test runner stays consistent with the existing project pattern: `python test_server.py`.
