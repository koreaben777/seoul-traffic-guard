# Seoul Traffic Guard

Seoul Traffic Guard is a Remote MCP server for checking Seoul traffic disruptions near user-defined areas and sending optional KakaoTalk self-alerts.

Korean service name: `서울 교통 이슈 알리미`

## What it does

- Registers named alert areas from Seoul addresses.
- Geocodes addresses with Kakao Local API.
- Checks Seoul Open Data `AccInfo` traffic incidents.
- Matches incidents against registered area radius.
- Previews alert text before sending.
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
| `set_alert_area` | Register or update an alert area by label, address, and radius. |
| `list_alert_areas` | List the current user's alert areas. |
| `check_traffic_issues` | Check Seoul traffic issues near the current user's registered areas. |
| `preview_alert_message` | Build alert text before sending. |
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
PLAYMCP_DB_PATH=./playmcp.db
PLAYMCP_USER_ID_HEADERS=
ALLOWED_ORIGINS=
TASK_RUN_SECRET=
```

Notes:

- `KAKAO_CLIENT_SECRET` is required only when the Kakao app client secret is enabled.
- `PLAYMCP_USER_ID_HEADERS` is optional and comma-separated. Set it only if PlayMCP confirms a different user id header.
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
- Kakao Login and KakaoTalk Message API: OAuth and self-message delivery.

User-facing summaries must not expose raw API payloads.
External API failures return short user-facing messages, not raw HTTP/OAuth errors.
OAuth callback failures return a generic reconnect message.

## Privacy and security notes

- Stores user alert areas, schedules, and OAuth tokens in SQLite.
- Separates data by user id from PlayMCP-related headers when present.
- Falls back to `local` only for local single-user development.
- Does not read KakaoTalk chat history, chat rooms, files, or local app storage.
- Does not send messages to friends or group chats.
- Does not log API keys, client secrets, access tokens, or refresh tokens.

## Known limitations

- User identity header names must be confirmed against the actual PlayMCP runtime.
- Scheduled alerts run only while the server process is alive.
- Public API MVP supports point-and-radius areas, not route buffers or transit-route buffers.
- Deployed OAuth must be retested after the final PlayMCP in KC endpoint is issued.
