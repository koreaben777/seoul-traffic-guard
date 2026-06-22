# Seoul Traffic Guard 기능 명세

작성일: 2026-06-19

## 1. 목적

`Seoul Traffic Guard`는 서울시 실시간 돌발 교통정보를 사용자가 등록한 생활권과 비교해, 사고·공사·통제·행사성 교통 이슈를 짧게 확인하고 필요하면 본인 카카오톡으로 알림을 보내는 Remote MCP 서버다.

핵심 사용 시나리오:

```text
학교 주변 교통 이슈 확인해줘.
집 근처에 오늘 아침 통제나 사고 있어?
이 내용을 나에게 알림으로 보내줘.
평일 아침 7시에 출근길 교통 이슈를 자동으로 알려줘.
```

## 2. MVP 범위

MVP는 다음 기능만 포함한다.

1. 사용자가 생활권을 등록한다.
2. 등록된 생활권 목록을 조회한다.
3. 서울시 실시간 돌발 교통정보를 조회한다.
4. 교통 이슈가 생활권 반경 안에 있는지 판정한다.
5. 발송 전 알림 문구를 미리 본다.
6. 사용자 OAuth 동의 후 본인 카카오톡 “나와의 채팅방”으로 알림을 보낸다.
7. 지정한 요일과 시간에 등록 생활권의 교통 이슈를 자동으로 확인해 알림을 보낸다.

MVP에서 제외한다.

- 친구 또는 단체방 메시지 발송
- 카카오톡 대화방, 메시지, 첨부파일 읽기
- 카카오맵 저장 장소, 최근 검색, 최근 길찾기 자동 조회
- 대중교통 최적 경로 탐색
- 경로 polyline 기반 생활권
- 행정구역 polygon 기반 판정

## 3. 데이터 소스

### 서울 열린데이터광장

| 용도 | 서비스명 | MVP 사용 |
| --- | --- | --- |
| 실시간 돌발 교통 이슈 | `AccInfo` | 필수 |
| 돌발 유형 코드 | `AccMainCode` | 가능하면 캐시 |
| 돌발 세부 유형 코드 | `AccSubCode` | 가능하면 캐시 |
| 도로 소통 정보 | `TrafficInfo` | 후순위 |
| 권역 정보 | `RegionInfo` | 후순위 |

`AccInfo`는 MVP의 주 데이터다. 응답 전체를 그대로 반환하지 않고, 사용자에게 필요한 필드만 요약한다.

### Kakao API

| 용도 | API |
| --- | --- |
| 주소를 좌표로 변환 | Local address search |
| 좌표를 행정구역으로 변환 | Local coord2regioncode |
| OAuth 로그인 | Kakao Login |
| 본인 채팅방 알림 | KakaoTalk Message “send to me” |

Kakao API 이름은 내부 구현과 환경 변수에만 사용한다. MCP 서버명과 tool name에는 `kakao`를 넣지 않는다.

## 4. 생활권 모델

MVP의 생활권은 `point_circle` 하나만 사용한다.

```json
{
  "id": "area_001",
  "label": "school",
  "address": "서울시 중구 세종대로 110",
  "lat": 37.5665,
  "lng": 126.9780,
  "radius_m": 1000,
  "created_at": "2026-06-19T00:00:00Z"
}
```

저장 원칙:

- 사용자가 입력한 label은 저장한다.
- 주소 원문은 MVP 디버깅 편의를 위해 저장할 수 있지만, 배포 전에는 좌표와 label 중심 저장으로 줄인다.
- API 키, OAuth token, refresh token은 로그에 남기지 않는다.
- 초기 구현은 파일 또는 SQLite 중 더 단순한 쪽을 사용한다. 배포 전 지속 저장이 필요하면 SQLite로 고정한다.

## 5. 교통 이슈 모델

서버 내부 정규화 형태:

```json
{
  "id": "acc_001",
  "type": "공사",
  "summary": "세종대로 일부 차로 통제",
  "location": "서울 중구 세종대로",
  "lat": 37.566,
  "lng": 126.978,
  "started_at": "2026-06-19T08:10:00+09:00",
  "expected_end_at": "2026-06-19T10:00:00+09:00",
  "source": "Seoul AccInfo"
}
```

응답 원칙:

- 원본 JSON/XML 전체를 반환하지 않는다.
- 사용자에게는 영향 지역, 이슈 유형, 요약, 예정 종료시각, 권장 행동만 보여준다.
- 좌표가 없거나 변환 실패한 이슈는 매칭에서 제외한다.
- 매칭 결과가 없으면 짧게 답한다.

```text
등록 지역 주변 확인된 교통 이슈 없음
```

## 6. 반경 매칭

MVP 판정 방식은 Haversine 거리 계산이다.

입력:

- 생활권 중심 좌표
- 교통 이슈 좌표
- 생활권 반경 m

판정:

```text
distance_m <= radius_m 이면 매칭
```

정밀한 도로망, 실제 경로 우회 시간, 대중교통 영향도는 MVP에서 계산하지 않는다.

## 7. 예약 알림 모델

예약 알림은 특정 생활권 label을 기준으로 동작한다. 예를 들어 `출근길`은 먼저 `set_alert_area`로 등록된 생활권이어야 한다.

```json
{
  "id": "schedule_001",
  "label": "commute",
  "area_label": "출근길",
  "weekdays": ["mon", "tue", "wed", "thu", "fri"],
  "time": "07:00",
  "timezone": "Asia/Seoul",
  "target_day": "today",
  "send_policy": "only_if_issues",
  "enabled": true,
  "last_sent_date": null
}
```

필드 의미:

| 필드 | 의미 |
| --- | --- |
| `label` | 예약 알림 이름 |
| `area_label` | 확인할 생활권 label |
| `weekdays` | 실행 요일 |
| `time` | 24시간제 `HH:MM` |
| `timezone` | 기본값 `Asia/Seoul` |
| `target_day` | 조회 대상 날짜, `today` 또는 `tomorrow` |
| `send_policy` | `only_if_issues` 또는 `always` |
| `enabled` | 예약 활성 여부 |
| `last_sent_date` | 같은 날짜 중복 발송 방지용 |

MVP 동작:

1. 서버가 1분 단위로 현재 시각과 예약을 비교한다.
2. 실행 시간이 된 예약만 처리한다.
3. 해당 생활권의 교통 이슈를 조회한다.
4. `send_policy`가 `only_if_issues`이면 매칭된 이슈가 있을 때만 발송한다.
5. `send_policy`가 `always`이면 이슈가 없어도 “확인된 교통 이슈 없음” 메시지를 보낸다.
6. 같은 예약은 같은 날짜에 한 번만 발송한다.

운영 제약:

- 서버 프로세스가 꺼져 있으면 예약 알림도 실행되지 않는다.
- PlayMCP in KC 배포 환경에서 장시간 백그라운드 실행이 불안정하면 외부 cron이 `TASK_RUN_SECRET`으로 보호된 `POST /tasks/run-due-alerts` 내부 엔드포인트를 호출한다.
- MVP는 사용자가 예약을 만든 뒤 자동 알림이 발송되는지만 검증한다. 복잡한 휴일 캘린더, 임시 정지 기간, 반복 간격 커스텀은 제외한다.

## 8. MCP Tool 정의

### 8.1 `set_alert_area`

생활권을 등록한다.

입력:

```json
{
  "label": "school",
  "address": "서울시 중구 세종대로 110",
  "radius_m": 1000
}
```

동작:

1. label, address를 검증한다.
2. Kakao Local API로 주소를 좌표화한다.
3. 좌표와 반경을 저장한다.
4. 같은 label이 이미 있으면 덮어쓴다.

출력 예:

```text
school 생활권을 등록했습니다. 반경 1000m 기준으로 교통 이슈를 확인합니다.
```

Annotation:

```json
{
  "readOnlyHint": false,
  "destructiveHint": false,
  "openWorldHint": true,
  "idempotentHint": true
}
```

### 8.2 `list_alert_areas`

등록된 생활권을 조회한다.

입력:

```json
{}
```

출력 예:

```text
- school: 서울시 중구 세종대로 110, 반경 1000m
- work: 서울시 강남구 테헤란로 123, 반경 800m
```

등록된 생활권이 없으면:

```text
등록된 생활권이 없습니다.
```

Annotation:

```json
{
  "readOnlyHint": true,
  "destructiveHint": false,
  "openWorldHint": false,
  "idempotentHint": true
}
```

### 8.3 `check_traffic_issues`

생활권 주변 교통 이슈를 조회한다.

입력:

```json
{
  "label": "school"
}
```

`label`이 없으면 모든 생활권을 확인한다.

동작:

1. 서울 `AccInfo`를 조회한다.
2. 필요한 필드만 정규화한다.
3. 좌표가 있는 이슈를 생활권 반경과 비교한다.
4. 매칭 결과를 중요도순으로 최대 5개 반환한다.

출력 예:

```text
school 주변 교통 이슈 1건

1. 공사 - 세종대로 일부 차로 통제
   위치: 서울 중구 세종대로
   예상 종료: 10:00
   권장 행동: 출발 전 우회 경로를 확인하세요.
```

Annotation:

```json
{
  "readOnlyHint": true,
  "destructiveHint": false,
  "openWorldHint": true,
  "idempotentHint": true
}
```

### 8.4 `preview_alert_message`

알림 발송 전 메시지를 미리 만든다.

입력:

```json
{
  "label": "school",
  "issue_summary": "세종대로 일부 차로 통제, 10:00 종료 예정"
}
```

출력 예:

```text
[서울 교통 이슈 알리미]
school 주변 교통 이슈가 있습니다.
세종대로 일부 차로 통제, 10:00 종료 예정
출발 전 우회 경로를 확인하세요.
```

Annotation:

```json
{
  "readOnlyHint": true,
  "destructiveHint": false,
  "openWorldHint": false,
  "idempotentHint": true
}
```

### 8.5 `send_self_alert`

사용자 본인 카카오톡으로 알림을 보낸다.

입력:

```json
{
  "message": "[서울 교통 이슈 알리미] school 주변 교통 이슈가 있습니다.",
  "dry_run": false
}
```

동작:

1. OAuth access token이 있는지 확인한다.
2. `talk_message` 동의가 없으면 발송하지 않는다.
3. KakaoTalk Message API로 나에게 보내기를 호출한다.
4. 성공 여부만 짧게 반환한다.

출력 예:

```text
나와의 채팅방으로 알림을 보냈습니다.
```

실패 예:

```text
카카오 메시지 동의가 필요합니다. 먼저 로그인 및 동의를 완료하세요.
```

Annotation:

```json
{
  "readOnlyHint": false,
  "destructiveHint": false,
  "openWorldHint": true,
  "idempotentHint": false
}
```

### 8.6 `set_scheduled_alert`

예약 알림을 생성하거나 같은 label의 예약을 갱신한다.

입력:

```json
{
  "label": "weekday_morning_commute",
  "area_label": "출근길",
  "weekdays": ["mon", "tue", "wed", "thu", "fri"],
  "time": "07:00",
  "target_day": "today",
  "send_policy": "only_if_issues"
}
```

동작:

1. `area_label`에 해당하는 생활권이 있는지 확인한다.
2. 요일과 시간을 검증한다.
3. 예약 정보를 저장한다.
4. 같은 `label`이 있으면 덮어쓴다.

출력 예:

```text
weekday_morning_commute 예약을 등록했습니다. 평일 07:00에 출근길 주변 교통 이슈를 확인합니다.
```

Annotation:

```json
{
  "readOnlyHint": false,
  "destructiveHint": false,
  "openWorldHint": false,
  "idempotentHint": true
}
```

### 8.7 `list_scheduled_alerts`

등록된 예약 알림을 조회한다.

입력:

```json
{}
```

출력 예:

```text
- weekday_morning_commute: 출근길, mon-fri 07:00, today, 이슈가 있을 때만 발송
```

Annotation:

```json
{
  "readOnlyHint": true,
  "destructiveHint": false,
  "openWorldHint": false,
  "idempotentHint": true
}
```

### 8.8 `delete_scheduled_alert`

예약 알림을 삭제한다.

입력:

```json
{
  "label": "weekday_morning_commute"
}
```

출력 예:

```text
weekday_morning_commute 예약을 삭제했습니다.
```

Annotation:

```json
{
  "readOnlyHint": false,
  "destructiveHint": true,
  "openWorldHint": false,
  "idempotentHint": true
}
```

## 9. OAuth 흐름

로컬 개발 Redirect URI:

```text
http://localhost:8000/auth/kakao/callback
```

필요 환경 변수:

```env
KAKAO_REST_API_KEY=
KAKAO_CLIENT_SECRET=
KAKAO_REDIRECT_URI=
```

MVP 인증 흐름:

1. 사용자가 로그인 URL을 연다.
2. Kakao Login에서 `talk_message` 선택 동의를 받는다.
3. callback에서 authorization code를 받는다.
4. access token과 refresh token을 서버 저장소에 저장한다.
5. `send_self_alert` 호출 시 access token을 사용한다.

토큰 저장은 초기에는 단일 사용자 로컬 개발 기준으로 시작한다. 다중 사용자 저장소는 PlayMCP 사용자 식별 방식이 확정된 뒤 붙인다.

## 10. 에러 처리

| 상황 | 처리 |
| --- | --- |
| API 키 누락 | 서버 시작 또는 tool 호출 시 짧은 설정 오류 반환 |
| 주소 검색 실패 | 생활권을 저장하지 않고 주소 확인 요청 |
| 서울 API 장애 | “서울 교통정보 조회에 실패했습니다” 반환 |
| 좌표 없는 이슈 | 해당 이슈만 매칭 제외 |
| 등록 생활권 없음 | 생활권 등록 안내 |
| OAuth token 없음 | 로그인 및 동의 필요 안내 |
| 메시지 발송 실패 | 발송 실패 사유를 짧게 반환 |
| 예약 생활권 없음 | 예약을 저장하지 않고 생활권 등록 안내 |
| 예약 시간 형식 오류 | `HH:MM` 형식 안내 |
| 예약 발송 중복 | 같은 날짜에는 재발송하지 않음 |

민감정보는 에러 메시지에 포함하지 않는다.

## 11. 보안 및 개인정보

- `.env`는 저장소에 커밋하지 않는다.
- API 키, client secret, access token, refresh token은 로그에 출력하지 않는다.
- 사용자의 주소 원문 저장은 최소화한다.
- 알림 발송은 사용자가 명시적으로 호출한 `send_self_alert` 또는 사용자가 등록한 예약 알림에서만 수행한다.
- 친구/단체방 발송은 구현하지 않는다.
- PlayMCP 제출 전 개인정보 처리 문구와 데이터 출처 표기를 준비한다.

## 12. 완료 기준

개발 1차 완료 기준:

- MCP Inspector에서 `initialize`, `tools/list`, `tools/call`이 통과한다.
- 8개 tool이 모두 노출된다.
- 모든 tool에 `annotations`가 있다.
- `set_alert_area`가 실제 주소를 좌표화해 저장한다.
- `check_traffic_issues`가 실제 `AccInfo`를 조회해 반경 매칭한다.
- 매칭 결과가 없을 때 짧은 정상 응답을 반환한다.
- `preview_alert_message`가 발송 전 문구를 만든다.
- `send_self_alert`가 OAuth 동의 후 나에게 보내기를 수행한다.
- `set_scheduled_alert`가 평일/시간/생활권 기준 예약을 저장한다.
- 예약 알림 실행기가 예약 시간에 `check_traffic_issues`와 동일한 매칭을 수행한다.
- 같은 예약이 같은 날짜에 중복 발송되지 않는다.
- tool/server name에 `kakao`가 없다.
- `.env.example`에는 변수명만 있고 실제 키가 없다.
