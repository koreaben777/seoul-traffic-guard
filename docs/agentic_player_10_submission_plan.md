# Agentic Player 10 공모전 제출 계획

작성일: 2026-06-19

## 1. 공모전 요약

참가 대상 공모전은 **Agentic Player 10**이다. 직접 개발한 Remote MCP 서버를 PlayMCP에 등록하고, 심사 승인 후 전체 공개 상태로 전환한 뒤 공모전 페이지의 예선 참여 폼으로 제출한다.

공식 일정:

| 단계 | 기간/일자 | 해야 할 일 |
| --- | --- | --- |
| 예선 접수 | 2026-06-15 ~ 2026-07-14 | MCP 서버 개발, PlayMCP in KC 배포, PlayMCP 등록/심사, 전체 공개, 예선 접수 |
| 본선 진출작 발표 | 2026-07-30 | 카카오톡 채널 메시지로 개별 안내 |
| 본선 추가 개발 | 2026-07-30 ~ 2026-08-27 | Kakao Tools 공개 및 본선 심사용 추가 개발 |
| 공개 투표 | 2026-08-31 ~ 2026-09-28 | Kakao Tools 사용자 투표 및 심사 |
| 최종 심사/시상 | 2026-10-23 | 카카오 AI캠퍼스 오프라인 시상 |

시상/지원:

- 대상: 과기정통부 장관상, 1,000만원
- 금상: 500만원, 2명/팀
- 은상: 100만원, 7명/팀
- 본선 진출작은 Kakao Tools에 공개되고 사용자 투표 대상이 된다.

심사 관점:

- 창의성: 새 아이디어로 문제를 해결하고 파급력이 있는가
- 편의성: UI/UX와 사용 흐름이 실질적 일상 가치를 주는가
- 안정성: 안정적으로 구동되고 정확한 데이터를 제공하며 보안 문제가 없는가

## 2. 제출까지의 필수 흐름

1. 로컬에서 MCP 서버를 개발한다.
2. MCP Inspector로 표준 준수 여부를 확인한다.
3. PlayMCP in KC에서 MCP 서버를 배포하고 Endpoint URL을 받는다.
4. PlayMCP 개발자 콘솔에서 새 MCP 서버를 **임시 등록**한다.
5. PlayMCP 채팅에서 충분히 테스트한다.
6. 테스트 완료 후 PlayMCP에서 **심사 요청**한다.
7. 심사 승인 후 공개 상태를 **나에게만 공개**에서 **전체 공개**로 바꾼다.
8. 승인된 MCP 상세 페이지 URL을 복사한다.
9. 공모전 페이지의 **Player 예선 참여** 버튼으로 비즈폼 접수를 완료한다.

중요 제약:

- 공모전용 MCP 서버는 PlayMCP in KC를 통해 생성한 Endpoint URL로 등록해야 한다.
- PlayMCP in KC는 2026-06-15 ~ 2026-07-14 예선 접수 기간에 서버 발급이 가능하다.
- 계정당 MCP 서버는 최대 2대까지 등록할 수 있다.
- 최종 제출은 1회만 가능하다.
- 심사는 최대 영업일 기준 7일이 걸릴 수 있다. 2026-07-07까지의 심사 요청은 2026-07-10까지 처리 예정이라고 안내되어 있으므로, 2026-07-03 전후를 내부 심사 요청 목표일로 잡는다.

## 3. 개발 전 준비 단계

개발을 시작하기 전에 API 키, 앱 등록, OAuth 방향을 먼저 잠근다. 이 단계가 끝나기 전에는 MCP 서버 구현을 시작하지 않는다.

### 3.1 계정과 콘솔 접근 확인

필수 계정:

| 계정/콘솔 | 목적 | 확인할 것 |
| --- | --- | --- |
| Kakao Developers | REST API 키, Kakao Login, KakaoTalk Message API 설정 | 앱 생성 가능 여부 |
| 서울 열린데이터광장 | 서울 교통 Open API 인증키 발급 | 일반 Open API 키 신청 가능 여부 |
| PlayMCP | MCP 서버 등록/심사 | 개발자 콘솔 접근 가능 여부 |
| PlayMCP in KC | 공모전용 MCP 서버 배포 | 서버 발급 가능 여부 |

완료 기준:

- 각 콘솔에 로그인할 수 있다.
- 담당 계정의 대표 이메일을 확인했다.
- 키/토큰을 저장할 로컬 위치를 정했다. 실제 키는 저장소에 커밋하지 않는다.

### 3.2 Kakao Developers 앱 등록

목적:

- Kakao Local API 호출용 REST API 키 확보
- Kakao Login OAuth 설정
- KakaoTalk "나에게 보내기" 알림을 위한 메시지 동의항목 준비

작업:

1. Kakao Developers 앱 관리 페이지에서 앱을 생성한다.
2. 앱 이름은 서비스명 후보인 `서울 교통 이슈 알리미` 또는 `Seoul Traffic Guard`로 둔다.
3. 회사명/팀명, 카테고리, 대표 도메인을 입력한다.
4. 앱 생성 후 **REST API 키**를 확인한다.
5. 키는 로컬 `.env`에만 둔다.

필요하지 않은 것:

- Admin Key: MVP에서 사용하지 않는다.
- Native App Key: Android/iOS 앱을 만들지 않으므로 사용하지 않는다.
- JavaScript Key: 웹 지도 UI를 만들기 전까지 사용하지 않는다.

완료 기준:

```env
KAKAO_REST_API_KEY=...
```

### 3.3 Kakao Login 및 메시지 권한 준비

목적:

- 사용자가 동의한 뒤 본인 카카오톡 "나와의 채팅방"으로 알림을 받을 수 있게 한다.

작업:

1. Kakao Developers 앱에서 Kakao Login을 활성화한다.
2. 로컬 개발용 redirect URI를 임시 등록한다.
3. 배포 후 PlayMCP in KC 또는 MCP 서버의 실제 OAuth callback URL을 추가한다.
4. KakaoTalk 메시지 발송에 필요한 동의항목 `talk_message`를 확인한다.
5. OAuth 토큰 저장 방식과 마스킹 정책을 정한다.

예상 redirect URI:

```text
http://localhost:8000/auth/kakao/callback
https://{deployed-mcp-host}/auth/kakao/callback
```

완료 기준:

```env
KAKAO_REDIRECT_URI=...
```

주의:

- 사용자의 카카오맵 저장 장소, 최근 검색, 최근 길찾기 기록을 가져오는 동의항목은 공개 API 기준 MVP에 포함하지 않는다.
- 메시지는 "나에게 보내기"만 사용한다. 친구/단체방 발송은 제외한다.

### 3.4 서울 열린데이터광장 Open API 키 신청

목적:

- `AccInfo`, `TrafficInfo`, `AccMainCode`, `AccSubCode`, `RegionInfo` 호출용 인증키 확보

작업:

1. 서울 열린데이터광장에 로그인한다.
2. Open API 인증키를 신청한다.
3. 샘플 키로 먼저 5건 호출을 확인한다.
4. 실제 키로 `AccInfo` 1~100건 호출을 확인한다.
5. 요청 한도와 에러 메시지 처리를 확인한다.

완료 기준:

```env
SEOUL_OPENAPI_KEY=...
```

필수 스모크 테스트:

```text
http://openapi.seoul.go.kr:8088/sample/xml/AccInfo/1/5/
http://openapi.seoul.go.kr:8088/{SEOUL_OPENAPI_KEY}/json/AccInfo/1/100/
```

### 3.5 PlayMCP 제출 제약 재확인

목적:

- 구현 전에 심사 반려 가능성을 줄인다.

작업:

1. MCP 서버명과 tool name에 `kakao`를 넣지 않는다.
2. 현재 제출용 구현은 PlayMCP 권장 범위에 맞춰 10개 tool만 노출한다.
3. 모든 tool의 `annotations` 필드를 설계한다.
4. Streamable HTTP만 지원하도록 기술 스택을 고른다.
5. OAuth가 필요한 tool과 필요 없는 tool을 나눈다.

현재 tool 분류:

| Tool | 인증 필요 | 비고 |
| --- | --- | --- |
| `set_alert_area` | 선택 | 주소 저장 정책 때문에 사용자별 저장소가 필요하면 인증 필요 |
| `list_alert_areas` | 선택 | 사용자별 저장소가 필요하면 인증 필요 |
| `delete_alert_area` | 선택 | 등록된 생활권 삭제 |
| `find_transit_route_options` | 선택 | ODsay 후보 경로 조회 |
| `set_selected_transit_route_alert_area` | 선택 | 사용자가 고른 ODsay 후보 경로 등록 |
| `check_traffic_issues` | 아니오 | 공개 교통 데이터 조회 중심 |
| `send_self_alert` | 예 | Kakao OAuth 토큰 필요 |
| `set_scheduled_alert` | 예 | 예약 알림 저장 및 자동 발송 준비 |
| `list_scheduled_alerts` | 선택 | 등록된 예약 알림 조회 |
| `delete_scheduled_alert` | 선택 | 예약 알림 삭제 |

### 3.6 개발 착수 조건

아래 항목이 끝나면 구현을 시작한다.

- [ ] Kakao Developers 앱 생성 완료
- [ ] REST API 키 확보
- [ ] Kakao Login 활성화 여부 확인
- [ ] `talk_message` 동의항목 설정 가능 여부 확인
- [ ] 서울 Open API 키 확보
- [ ] `AccInfo` 샘플 호출 성공
- [ ] 실제 키는 `.env`에만 저장
- [ ] `.env.example`에 변수명만 정리
- [ ] 서버명/tool name 금지어 점검

## 4. PlayMCP 서버 심사 조건

서버 조건:

- MCP 지원 버전: 최소 `2025-03-26`, 최대 `2025-11-25`
- 전송 방식: **Streamable HTTP**만 지원
- Remote MCP 서버만 지원하며 공개 URL로 접근 가능해야 함
- Stateless 서버 권장
- 사용자 인증이 필요하면 OAuth 인증 또는 커스텀 헤더 방식을 지원
- MCP Inspector로 사전 점검
- 활발히 운영되는 MCP SDK 사용 또는 참조
- MCP Server Name 또는 Tool Name에 `kakao`를 prefix/suffix/중간 문자열로 포함하면 안 됨

Tool 조건:

- 툴 이름은 1~128자
- 허용 문자: 영어 대소문자, 숫자, `_`, `-`
- 툴 이름은 중복 금지, 대소문자 구분
- 서버당 툴 20개 초과 금지, 3~10개 권장
- 각 tool에는 `name`, `description`, `inputSchema`, `annotations` 포함
- `annotations`에는 `title`, `readOnlyHint`, `destructiveHint`, `openWorldHint`, `idempotentHint`를 모두 지정
- description은 가능한 영어 권장, 서비스 이름을 영문/국문 병기, 1,024자 이내
- result는 최소 크기로 정리하고 원본 API 응답을 그대로 반환하지 않음

운영 조건:

- 툴 평균 응답속도 100ms 이내 목표
- p99 응답속도 3,000ms 필수
- 광고 노출을 유도하지 않음
- 키, 토큰, 주소 등 민감정보는 로그에 노출하지 않음

## 5. 출품 주제 구체화

출품명 후보:

> Seoul Traffic Guard / 서울 교통 이슈 알리미

금지어 회피:

- 서버명과 tool name에는 `kakao`를 넣지 않는다.
- Kakao API는 내부 구현 설명과 환경 변수명에서만 언급한다.

서비스 한 줄 설명:

> 서울시 실시간 돌발 교통정보와 사용자가 등록한 생활권을 비교해, 등교/출근 전 지연 위험이 있는 교통 통제·공사·사고 정보를 알려주는 MCP 서버.

MVP 가치:

- 집/학교/직장 주변의 교통 통제, 공사, 사고, 행사성 통제 정보를 미리 확인한다.
- 사용자는 “오늘 아침 학교 주변에 지연 위험이 있어?”처럼 자연어로 물을 수 있다.
- 필요 시 본인 카카오톡 “나와의 채팅방”으로 알림을 보낸다.

## 6. 최종 목표 사용자 경험

최종 목표는 사용자가 **카카오톡의 ChatGPT for Kakao 안에서 대화만으로 즉시 서비스를 쓰는 것**이다. 사용자는 별도 웹 콘솔이나 개발자 도구를 직접 조작하지 않고, ChatGPT for Kakao가 PlayMCP/Kakao Tools에 등록된 MCP 서버를 도구로 호출한다.

목표 상호작용:

```text
카카오톡 실행
→ ChatGPT for Kakao 대화 진입
→ 사용자가 자연어로 요청
→ ChatGPT for Kakao가 PlayMCP에 등록된 MCP tool 호출
→ Seoul Traffic Guard가 생활권 저장, 교통 이슈 조회, 예약 저장을 수행
→ 필요한 경우 사용자 본인의 카카오톡 나와의 채팅방으로 알림 발송
```

대표 사용자 발화:

```text
출근길을 서울시청 반경 1km로 등록해줘.
내 출근길 주변에 지금 통제나 사고 있어?
이 내용을 나에게 카카오톡으로 보내줘.
평일 아침 7시에 출근길 교통 이슈를 자동으로 알려줘.
예약 알림 목록 보여줘.
출근길 아침 알림 삭제해줘.
```

이 목표는 카카오톡 채팅방을 우리가 직접 읽거나 조작하는 방식이 아니다. 사용자 입력은 ChatGPT for Kakao/PlayMCP 호스트를 통해 MCP tool 인자로 전달되고, 카카오톡은 OAuth 동의 후 알림 수신 채널로 사용한다.

사용자 관점의 성공 기준:

1. 카카오톡 안의 ChatGPT for Kakao에서 자연어로 생활권을 등록할 수 있다.
2. 등록된 생활권 주변의 서울시 실시간 돌발 교통정보를 짧게 확인할 수 있다.
3. 사용자가 명시적으로 요청하면 본인 카카오톡으로 알림을 받을 수 있다.
4. 사용자가 요일과 시간을 말하면 예약 알림이 저장된다.
5. 예약 시각에 서버가 교통 이슈를 확인하고, 조건에 맞으면 본인 카카오톡으로 알림을 보낸다.

현재 로컬 구현과의 차이:

| 구분 | 현재 로컬 구현 | 최종 목표 |
| --- | --- | --- |
| 사용자 진입점 | 로컬 MCP 호출 또는 직접 HTTP 호출 | 카카오톡의 ChatGPT for Kakao 대화 |
| 사용자 식별 | 단일 사용자 SQLite 저장 | PlayMCP 사용자 단위 저장 |
| OAuth Redirect URI | `localhost` | 배포 Endpoint 기반 URI |
| 알림 채널 | 나와의 채팅방 전송 성공 | 사용자별 OAuth 토큰으로 나와의 채팅방 전송 |
| 검증 위치 | 로컬 테스트와 수동 OAuth | PlayMCP 임시 등록 후 ChatGPT/Kakao Tools 대화 |

## 7. Current Tool Contract

Tool name은 `kakao`를 포함하지 않는다.

| Tool | 용도 | Annotation 방향 |
| --- | --- | --- |
| `set_alert_area` | 주소와 반경을 등록 | destructiveHint=false, idempotentHint=true |
| `list_alert_areas` | 등록된 생활권 목록 조회 | readOnlyHint=true |
| `delete_alert_area` | 등록된 생활권 삭제 | destructiveHint=true, idempotentHint=true |
| `find_transit_route_options` | ODsay 대중교통 후보 경로 조회 | readOnlyHint=true, openWorldHint=true |
| `set_selected_transit_route_alert_area` | 사용자가 선택한 후보 경로 등록 | destructiveHint=false, idempotentHint=true |
| `check_traffic_issues` | 등록 생활권 주변 실시간 돌발정보 조회/매칭 | readOnlyHint=true, openWorldHint=true |
| `send_self_alert` | 사용자 동의 후 나에게 알림 발송 | destructiveHint=false, openWorldHint=true |
| `set_scheduled_alert` | 지정 요일/시간에 생활권 교통 이슈 자동 알림 예약 | destructiveHint=false, idempotentHint=true |
| `list_scheduled_alerts` | 등록된 자동 알림 예약 조회 | readOnlyHint=true |
| `delete_scheduled_alert` | 자동 알림 예약 삭제 | destructiveHint=true, idempotentHint=true |

현재 제출용 구현은 PlayMCP 권장 범위에 맞춰 10개 tool만 노출한다. 행정동 전체 영역 등록, 수동 경유지 등록, 다중 일괄 등록, 별도 미리보기 tool은 제출 범위에서 제외한다. 카카오톡 메시지는 KakaoTalk Message API의 "나에게 보내기" 범위로 제한한다. 공식 문서 기준 기본 템플릿 나에게 보내기는 `talk_message` 동의항목과 액세스 토큰이 필요하며, 친구 등 다른 사용자에게 보내기는 별도 사용 권한이 필요하므로 제외한다.

예약 알림은 사용자가 등록한 생활권 label을 기준으로 동작한다. 예를 들어 `출근길` 생활권을 등록한 뒤 `set_scheduled_alert`로 평일 07:00 예약을 만들면, 서버는 해당 시각에 교통 이슈를 확인하고 본인 카카오톡으로 알림을 보낸다. 현재 구현은 공휴일 제외, 임시중지, 반복 간격 규칙도 지원한다.

## 8. 데이터/API 설계

서울 Open API:

| 용도 | 데이터셋 | SERVICE |
| --- | --- | --- |
| 돌발 교통 이슈 | 서울시 실시간 돌발 정보 | `AccInfo` |
| 링크별 소통 속도 | 서울시 실시간 도로 소통 정보 | `TrafficInfo` |
| 권역 참고 정보 | 서울시 소통 돌발 교통 권역 정보 | `RegionInfo` |
| 돌발 유형 코드 | 서울시 돌발 유형 코드 정보 | `AccMainCode` |
| 돌발 세부유형 코드 | 서울시 돌발 세부유형 코드 정보 | `AccSubCode` |

Kakao API:

- 주소 검색: `GET https://dapi.kakao.com/v2/local/search/address.json`
- 좌표계 변환: `GET https://dapi.kakao.com/v2/local/geo/transcoord.json`
- 좌표 행정구역 변환: `GET https://dapi.kakao.com/v2/local/geo/coord2regioncode.json`
- 나에게 메시지 발송: `POST https://kapi.kakao.com/v2/api/talk/memo/default/send`

환경 변수:

```env
SEOUL_OPENAPI_KEY=
KAKAO_REST_API_KEY=
KAKAO_REDIRECT_URI=
PLAYMCP_DB_PATH=
ALLOWED_ORIGINS=
TASK_RUN_SECRET=
```

실제 키는 저장소에 저장하지 않는다.

근거:

- 서울 열린데이터광장은 Open API 사용 전 인증키 발급을 안내하며, 한 번에 최대 1,000건 요청 제한을 안내한다.
- `서울시 실시간 돌발 정보` 데이터셋은 교통 분야의 실시간/매일 갱신 데이터로, 통제·교통상황·교통량 태그를 갖는다.
- Kakao Local API는 REST API 키로 주소를 좌표로 변환한다.
- Kakao Login은 사용 설정과 Redirect URI 등록이 필수다.

## 9. 생활권 추가 방식별 가능성

생활권은 내부적으로 다음 중 하나로 저장한다.

```text
point_circle: 중심 좌표 + 반경
route_buffer: 경로 polyline + 버퍼 반경
transit_line_buffer: 대중교통 노선/정류장 polyline + 버퍼 반경
admin_area: 구/동 행정구역명 또는 행정구역 polygon
```

MVP는 `point_circle`만 구현한다. 나머지는 공모전 본선 또는 시상 이후 확장으로 둔다.

| 추가 방식 | 가능성 | 구현 방향 | MVP 포함 |
| --- | --- | --- | --- |
| 특정 위치 기반 | 높음 | 사용자가 집/회사/학교 등 이름과 주소를 입력하면 Kakao Local API로 좌표 변환 후 원형 생활권 저장 | 포함 |
| 특정 경로 기반 | 중간 | 출발지/도착지를 Kakao Local API로 좌표화하고 Kakao Mobility 자동차 길찾기 API로 경로 후보를 받아, 사용자가 선택한 경로의 `vertexes`를 버퍼 영역으로 저장 | 제외 |
| 특정 대중교통 노선 기반 | 중간~낮음 | 서울 공공데이터의 버스 노선/경유정류소/지하철역 정보를 활용해 노선 주변을 생활권으로 저장. 카카오맵 수준의 통합 대중교통 경로 탐색은 공개 API만으로는 제한적 | 제외 |
| 특정 행정구역 기반 | 중간 | Kakao Local API의 행정구역 변환/주소검색으로 구·동 이름을 정규화한다. 정확한 포함 판정은 행정구역 polygon 데이터가 필요하므로 후속 검증 | 제외 |

### 9.1 특정 위치 기반

사용 예:

```text
집을 생활권으로 추가해줘. 주소는 서울시 중구 세종대로 110이고 반경은 1km.
```

처리:

1. 주소를 Kakao Local API로 좌표 변환한다.
2. 사용자가 붙인 이름(`집`, `회사`, `학교`)과 반경을 저장한다.
3. 교통 이슈 좌표가 원 안에 들어오면 매칭한다.

이 방식은 공개 API만으로 가능하며 공모전 MVP의 기본 방식이다.

### 9.2 특정 경로 기반

사용 예:

```text
집에서 학교까지 가는 경로를 생활권으로 추가해줘.
```

처리 방향:

1. 출발지/도착지를 좌표로 변환한다.
2. Kakao Mobility 자동차 길찾기 API로 경로를 조회한다.
3. `alternatives=true`, `summary=false`로 가능한 경로 후보와 상세 `roads.vertexes`를 받는다.
4. 사용자에게 후보를 요약해서 보여준다.
5. 사용자가 선택한 경로 polyline 주변을 일정 반경으로 버퍼링해 생활권으로 저장한다.

제약:

- 이 기능은 자동차 경로 중심이다.
- PlayMCP 채팅만으로 “지도에서 경로 선택” UX를 만들기는 제한적이다.
- 지도 기반 선택 UI가 필요하면 별도 웹 화면 또는 widget이 필요하다.

### 9.3 특정 대중교통 노선 기반

사용 예:

```text
272번 버스 노선을 생활권으로 추가해줘.
2호선 강남역-잠실역 구간을 생활권으로 추가해줘.
```

가능한 공개 데이터 후보:

- 서울시 버스 노선 정보 조회
- 서울시 버스노선별 경유정류소 목록정보
- 서울시 버스노선경로 목록정보
- 서울교통공사 노선별 지하철역 정보
- 서울시 지하철 실시간 도착정보

처리 방향:

1. 사용자가 노선 번호, 지하철 호선, 구간을 입력한다.
2. 노선/정류장/역 목록을 조회한다.
3. 노선 좌표 또는 정류장/역 좌표를 선으로 연결한다.
4. 해당 선 주변을 버퍼링해 생활권으로 저장한다.

제약:

- 공개 데이터만으로 카카오맵 앱과 동일한 대중교통 경로 탐색 UX를 보장하기 어렵다.
- “현재 내 출발지에서 목적지까지 최적 대중교통 경로”는 공모전 MVP에서 제외한다.

### 9.4 특정 행정구역 기반

사용 예:

```text
마포구를 생활권으로 추가해줘.
성수동을 생활권으로 추가해줘.
```

처리 방향:

1. 구/동 이름을 Kakao Local API나 서울 행정 데이터로 정규화한다.
2. 단순 버전은 행정구역명 매칭으로 시작한다.
3. 정확한 버전은 행정구역 경계 polygon을 확보해 point-in-polygon으로 판정한다.

제약:

- `구`, `동`은 행정동/법정동 차이가 있어 사용자에게 선택을 확인해야 한다.
- 정확한 경계 판정은 별도 경계 데이터 검증이 필요하다.

## 10. 시상 이후 카카오 협업 후보

공개 API만으로는 카카오맵 앱 사용자 계정에 저장된 집/회사/즐겨찾기 장소를 자동 조회할 수 있다고 보기 어렵다. 다만 시상 이후 카카오와 협업할 수 있다면 다음 기능을 확장 후보로 남긴다.

협업 후보:

- 카카오맵에 저장된 `집`, `회사`, 즐겨찾기 장소를 사용자 동의 후 가져오기
- 카카오맵 최근 검색/최근 길찾기 목적지를 사용자 동의 후 생활권 후보로 제안
- 카카오맵에서 선택한 경로를 PlayMCP 생활권으로 내보내기
- 카카오맵 대중교통 경로 후보를 MCP 서버가 받아 생활권으로 저장
- 카카오맵/카카오톡 알림 UX를 연결해 “등교/출근 전 교통 위험 알림”을 자동화

주의:

- 이 기능들은 공개 API만으로 MVP에 포함하지 않는다.
- 사용자 동의, 개인정보 제3자 제공, 저장 위치/경로 데이터의 보관 기간을 별도 설계해야 한다.

## 11. 남은 개발 작업

현재 로컬 구현은 단일 사용자 베타 기준으로 동작한다. ChatGPT for Kakao에서 공개 사용자용으로 쓰려면 다음 작업이 남아 있다.

### 11.1 PlayMCP 호환성 확정

목표: PlayMCP/Kakao Tools가 우리 서버를 안정적으로 발견하고 호출하도록 만든다.

작업:

1. MCP Inspector로 `initialize`, `tools/list`, `tools/call`을 검증한다.
2. Streamable HTTP 규격에 맞춰 단일 MCP endpoint를 명확히 둔다.
3. POST 요청의 `Accept` 처리, JSON-RPC batch 또는 notification 처리 범위를 점검한다.
4. 로컬 서버의 `GET /health`, OAuth route와 MCP endpoint가 충돌하지 않도록 정리한다.
5. 배포 직후 환경변수, OAuth callback, SQLite 접근 가능 여부를 `/ready`로 점검한다.
6. `Origin` 검증 또는 배포 환경의 허용 호스트 정책을 추가한다.

완료 기준:

- MCP Inspector에서 현재 노출 tool이 모두 보인다.
- 제출 전 tool 수가 PlayMCP 허용 범위에 들어가는지 확인한다.
- `/ready`가 비밀값 없이 boolean 점검 결과만 반환하고, 정상 배포에서 `status: ok`를 반환한다.
- 모든 tool schema와 annotations가 오류 없이 표시된다.
- `check_traffic_issues` 같은 외부 API 호출 tool도 실패 시 짧은 사용자 메시지를 반환한다.

### 11.2 사용자별 저장소 분리

목표: ChatGPT for Kakao의 여러 사용자가 같은 서버를 써도 생활권, 예약, OAuth 토큰이 섞이지 않게 한다.

작업:

1. PlayMCP 요청에서 사용할 수 있는 사용자 식별 컨텍스트를 확인한다.
2. 확정 전까지는 `X-PlayMCP-User-Id` 같은 커스텀 헤더 후보를 격리 계층으로 둔다.
3. 실제 헤더명이 다르면 `PLAYMCP_USER_ID_HEADERS`에 쉼표 구분으로 추가한다.
4. SQLite 테이블에 `user_id` 컬럼을 추가한다.
5. `alert_areas`, `scheduled_alerts`, `oauth_tokens`의 기본 키를 `(user_id, label)` 또는 `(user_id, id)` 기준으로 바꾼다.
6. OAuth `state`에 user/session 바인딩 값을 넣어 callback에서 올바른 사용자 토큰으로 저장한다.
7. 테스트에서 사용자 A/B의 생활권과 토큰이 섞이지 않는지 확인한다.

완료 기준:

- 사용자 A가 등록한 `출근길`은 사용자 B의 `list_alert_areas`에 보이지 않는다.
- 사용자 B의 OAuth 토큰으로 사용자 A 알림이 발송되지 않는다.
- 예약 알림 실행기가 예약별 `user_id`를 기준으로 해당 사용자의 토큰만 사용한다.

### 11.3 OAuth 배포 전환

목표: 로컬 OAuth가 아니라 배포 Endpoint 기준으로 사용자 동의와 토큰 갱신이 동작하게 한다.

작업:

1. PlayMCP in KC Endpoint URL을 받은 뒤 Kakao Developers에 배포 Redirect URI를 등록한다.
2. `.env`의 `KAKAO_REDIRECT_URI`를 배포 URL로 설정한다.
3. `KAKAO_CLIENT_SECRET`이 ON이면 배포 환경변수에도 함께 설정한다.
4. OAuth 시작 URL을 tool 결과 또는 설정 안내에서 사용자에게 제공한다.
5. 토큰 갱신 실패 시 재연결 안내를 반환한다.

완료 기준:

- 배포 URL에서 `/auth/kakao/start`가 정상적으로 Kakao Login으로 이동한다.
- callback 후 사용자별 `oauth_tokens`에 access token과 refresh token이 저장된다.
- `send_self_alert`가 배포 환경에서도 나와의 채팅방으로 1건 전송된다.

### 11.4 ChatGPT for Kakao 대화 테스트

목표: 사용자가 카카오톡 안에서 자연어로 서비스를 즉시 사용할 수 있는지 확인한다.

테스트 스크립트:

| 테스트 | 사용자 발화 | 기대 tool |
| --- | --- | --- |
| 생활권 등록 | `출근길을 서울시청 반경 1km로 등록해줘.` | `set_alert_area` |
| 목록 확인 | `내 교통 알림 영역 보여줘.` | `list_alert_areas` |
| 이슈 확인 | `출근길 주변에 지금 통제나 사고 있어?` | `check_traffic_issues` |
| 발송 전 확인 | `이 내용을 보내도 되는지 확인해줘.` | `send_self_alert` (`dry_run=true`) |
| 즉시 발송 | `카카오톡으로 나에게 보내줘.` | `send_self_alert` (`dry_run=false`) |
| 예약 등록 | `평일 아침 7시에 출근길 교통 이슈 알려줘.` | `set_scheduled_alert` |
| 예약 조회 | `예약 알림 목록 보여줘.` | `list_scheduled_alerts` |
| 예약 삭제 | `출근길 아침 알림 삭제해줘.` | `delete_scheduled_alert` |

완료 기준:

- 로컬에서는 `python3 scripts/local_beta_flow.py`로 등록, 조회, 이슈 확인, dry-run 발송 흐름을 한 번에 점검한다.
- 사용자가 tool 이름을 몰라도 자연어 발화가 올바른 tool 호출로 이어진다.
- 인자가 부족하면 ChatGPT for Kakao가 주소, 반경, 시간 같은 필요한 값만 추가 질문한다.
- tool 응답은 원본 API JSON/XML을 노출하지 않고 사용자가 이해할 수 있는 한국어 요약으로 표시된다.

### 11.5 예약 알림 운영 안정화

목표: 예약 알림이 배포 환경에서 누락되거나 중복 발송되지 않게 한다.

작업:

1. PlayMCP in KC가 장시간 백그라운드 스레드를 유지하는지 확인한다.
2. 유지가 불안정하면 `TASK_RUN_SECRET`으로 보호된 `POST /tasks/run-due-alerts` 내부 endpoint와 외부 cron 방식으로 바꾼다.
3. `last_sent_date` 기준 중복 발송 방지를 유지한다.
4. Seoul Open API 장애나 Kakao 전송 실패 시 다음 실행을 막지 않는다.

완료 기준:

- 같은 예약이 같은 날짜에 두 번 발송되지 않는다.
- 서버 재시작 후에도 SQLite의 예약이 유지된다.
- API 장애 시 사용자에게 짧은 실패 메시지를 남기고 민감정보는 로그에 출력하지 않는다.

### 11.6 제출 전 문서와 정책 정리

목표: 심사자가 서비스 목적, 데이터 출처, 개인정보 처리, 실행 방법을 바로 확인할 수 있게 한다.

작업:

1. `README.md` 작성
2. `.env.example` 최신화
3. 개인정보 처리 요약 작성
4. 데이터 출처와 라이선스 표기
5. 베타 테스트 스크립트 작성
6. 로컬 제출 전 preflight 스크립트 작성
7. 반려 대응을 위한 known limitations 정리

완료 기준:

- 저장소 첫 화면에서 서비스 목적과 실행 방법을 바로 이해할 수 있다.
- `python3 scripts/preflight.py`로 컴파일, 단위 테스트, readiness, MCP smoke, 로컬 베타 흐름을 한 번에 확인할 수 있다.
- 실제 키나 토큰은 어디에도 커밋되지 않는다.
- 서울시 공공데이터 출처와 Kakao API 사용 범위가 명시되어 있다.

## 12. 최종 제출 산출물 형식

### 12.1 Git 저장소

필수 파일:

```text
README.md
Dockerfile
.dockerignore
.gitignore
.env.example
server.py
test_server.py
docs/agentic_player_10_submission_plan.md
docs/seoul_traffic_guard_feature_spec.md
docs/privacy_and_data_sources.md
```

`README.md` 필수 목차:

```text
# Seoul Traffic Guard
## What it does
## User flow in ChatGPT for Kakao
## Tools
## Required environment variables
## Local run
## Docker run
## OAuth setup
## PlayMCP deployment
## Data sources and attribution
## Privacy and security notes
## Known limitations
```

### 12.2 PlayMCP in KC 배포 입력값

Git 소스 빌드 기준:

| 항목 | 값 |
| --- | --- |
| Repository URL | 제출용 Git 저장소 URL |
| Branch/Ref | 심사용 고정 브랜치 또는 태그 |
| Build type | Git source build |
| Dockerfile path | `Dockerfile` |
| Port | `8000` |
| Health check | `/health` |
| Environment variables | `SEOUL_OPENAPI_KEY`, `KAKAO_REST_API_KEY`, `KAKAO_CLIENT_SECRET`, `KAKAO_REDIRECT_URI`, `PLAYMCP_DB_PATH`, `ALLOWED_ORIGINS`, `TASK_RUN_SECRET` |

컨테이너 이미지 대안:

| 항목 | 값 |
| --- | --- |
| Platform | `linux/amd64` |
| Image | 레지스트리 이미지명 |
| Tag | 제출용 고정 태그 |
| Port | `8000` |
| Health check | `/health` |

### 12.3 PlayMCP 개발자 콘솔 등록 정보

| 항목 | 작성안 |
| --- | --- |
| MCP 서버명 | `Seoul Traffic Guard` |
| 한글 표시명 | `서울 교통 이슈 알리미` |
| 한 줄 소개 | `카카오톡의 ChatGPT for Kakao에서 출근·등교 전 서울 교통 통제와 사고를 확인하고 알림으로 받을 수 있는 MCP 서버` |
| 상세 설명 | `사용자가 생활권과 예약 시간을 자연어로 등록하면 서울시 실시간 돌발 교통정보를 조회해 반경 내 이슈를 요약하고, OAuth 동의 후 본인 카카오톡 나와의 채팅방으로 알림을 보냅니다.` |
| 카테고리 | 교통, 생활, 생산성 중 콘솔 옵션에 맞춰 선택 |
| Endpoint URL | PlayMCP in KC에서 발급된 MCP endpoint |
| 공개 범위 | 테스트 중 `나에게만 공개`, 승인 후 `전체 공개` |

Tool 설명은 영어를 기본으로 유지하되, 사용자에게 보이는 응답은 한국어로 둔다. 서버명과 tool name에는 `kakao` 문자열을 넣지 않는다.

### 12.4 공모전 예선 참여 폼 준비물

폼 입력 전 준비:

1. 승인된 MCP 상세 페이지 URL
2. 팀명/대표자/연락처
3. 서비스명: `Seoul Traffic Guard / 서울 교통 이슈 알리미`
4. 서비스 한 줄 설명
5. 사용 시나리오 3개
6. 주요 기술 구성
7. 개인정보 및 데이터 출처 설명
8. 시연 화면 또는 시연 문구

제출용 소개문 초안:

```text
서울 교통 이슈 알리미는 카카오톡의 ChatGPT for Kakao 안에서 자연어로 출근길·등교길 생활권을 등록하고, 서울시 실시간 돌발 교통정보를 확인해 지연 위험을 미리 알려주는 MCP 서버입니다. 사용자는 "평일 아침 7시에 출근길 교통 이슈 알려줘"처럼 말하면 예약 알림을 만들 수 있고, 서버는 서울시 교통 데이터를 조회해 반경 내 사고·공사·통제 정보를 요약한 뒤 사용자 동의하에 본인 카카오톡으로 알림을 보냅니다.
```

### 12.5 시연 스크립트

1분 시연 흐름:

```text
1. 카카오톡에서 ChatGPT for Kakao를 연다.
2. "출근길을 서울시청 반경 1km로 등록해줘"라고 입력한다.
3. 등록 완료 응답을 확인한다.
4. "출근길 주변에 지금 교통 이슈 있어?"라고 입력한다.
5. 서울시 실시간 돌발 정보 요약을 확인한다.
6. "평일 아침 7시에 출근길 교통 이슈 알려줘"라고 입력한다.
7. 예약 등록 응답을 확인한다.
8. "테스트 알림을 나에게 보내줘"라고 입력한다.
9. 카카오톡 나와의 채팅방에 알림이 도착한 것을 확인한다.
```

## 13. 구현 일정

현재 날짜 기준 내부 목표 일정:

| 날짜 | 목표 | 산출물 |
| --- | --- | --- |
| 06-19 ~ 06-20 | 개발 전 준비 | Kakao Developers 앱, 서울 Open API 키, `.env.example`, API 샘플 호출 |
| 06-21 | 데이터 스파이크 | `AccInfo`, `TrafficInfo`, 좌표 변환, 위치 기반 생활권 검증 |
| 06-22 | 로컬 MCP MVP | 초기 8개 툴, SQLite 저장소, OAuth 나에게 보내기, Docker 빌드 |
| 06-23 | 사용자별 저장소 분리 | `user_id` 기반 생활권/예약/OAuth 분리 |
| 06-24 | MCP Inspector 검증 | Streamable HTTP, tool schema, annotations 확인 |
| 06-25 | README/제출 문서 | Git 소스 빌드, OAuth, 개인정보, 데이터 출처 문서 |
| 06-26 | PlayMCP in KC 배포 | Endpoint URL 확보, 배포 Redirect URI 등록 |
| 06-27 ~ 06-30 | PlayMCP 임시 등록/ChatGPT for Kakao 테스트 | 자연어 tool 호출, 알림 발송, 예약 흐름 검증 |
| 07-01 ~ 07-03 | 심사 요청 | 전체 제출 후보 확정, 시연 스크립트 준비 |
| 07-04 ~ 07-10 | 반려 대응 버퍼 | 수정 후 재심사 |
| 07-11 ~ 07-14 | 전체 공개 및 예선 접수 | 비즈폼 최종 제출 |

## 14. 배포 방식 선택

1차 선택: **Git 소스 빌드**

- PlayMCP in KC에서 Git 저장소 URL과 브랜치/ref를 입력한다.
- 저장소 루트 또는 지정 경로에 Dockerfile이 필요하다.
- public 저장소면 PAT 없이 진행 가능하다.
- 서버가 Active가 되면 상세 화면의 Endpoint URL을 PlayMCP 등록에 사용한다.

대안: **컨테이너 이미지 등록**

- 이미지를 레지스트리에 올린 뒤 Registry host, image name, tag를 입력한다.
- Apple Silicon Mac에서 빌드할 경우 반드시 `docker build --platform linux/amd64 ...`를 사용한다.
- arm64 이미지는 서버 활성화에 실패할 수 있다.

## 15. 심사용 품질 기준

정확성:

- `AccInfo` 원본 시간과 유형 코드를 사람이 읽을 수 있는 한국어로 변환한다.
- 좌표 변환 실패 시 해당 이슈는 매칭에서 제외하고 오류로 폭발시키지 않는다.
- 반경 매칭은 Haversine 거리 계산으로 단순하게 처리한다.

응답 품질:

- 원본 XML/JSON 전체를 반환하지 않는다.
- 사용자 질문에는 “영향 지역, 이슈 유형, 내용, 예정 종료시각, 권장 행동”만 요약한다.
- 데이터가 없으면 “등록 지역 주변 확인된 교통 이슈 없음”처럼 짧게 답한다.

보안/개인정보:

- 주소 원문은 기본 저장하지 않고 좌표와 label만 저장한다.
- OAuth token은 평문 로그 금지.
- `TOKEN_ENCRYPTION_KEY` 설정 시 OAuth token은 SQLite에 암호문으로 저장한다.
- API key, access token, refresh token은 마스킹한다.
- MCP 요청 body, JSON-RPC batch, 사용자별 호출량, 카카오톡 중복 발송을 제한한다.
- PlayMCP 연동 시 개인정보 제3자 제공 동의 문구를 준비한다.

성능:

- `AccMainCode`, `AccSubCode`는 서버 시작 시 캐시한다.
- `AccInfo`는 짧은 TTL 캐시를 둔다.
- `TrafficInfo`는 매칭된 이슈의 `LINK_ID`에 대해서만 선택 호출한다.

## 16. 제출 전 체크리스트

- [ ] MCP 서버가 Streamable HTTP로 동작한다.
- [ ] 개발 전 준비 단계의 키/앱/권한 확인이 끝났다.
- [ ] MCP Inspector에서 초기화, tools/list, tools/call이 통과한다.
- [ ] 모든 tool에 `annotations`가 있다.
- [ ] tool name과 server name에 `kakao`가 없다.
- [ ] Tool count is 10 and stays within the PlayMCP recommended 3-10 range.
- [ ] 사용자별 생활권, 예약, OAuth token이 분리된다.
- [ ] 배포 환경에 `PLAYMCP_USER_ID_HEADERS`, `REQUIRE_USER_ID_HEADER`, `TOKEN_ENCRYPTION_KEY`가 설정됐다.
- [ ] 배포 Redirect URI가 Kakao Developers에 등록됐다.
- [ ] ChatGPT for Kakao 자연어 발화가 의도한 tool 호출로 이어진다.
- [ ] 나에게 보내기 알림이 사용자별 OAuth 토큰으로 동작한다.
- [ ] 예약 알림이 중복 없이 발송된다.
- [ ] 과도한 요청, 큰 request body, 큰 JSON-RPC batch, 중복 카카오톡 발송이 차단된다.
- [ ] 배포 환경에서 백그라운드 스레드가 불안정할 경우 `/tasks/run-due-alerts`와 `TASK_RUN_SECRET` 기반 외부 스케줄 실행이 가능하다.
- [ ] 평균 응답 100ms 목표, p99 3초 이내를 확인했다.
- [ ] PlayMCP in KC에서 Endpoint URL을 확보했다.
- [ ] PlayMCP 임시 등록 후 “정보 불러오기”가 성공했다.
- [ ] PlayMCP 채팅에서 생활권 등록/조회/알림 미리보기가 동작한다.
- [ ] 카카오톡의 ChatGPT for Kakao에서 1분 시연 스크립트가 통과한다.
- [ ] README에 실행 방법, OAuth 설정, 데이터 출처, 개인정보 처리 요약이 있다.
- [ ] 심사 승인 후 공개 상태를 전체 공개로 바꿨다.
- [ ] 공모전 페이지에서 예선 참여 폼을 제출했다.

## 17. 참고 출처

- Agentic Player 10 공모전 페이지: https://b.kakao.com/views/PlayMCP/AGENTIC_PlAYER_10
- Agentic Player 10 공모전 참가 가이드: https://app.notion.com/p/3749b97b4888803bb90bef3ddbcfbcfb
- PlayMCP 서버 개발가이드: https://app.notion.com/p/PlayMCP-2d89b97b4888808a9e1dc17a13e70187
- MCP Streamable HTTP 스펙: https://modelcontextprotocol.io/specification/2025-03-26/basic/transports#streamable-http
- MCP Authorization 스펙: https://modelcontextprotocol.io/specification/2025-03-26/basic/authorization#authorization-flow
- MCP Inspector: https://modelcontextprotocol.io/docs/tools/inspector
- Kakao API 시작하기: https://developers.kakao.com/docs/latest/ko/tutorial/start
- Kakao Login 설정하기: https://developers.kakao.com/docs/latest/ko/kakaologin/prerequisite
- 서울 Open API 이용가이드: https://data.seoul.go.kr/together/guide/useGuide.do
- 서울시 실시간 돌발 정보: https://data.seoul.go.kr/dataList/OA-13315/A/1/datasetView.do
- Kakao Mobility 자동차 길찾기 API: https://developers.kakaomobility.com/guide/navi-api/directions.html
- Kakao Local REST API: https://developers.kakao.com/docs/latest/ko/local/dev-guide
- KakaoTalk Message REST API: https://developers.kakao.com/docs/latest/ko/kakaotalk-message/rest-api
