# Simulation User Flow Coverage

Date: 2026-06-23
Last updated: 2026-06-23 after ODsay Server IP allowlist fix

This document defines a practical end-to-end coverage set for the current Seoul Traffic Guard MCP server. It uses the public 10-tool contract and avoids real KakaoTalk sends unless explicitly requested.

## Scope

Test through real user intents, not isolated tool calls:

1. Empty-state lookup
2. Address-radius area registration
3. Traffic issue lookup
4. Alert send dry-run
5. Scheduled alert create/list/delete
6. Alert area delete
7. Public-transit route candidate lookup
8. Selected transit route registration

Out of scope for this pass:

- Real KakaoTalk send with `dry_run=false`
- Production PlayMCP endpoint verification

## Test Setup

Local server:

```bash
python3 server.py
```

Simulator thread:

- Thread: `MCP Simulator`
- User id: `codex-sim-tools10-flow`
- MCP URL: `http://127.0.0.1:8000/mcp`

Direct local cross-check user:

- User id: `codex-sim-tools10-doc`

ODsay retest users:

- Direct local: `codex-sim-odsay-retest`
- Simulator thread: `codex-sim-odsay-thread-retest`

## Coverage Matrix

| User intent | Expected tool | Expected result |
| --- | --- | --- |
| 내 교통 알림 지역 목록 보여줘. | `list_alert_areas` | Empty state is clear. |
| 출근길을 서울시청 반경 1km로 등록해줘. | `set_alert_area` | Point-radius area is registered. |
| 출근길 주변 교통 이슈를 확인해줘. | `check_traffic_issues` | Matching Seoul traffic issues are returned, or a clear no-issue message is returned. |
| 방금 확인한 내용을 실제 발송 말고 발송 전 확인만 해줘. | `send_self_alert` with `dry_run=true` | No real send; dry-run confirmation is returned. |
| 평일 오전 7시에 출근길 교통 이슈를 알려줘. 단, 2026-06-24는 쉬어줘. | `set_scheduled_alert` | Weekday schedule with skip date is registered. |
| 예약 알림 목록 보여줘. | `list_scheduled_alerts` | Registered schedule is listed. |
| 출근길 예약 알림을 삭제해줘. | `delete_scheduled_alert` | Schedule is deleted. |
| 출근길 알림 지역도 삭제해줘. | `delete_alert_area` | Area is deleted. |
| 이촌로 174에서 을지로 19까지 대중교통 경로 후보를 보여줘. | `find_transit_route_options` | Candidate routes are returned. |
| 1번 경로를 출근길로 등록해줘. | `set_selected_transit_route_alert_area` | Registers selected route only after candidate route ids exist. |

## Simulation Thread Result

`MCP Simulator` ran the user-flow set with `SIM_USER_ID=codex-sim-tools10-flow`.

| Step | Status | Tool | Observed result |
| --- | --- | --- | --- |
| Empty area lookup | PASS | `list_alert_areas` | No registered areas. |
| Register Seoul City Hall commute area | PASS | `set_alert_area` | `출근길` registered at `서울 중구 세종대로 110`, radius 1000m. |
| Check commute traffic issues | PASS | `check_traffic_issues` | 2 issues found near `출근길`. |
| Dry-run send preview | PASS | `send_self_alert` | Dry-run confirmed; no real send. |
| Create weekday schedule with skip date | PASS | `set_scheduled_alert` | Weekday 07:00 schedule registered with `2026-06-24` skip date. |
| List schedules | PASS | `list_scheduled_alerts` | Registered schedule listed. |
| Delete schedule | PASS | `delete_scheduled_alert` | Schedule deleted. |
| Delete area | PASS | `delete_alert_area` | `출근길` area deleted. |
| Find transit route options | PASS | `find_transit_route_options` | Candidate route lookup succeeded after ODsay Server IP allowlist fix. |
| Register selected transit route | PASS | `set_selected_transit_route_alert_area` | Route 1 was registered as `출근길`. |

## Direct Local Cross-Check

Commands were run with `SIM_USER_ID=codex-sim-tools10-doc`.

| Check | Result |
| --- | --- |
| `list_alert_areas` before setup | `No alert areas registered.` |
| `set_alert_area` for `출근길`, `서울시청`, 1000m | PASS |
| `check_traffic_issues` for `출근길` | PASS, returned 서소문로 전면통제 and 소공로 공사 issues |
| `send_self_alert` with `dry_run=true` | PASS, dry-run only |
| `set_scheduled_alert` weekday 07:00 with `2026-06-24` skip date | PASS |
| `list_scheduled_alerts` | PASS |
| `delete_scheduled_alert` | PASS |
| `delete_alert_area` | PASS |
| `find_transit_route_options` before ODsay IP fix | BLOCKED by ODsay Server API Key or Server IP allowlist |
| `find_transit_route_options` after ODsay IP fix | PASS, returned 5 public-transit candidates |
| `set_selected_transit_route_alert_area` with `route-1` | PASS, registered route 1 as `출근길` |
| `check_traffic_issues` for selected transit route | PASS, no current issues near registered route |

## Assessment

Core non-transit user flow is covered end to end:

- Area creation
- Traffic issue lookup
- Dry-run message path
- Scheduled alert lifecycle
- Deletion lifecycle

ODsay-backed transit coverage is now unblocked locally.

The retest returned these candidate examples for `이촌로 174` to `을지로 19`:

- `route-1`: `100 이촌동두산위브트레지움.한강대우아파트-롯데영프라자`
- `route-2`: `504/500 한강대교북단.LG유플러스-을지로입구.시청입구`

The 500 bus route exists as the second candidate. If a user wants the 500 bus, they should choose route 2, not route 1.

Retest commands:

```bash
SIM_USER_ID=codex-sim-odsay-retest python3 scripts/codex_mcp_chat.py call find_transit_route_options '{"label":"출근길","origin":"이촌로 174","destination":"을지로 19"}'
SIM_USER_ID=codex-sim-odsay-retest python3 scripts/codex_mcp_chat.py call set_selected_transit_route_alert_area '{"label":"출근길","route_ids":["route-1"],"radius_m":500}'
SIM_USER_ID=codex-sim-odsay-retest python3 scripts/codex_mcp_chat.py call check_traffic_issues '{"label":"출근길"}'
```
