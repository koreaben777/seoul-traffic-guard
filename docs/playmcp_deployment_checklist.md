# PlayMCP Deployment Checklist

Use this after local development is done and before requesting PlayMCP review.

## Local Gates

- [ ] Server is running locally: `python3 server.py`
- [ ] Local preflight passes: `python3 scripts/preflight.py`
- [ ] Docker image builds: `docker build -t seoul-traffic-guard:local .`
- [ ] Docker runtime smoke passes:

```bash
docker run --rm -d --name stg-runtime-smoke --env-file .env -e HOST=0.0.0.0 -e PLAYMCP_DB_PATH=/tmp/playmcp.db -p 8015:8000 seoul-traffic-guard:local
READY_URL=http://127.0.0.1:8015/ready python3 scripts/check_readiness.py
MCP_URL=http://127.0.0.1:8015/mcp python3 scripts/smoke_mcp_http.py
docker rm -f stg-runtime-smoke
```

## PlayMCP In KC

- [ ] Deploy from Git source using `Dockerfile`.
- [ ] Set port to `8000`.
- [ ] Set health check path to `/health`.
- [ ] Set required environment variables:
  - `KAKAO_REST_API_KEY`
  - `KAKAO_REDIRECT_URI`
  - `SEOUL_OPENAPI_KEY`
  - `PLAYMCP_DB_PATH`
- [ ] Set optional environment variables only if needed:
  - `KAKAO_CLIENT_SECRET`
  - `ALLOWED_ORIGINS`
  - `TASK_RUN_SECRET`
  - `PLAYMCP_USER_ID_HEADERS`
  - `REQUIRE_USER_ID_HEADER`
  - `MAX_REQUEST_BYTES`
  - `MAX_BATCH_REQUESTS`
  - `TOKEN_ENCRYPTION_KEY`
- [ ] Confirm the real PlayMCP user identity header name.
- [ ] Set `PLAYMCP_USER_ID_HEADERS` to only the confirmed header.
- [ ] Set `REQUIRE_USER_ID_HEADER=true` after PlayMCP header behavior is confirmed.
- [ ] Set `TOKEN_ENCRYPTION_KEY` if OAuth tokens will be persisted.

## After Deployed Host Is Issued

- [ ] Add `https://{deployed-host}/auth/kakao/callback` in Kakao Developers.
- [ ] Set `KAKAO_REDIRECT_URI=https://{deployed-host}/auth/kakao/callback`.
- [ ] Set `ALLOWED_ORIGINS` to the confirmed PlayMCP/Kakao Tools browser origin if the client sends `Origin`.
- [ ] Confirm `https://{deployed-host}/ready` returns `status: ok`.
- [ ] Register MCP endpoint: `https://{deployed-host}/mcp`.
- [ ] Open `https://{deployed-host}/auth/kakao/start` and complete OAuth.
- [ ] In PlayMCP/ChatGPT for Kakao, test:
  - `출근길을 서울시청 반경 1km로 등록해줘.`
  - `출근길 주변에 지금 통제나 사고 있어?`
  - `이 내용을 나에게 카카오톡으로 보내줘.`
  - `평일 아침 7시에 출근길 교통 이슈를 자동으로 알려줘.`

## Review Request

- [ ] Tool names do not contain `kakao`.
- [ ] Tool count is 10 and stays within the PlayMCP recommended 3-10 range.
- [ ] Raw API payloads, API keys, OAuth tokens, and full error traces are not exposed.
- [ ] Oversized MCP request bodies return 413.
- [ ] JSON-RPC batches above `MAX_BATCH_REQUESTS` are rejected.
- [ ] Per-user rate limiting returns a retry-later message.
- [ ] Duplicate KakaoTalk sends within 60 seconds are blocked.
- [ ] SQLite token rows do not contain raw `access_token` or `refresh_token` values when `TOKEN_ENCRYPTION_KEY` is set.
- [ ] Known limitations are documented in `README.md`.
