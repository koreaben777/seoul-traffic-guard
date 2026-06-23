# Seoul Traffic Guard

Seoul Traffic Guard is a Remote MCP server for checking Seoul traffic disruptions near user-defined areas and sending optional KakaoTalk self-alerts.

Korean service name: `서울 교통 이슈 알리미`

## What it does

- Registers named alert areas from Seoul addresses.
- Registers named point-radius alert areas and selectable public-transit routes.
- Geocodes addresses with Kakao Local API.
- Finds public-transit route candidates with ODsay.
- Checks Seoul Open Data `AccInfo` traffic incidents.
- Matches incidents against registered area radius.
- Sends alerts to the user's own KakaoTalk chat after OAuth consent.
- Stores scheduled alerts and runs them while the server is alive.

## User flow in ChatGPT for Kakao

Target flow after PlayMCP registration:

```text
KakaoTalk
-> ChatGPT for Kakao
-> user asks in natural language
-> ChatGPT for Kakao calls this MCP server's tools through PlayMCP
-> server stores areas, checks traffic issues, or stores schedules
-> server sends a KakaoTalk self-alert only after user OAuth consent
```

Example user prompts:

```text
출근길을 서울시청 반경 1km로 등록해줘.
출근길 주변에 지금 통제나 사고 있어?
이 내용을 나에게 카카오톡으로 보내줘.
평일 아침 7시에 출근길 교통 이슈를 자동으로 알려줘.
예약 알림 목록 보여줘.
```

## Tools

| Tool | Purpose |
| --- | --- |
| `set_alert_area` | Register or update a point-radius alert area from a Seoul address or place keyword. |
| `list_alert_areas` | List the current user's alert areas. |
| `delete_alert_area` | Delete an alert area by label. |
| `find_transit_route_options` | Find selectable public-transit route candidates with ODsay. |
| `set_selected_transit_route_alert_area` | Register the route candidate selected by the user. |
| `check_traffic_issues` | Check Seoul traffic issues near the current user's registered areas. |
| `send_self_alert` | Send a prepared alert to the current user's own KakaoTalk chat. |
| `set_scheduled_alert` | Create or update a scheduled traffic alert. |
| `list_scheduled_alerts` | List scheduled traffic alerts. |
| `delete_scheduled_alert` | Delete a scheduled traffic alert. |

Tool and server names intentionally do not contain `kakao`.

## Required environment variables

```env
KAKAO_REST_API_KEY=
KAKAO_CLIENT_SECRET=
KAKAO_REDIRECT_URI=http://localhost:8000/auth/kakao/callback
SEOUL_OPENAPI_KEY=
ODSAY_API_KEY=
PLAYMCP_DB_PATH=./playmcp.db
PLAYMCP_USER_ID_HEADERS=
REQUIRE_USER_ID_HEADER=
MAX_REQUEST_BYTES=262144
MAX_BATCH_REQUESTS=20
TOKEN_ENCRYPTION_KEY=
ALLOWED_ORIGINS=
TASK_RUN_SECRET=
```

Notes:

- `KAKAO_CLIENT_SECRET` is required only when the Kakao app client secret is enabled.
- `ODSAY_API_KEY` is required for public-transit route candidate lookup.
- `PLAYMCP_USER_ID_HEADERS` is optional and comma-separated. In public deployment, set it to the confirmed PlayMCP user id header only.
- `REQUIRE_USER_ID_HEADER=true` rejects MCP requests without the confirmed user id header. Keep it empty only for local single-user development.
- `MAX_REQUEST_BYTES` and `MAX_BATCH_REQUESTS` cap MCP request size and batch fan-out.
- `TOKEN_ENCRYPTION_KEY` enables Fernet encryption for newly saved OAuth tokens. Generate it with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- `ALLOWED_ORIGINS` is optional locally and comma-separated. Set it for confirmed deployed PlayMCP/Kakao Tools browser origins.
- `TASK_RUN_SECRET` is optional. Set it only when an external scheduler will call `/tasks/run-due-alerts`.
- Do not commit `.env`, API keys, OAuth tokens, or `playmcp.db`.

## Local run

```bash
python3 server.py
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Readiness check:

```bash
curl http://127.0.0.1:8000/ready
python3 scripts/check_readiness.py
```

`/ready` returns only boolean configuration checks. It does not return API keys, client secrets, OAuth tokens, or database contents.

MCP endpoint:

```text
http://127.0.0.1:8000/mcp
```

Local MCP smoke check:

```bash
python3 scripts/smoke_mcp_http.py
```

Local beta flow:

```bash
python3 scripts/local_beta_flow.py
```

This registers a sample Seoul City Hall area for user id `beta-local`, checks nearby traffic issues, and previews an alert message. It does not send KakaoTalk messages.

Local preflight after the server is running:

```bash
python3 scripts/preflight.py
```

OAuth start URL:

```text
http://localhost:8000/auth/kakao/start
```

## Docker run

Build:

```bash
docker build -t seoul-traffic-guard:local .
```

Run:

```bash
mkdir -p .data
docker run --rm \
  --env-file .env \
  -e HOST=0.0.0.0 \
  -e PLAYMCP_DB_PATH=/data/playmcp.db \
  -p 8000:8000 \
  -v "$PWD/.data:/data" \
  seoul-traffic-guard:local
```

Deployment compatibility build:

```bash
docker build --platform linux/amd64 -t seoul-traffic-guard:amd64 .
```

Runtime smoke:

```bash
docker run --rm -d --name stg-runtime-smoke --env-file .env -e HOST=0.0.0.0 -e PLAYMCP_DB_PATH=/tmp/playmcp.db -p 8015:8000 seoul-traffic-guard:local
READY_URL=http://127.0.0.1:8015/ready python3 scripts/check_readiness.py
MCP_URL=http://127.0.0.1:8015/mcp python3 scripts/smoke_mcp_http.py
docker rm -f stg-runtime-smoke
```

## OAuth setup

1. Create or open the Kakao Developers app.
2. Enable Kakao Login.
3. Enable KakaoTalk message consent for `talk_message`.
4. Register redirect URI:

```text
http://localhost:8000/auth/kakao/callback
https://{deployed-host}/auth/kakao/callback
```

5. Start the server.
6. Open `/auth/kakao/start`.
7. Complete Kakao Login and consent.
8. Use `send_self_alert` with `dry_run=false`.

## PlayMCP deployment

Use `docs/playmcp_deployment_checklist.md` as the deployment checklist.

Git source build target:

| Field | Value |
| --- | --- |
| Dockerfile path | `Dockerfile` |
| Port | `8000` |
| Health check | `/health` |
| Readiness check | `/ready` |
| MCP endpoint | `/mcp` |

After receiving the deployed host:

1. Add `https://{deployed-host}/auth/kakao/callback` to Kakao Developers.
2. Set `KAKAO_REDIRECT_URI` to that deployed callback.
3. Set all required environment variables in PlayMCP in KC.
4. Confirm `/ready` returns `status: ok`.
5. Register the endpoint in PlayMCP.
6. Test from PlayMCP/ChatGPT for Kakao with the prompts above.

## Scheduled alerts

The server has an in-process scheduler that checks due alerts every 60 seconds while the process is running.
One failed scheduled alert does not stop later due alerts in the same run.

If the deployment environment does not keep background threads reliably alive, set `TASK_RUN_SECRET` and call the internal endpoint from an external scheduler:

```bash
curl -X POST \
  -H "Authorization: Bearer $TASK_RUN_SECRET" \
  https://{deployed-host}/tasks/run-due-alerts
```

If `TASK_RUN_SECRET` is not set, this endpoint returns 404.

## Data sources and attribution

- Seoul Open Data: `AccInfo`, Seoul real-time traffic incident information.
- Kakao Local API: address search and coordinate transform.
- ODsay API: public-transit route candidate lookup and selected route geometry.
- Kakao Login and KakaoTalk Message API: OAuth and self-message delivery.

User-facing summaries must not expose raw API payloads.
External API failures return short user-facing messages, not raw HTTP/OAuth errors.
OAuth callback failures return a generic reconnect message.

## Privacy and security notes

- Stores user alert areas, schedules, and OAuth tokens in SQLite.
- Separates data by user id from PlayMCP-related headers when present.
- Falls back to `local` only for local single-user development.
- Encrypts newly saved OAuth tokens when `TOKEN_ENCRYPTION_KEY` is configured.
- Rejects oversized MCP request bodies, oversized JSON-RPC batches, excessive per-user calls, and duplicate KakaoTalk sends.
- Does not read KakaoTalk chat history, chat rooms, files, or local app storage.
- Does not send messages to friends or group chats.
- Does not log API keys, client secrets, access tokens, or refresh tokens.

## Known limitations

- User identity header names must be confirmed against the actual PlayMCP runtime.
- Header spoofing can only be fully prevented if PlayMCP or the ingress strips external spoofed user headers or provides a signed/trusted identity boundary.
- Current implementation exposes 10 submission-facing tools, within the PlayMCP recommended 3-10 range.
- Scheduled alerts run only while the server process is alive.
- Public-transit route registration uses ODsay candidates and stores selected route geometry. Use `loadLane` graph geometry first if route-line precision becomes a review requirement.
- Deployed OAuth and user separation must be retested after the final PlayMCP in KC endpoint and user-id header are confirmed.
