# PlayMCP Project Handoff

Date: 2026-06-19
Workspace: `/Users/june_kim/Documents/Attatchment-manager-PlayMCP`

## Current Decision

The original topic, **"KakaoTalk Attachment Assistant"**, was rejected.

The new topic is:

> **KakaoMap API + Seoul city traffic information based Traffic Issue Alert**
>
> Collect traffic disruption issues such as assemblies, accidents, roadworks, and road controls. If an issue falls inside a user-configured area, notify the user in advance through KakaoTalk so they can avoid lateness during commute or school travel.

## Rejected Topic: KakaoTalk Attachment Assistant

### Original Idea

Manage KakaoTalk attachment states:

1. Streaming: file remains on KakaoTalk server.
2. In-app download: downloaded inside KakaoTalk local app storage.
3. External download: saved outside KakaoTalk, such as phone gallery or files.

Problems:

- Streaming file expires and cannot be reopened.
- In-app and external downloads are mixed, wasting storage.
- Users cannot easily choose optimal storage state by file type, chat room purpose, or future access likelihood.

### Reason For Rejection

Under PlayMCP's expected model, a **remote MCP server is registered through a server URL**. This does not grant direct access to a user's KakaoTalk app, local app sandbox, chat database, cached attachments, or KakaoTalk server-side attachment metadata.

Public Kakao APIs checked during the chat are mostly for Kakao Login, Local/Map API, and KakaoTalk message sending. No public API was confirmed for:

- reading existing KakaoTalk chat rooms,
- reading prior chat messages,
- listing chat attachments,
- checking attachment expiry,
- reading KakaoTalk in-app downloaded files,
- deleting KakaoTalk app-internal cache.

### Remote MCP Access Boundary

A remote MCP server can access only:

- user input sent through the MCP host,
- parameters passed to MCP tool calls,
- data explicitly uploaded or selected by the user,
- data available through APIs for which the user granted OAuth/API consent,
- local file roots only if the MCP client explicitly supports and grants them.

It cannot directly access:

- KakaoTalk app internal storage,
- KakaoTalk local cache,
- KakaoTalk chat history,
- KakaoTalk server attachment metadata,
- user's phone filesystem outside explicit OS/user grants.

### Possible Narrow Variant

A reduced product could manage only files that users explicitly export/share from KakaoTalk. That variant is feasible but not the original idea.

## New Topic: Traffic Issue Alert

### Product Statement

Use Seoul traffic/city data and Kakao APIs to alert users about traffic issues near their registered areas before commute or school travel.

Safe phrasing:

> "Alert users about traffic controls and disruptions caused by assemblies, events, accidents, and roadworks."

This is safer than promising direct assembly prediction, because assembly data may not be consistently available as a standalone public API. The reliable product surface is the resulting road control/disruption information.

## Feasibility

### Overall

Feasibility is high.

Unlike the attachment assistant, this topic uses public data and user-consented messaging. It does not require private KakaoTalk app access.

### Data Sources

Candidate public sources:

- Seoul real-time incident/control information.
- Seoul real-time road traffic speed/congestion.
- Seoul real-time city data.

These can cover accidents, construction, events, controls, congestion, and area-level conditions depending on dataset coverage.

### Kakao API Role

Use Kakao APIs for:

- address to coordinate conversion,
- coordinate to administrative region conversion,
- map link or map display,
- KakaoTalk message delivery after user OAuth consent.

### MVP Scope

Do not start with full route optimization.

Minimum useful MVP:

1. User registers one or more alert areas: home, school, workplace, commute area.
2. Server periodically fetches Seoul traffic issue data.
3. Server geocodes/normalizes user area.
4. Server matches traffic issues against user's configured area/radius.
5. Server summarizes issue and urgency.
6. Server sends KakaoTalk "send to me" message.

## Permission And API Key Requirements

### Kakao Developers Key

For the MCP server, the first required key is:

- **REST API key**

Use it for:

- Kakao Local API,
- Kakao Login OAuth flow,
- KakaoTalk message API token flow.

Optional:

- **JavaScript key** only if a web UI directly renders Kakao Map in browser.

Not needed:

- Native app key unless building Android/iOS app.
- Admin key. Do not use it for this MVP.

### KakaoTalk Alert Permission

To send KakaoTalk alerts:

1. Enable Kakao Login.
2. Register OAuth redirect URI.
3. Configure consent item for KakaoTalk message sending, commonly `talk_message`.
4. User must log in and grant consent.
5. MCP server stores and refreshes OAuth tokens securely.
6. Server sends message through KakaoTalk Message API, preferably "send to me" for MVP.

Sending to other people is not part of MVP and likely requires broader permission/review.

### Seoul Open Data Key

Need a Seoul Open Data API key for traffic/city datasets.

### User Data

Sensitive user data:

- home/school/work address,
- commute time window,
- Kakao OAuth tokens.

Minimal approach:

- Ask user to manually enter address or district instead of using live GPS.
- Store only normalized coordinates and label.
- Mask all tokens in logs.
- Do not store unnecessary chat/message content.

## Kakao API Key Issuance Flow Observed In Chrome

The user opened `https://apis.map.kakao.com/`.

Observed flow:

1. Click **APP KEY 발급**.
2. It opens Kakao Developers app console:
   - `https://developers.kakao.com/console/app`
3. The account was logged in.
4. The console showed:
   - `전체 앱0`
   - button: `앱 생성`
5. Clicking `앱 생성` opened a modal.

App creation modal fields observed:

- App icon: optional upload.
- App name: required.
- Company name: required.
- Category: required.
- Representative app domain: optional.
- Policy confirmation checkbox.
- Save button disabled until required fields/check are completed.

No app was created by the agent.

### Guide To Create Key

1. Open Kakao Developers app console.
2. Click `앱 생성`.
3. Fill:
   - App name: `교통 이슈 알리미` or similar.
   - Company/team name.
   - Category matching mobility/lifestyle/service.
   - Representative domain if available.
4. Check policy confirmation.
5. Save.
6. Open created app detail.
7. Copy **REST API key** from app key section.
8. If building web map UI:
   - copy JavaScript key,
   - register Web platform domain such as localhost and deployed domain.
9. For KakaoTalk message alert:
   - enable Kakao Login,
   - add redirect URI,
   - configure message consent item,
   - implement OAuth flow.

Recommended environment variables:

```env
KAKAO_REST_API_KEY=...
KAKAO_REDIRECT_URI=https://your-mcp-server.com/auth/kakao/callback
SEOUL_OPENAPI_KEY=...
PLAYMCP_DB_PATH=./playmcp.db
```

Only if frontend renders Kakao Map:

```env
KAKAO_JAVASCRIPT_KEY=...
```

Do not store `KAKAO_ADMIN_KEY` for this MVP.

## Suggested MCP Tools

Keep the tool set small.

```text
set_alert_area(address, radius_m, label)
list_alert_areas()
fetch_traffic_issues()
match_traffic_issues()
send_kakao_alert(issue_id)
```

Potential later tools:

```text
set_commute_window(label, start_time, end_time)
preview_alert_message(issue_id)
disable_alert_area(label)
```

## Next Thread Instructions

Continue from this handoff.

Priority:

1. Do not resume the KakaoTalk attachment assistant topic except as rejected context.
2. Continue with the traffic issue alert topic.
3. Verify Seoul traffic/city datasets and exact API endpoints before implementation.
4. Keep implementation minimal.
5. First build a small remote MCP server skeleton only after source data/API endpoints are confirmed.
6. Do not create Kakao app, submit forms, reveal keys, or push git unless the user explicitly asks.
7. If implementing, use environment variables for all keys and mask secrets in logs.

Suggested immediate next task:

> Confirm exact Seoul Open Data datasets/endpoints for incident/control/roadwork/congestion and draft the minimal MCP server tool contract.

## Competition MCP Development Plan

This plan is for the new **Traffic Issue Alert** topic only.

### Confirmed Public API Surface

Primary Seoul Open Data endpoint format:

```text
http://openapi.seoul.go.kr:8088/{SEOUL_OPENAPI_KEY}/{TYPE}/{SERVICE}/{START_INDEX}/{END_INDEX}/{OPTIONAL_PARAMS}
```

Confirmed MVP datasets:

| Purpose | Seoul dataset | SERVICE | Notes |
| --- | --- | --- | --- |
| Traffic disruption issues | 서울시 실시간 돌발 정보 | `AccInfo` | Primary feed. Covers disruptions and controls through `ACC_TYPE`, `ACC_DTYPE`, `ACC_INFO`, `LINK_ID`, `GRS80TM_X`, `GRS80TM_Y`. |
| Road speed for affected link | 서울시 실시간 도로 소통 정보 | `TrafficInfo` | Optional MVP enrichment. Requires `LINK_ID`; returns `PRCS_SPD`, `PRCS_TRV_TIME`. |
| Area metadata | 서울시 소통 돌발 교통 권역 정보 | `RegionInfo` | Reference data for Seoul traffic regions. |
| Incident type labels | 서울시 돌발 유형 코드 정보 | `AccMainCode` | Maps `ACC_TYPE`; sample includes traffic accident, disabled vehicle, pedestrian accident, roadwork, falling object. |
| Incident subtype labels | 서울시 돌발 세부유형 코드 정보 | `AccSubCode` | Maps `ACC_DTYPE`. |

Useful sample calls:

```text
http://openapi.seoul.go.kr:8088/sample/xml/AccInfo/1/5/
http://openapi.seoul.go.kr:8088/sample/xml/TrafficInfo/1/5/1220003800
http://openapi.seoul.go.kr:8088/sample/xml/AccMainCode/1/5/
http://openapi.seoul.go.kr:8088/sample/xml/AccSubCode/1/5/
```

Kakao API surface for MVP:

- Kakao Local address search: `GET https://dapi.kakao.com/v2/local/search/address.json`
- Kakao Local coordinate to region: `GET https://dapi.kakao.com/v2/local/geo/coord2regioncode.json`
- Kakao Local coordinate transform: `GET https://dapi.kakao.com/v2/local/geo/transcoord.json`
- KakaoTalk "send to me" default message: `POST https://kapi.kakao.com/v2/api/talk/memo/default/send`

Sources:

- Seoul real-time disruption dataset: https://data.seoul.go.kr/dataList/OA-13315/A/1/datasetView.do
- Seoul Open API usage guide: https://data.seoul.go.kr/together/guide/useGuide.do
- Kakao Local REST API: https://developers.kakao.com/docs/latest/ko/local/dev-guide
- KakaoTalk Message REST API: https://developers.kakao.com/docs/latest/ko/kakaotalk-message/rest-api

### Development Phases

#### Phase 0 - Keys And Scope Lock

Goal: make the demo buildable without over-permission.

Tasks:

1. Create `.env.example` only, not real secrets.
2. Require only `SEOUL_OPENAPI_KEY`, `KAKAO_REST_API_KEY`, `KAKAO_REDIRECT_URI`.
3. Exclude `KAKAO_ADMIN_KEY`.
4. Document that user addresses and Kakao OAuth tokens are sensitive.

Done when:

- Local config loads from environment variables.
- Missing keys fail with masked messages.

#### Phase 1 - Seoul Data Spike

Goal: prove the exact traffic data path before building the MCP server.

Tasks:

1. Fetch `AccInfo` with the sample key and real key.
2. Fetch `AccMainCode` and `AccSubCode`; build a small code-name map.
3. Fetch `TrafficInfo` for one `LINK_ID` from `AccInfo`.
4. Verify whether `GRS80TM_X/Y` can be converted by Kakao `transcoord` with `input_coord=WTM`; if not, use a minimal coordinate conversion helper after confirming the correct CRS.

Done when:

- One sample disruption is normalized to `{id, type, subtype, text, start_at, expected_clear_at, link_id, lon, lat}`.
- No route optimization exists yet.

#### Phase 2 - Minimal Local Data Model

Goal: store only what the alert matcher needs.

Use a simple file or SQLite table:

```text
alert_area(label, lat, lon, radius_m)
kakao_token(user_id, access_token, refresh_token, expires_at)
sent_alert(issue_id, area_label, sent_at)
```

Tasks:

1. Save alert areas after address geocoding.
2. Deduplicate alerts by `issue_id + area_label`.
3. Mask tokens in all logs.

Skipped for MVP:

- live GPS,
- route history,
- chat content storage,
- sending to friends or groups.

#### Phase 3 - MCP Server Skeleton

Goal: expose the smallest useful tool contract.

MVP tools:

```text
set_alert_area(address, radius_m, label)
list_alert_areas()
fetch_traffic_issues(limit=100)
match_traffic_issues()
send_kakao_alert(issue_id)
```

Tool behavior:

- `set_alert_area`: Kakao address search -> save normalized coordinate.
- `fetch_traffic_issues`: Seoul `AccInfo` -> normalized issue list.
- `match_traffic_issues`: distance check against saved areas.
- `send_kakao_alert`: send one "send to me" KakaoTalk message after OAuth consent.

Keep matching simple:

```text
alert if distance(issue.lonlat, area.lonlat) <= area.radius_m
```

#### Phase 4 - Kakao OAuth And Message Send

Goal: make the alert deliverable through user consent.

Tasks:

1. Enable Kakao Login in the Kakao app.
2. Register redirect URI.
3. Request `talk_message` consent.
4. Store refreshable tokens securely.
5. Send a default-template "send to me" message with issue title, road/control text, expected clear time, and Kakao Map link.

Done when:

- A test user can authorize once and receive one manual alert.

#### Phase 5 - Scheduler And Demo Scenario

Goal: make the competition demo repeatable.

Tasks:

1. Add one periodic job, such as every 5-10 minutes.
2. Fetch issues, match areas, skip already sent alerts.
3. Provide one command to run the server locally.
4. Prepare a demo using one registered commute area and one live/sample `AccInfo` disruption.

Skipped until after MVP:

- full commute route optimization,
- predictive assembly detection,
- push to other users,
- JavaScript map UI.

### Build Order

1. Data spike script.
2. MCP server with in-memory or file-backed alert areas.
3. Kakao OAuth callback.
4. KakaoTalk message send.
5. Scheduler.
6. Demo README.

### Verification Checklist

- `AccInfo` sample and real-key calls work.
- `TrafficInfo` enrichment works for at least one `LINK_ID`.
- Coordinate conversion is verified against a known Seoul location.
- `set_alert_area` stores no raw address unless explicitly needed.
- `match_traffic_issues` catches an issue inside radius and ignores one outside radius.
- Kakao alert sends only after OAuth consent.
- Logs never print API keys, access tokens, refresh tokens, or full home/school addresses.
