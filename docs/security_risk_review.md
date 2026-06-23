# Security Risk Review

작성일: 2026-06-23

## 범위

이 문서는 `seoul-traffic-guard` MCP 서버를 Agentic Player 10 공모전 제출 환경과 실제 사용자 흐름 기준으로 점검한 결과다. 점검은 `superpowers:using-superpowers` 절차로 관련 보안 스킬을 확인한 뒤, `codex-security`의 threat-model/security-scan 관점과 triage 결과 형식에 맞춰 수행했다.

점검 대상:

- Remote MCP HTTP endpoint: `/mcp`
- Kakao OAuth callback: `/auth/kakao/start`, `/auth/kakao/callback`
- KakaoTalk 나에게 보내기 발송 흐름
- 사용자별 생활권, 예약, OAuth token 분리
- 서울 Open API, Kakao Local API, ODsay API 호출
- 예약 실행 endpoint: `/tasks/run-due-alerts`
- Git 저장소에 남은 secret 흔적

비밀값 점검은 값 자체를 출력하지 않고 패턴과 위치만 확인했다. 현재 저장소 스캔에서는 실제 API key, access token, refresh token, PAT, OpenAI key 형태의 하드코딩된 값은 발견되지 않았다. 탐지된 항목은 `server.py` 안의 변수명 기반 token 처리 코드뿐이다.

## 현재 보안상 긍정적인 점

- `.gitignore`가 `.env`, `playmcp.db`, `playmcp.db-*`, `.data/`를 제외한다.
- `/ready`는 환경 변수 존재 여부를 boolean으로만 반환하고 key 값을 반환하지 않는다.
- OAuth callback 실패 응답은 구체 오류 대신 재연결 안내만 반환한다.
- OAuth token은 `TOKEN_ENCRYPTION_KEY` 설정 시 Fernet으로 암호화되어 SQLite에 저장된다.
- MCP POST body 크기와 JSON-RPC batch 개수를 제한한다.
- 사용자별 호출량 제한, 서울 교통 API 짧은 TTL 캐시, 카카오톡 중복 발송 방지 로직이 있다.
- KakaoTalk 발송은 친구/단체방이 아니라 `나에게 보내기` API로 제한되어 있다.
- `send_self_alert`는 기본값이 `dry_run=true`라 사용자가 명시적으로 실제 발송을 요청해야 한다.
- 예약 실행 endpoint는 `TASK_RUN_SECRET`이 없으면 404를 반환하고, 설정된 경우 `secrets.compare_digest`로 비교한다.
- SQLite 쿼리는 사용자 입력을 문자열 보간하지 않고 parameterized query를 사용한다.
- 사용자가 지정한 외부 URL을 fetch하지 않는다. 외부 호출 대상은 서울 Open API, Kakao API, ODsay API의 고정 domain이다.
- ODsay, Kakao, Seoul API의 주요 실패 경로는 원본 HTTP 오류 대신 짧은 사용자 안내로 매핑되어 있다.

## 신뢰 경계

| 경계 | 현재 구현 | 제출 환경에서 필요한 가정 |
| --- | --- | --- |
| 사용자 식별 | `X-PlayMCP-User-Id` 등 헤더 값을 `user_id`로 사용 | PlayMCP 또는 앞단 proxy가 이 헤더를 신뢰 가능하게 주입하고, 외부 사용자가 임의로 조작하지 못해야 한다. |
| OAuth token 저장 | `TOKEN_ENCRYPTION_KEY` 설정 시 SQLite `oauth_tokens`에 암호문으로 저장 | DB 파일/볼륨/백업은 secret storage로 취급하고, encryption key는 환경 변수 secret으로 관리해야 한다. |
| 외부 API key | 환경 변수 또는 `.env`에서 로드 | PlayMCP in KC 환경 변수에만 저장하고 로그/문서/스크린샷에 노출하지 않아야 한다. |
| 예약 실행 | 내부 endpoint 또는 background thread | 외부 cron을 쓰는 경우 `TASK_RUN_SECRET`을 설정하고 secret 값을 노출하지 않아야 한다. |
| 브라우저 Origin | `Origin`이 있으면 allowlist 확인, 없으면 허용 | MCP 서버 간 호출을 위해 Origin 없음은 허용하되, 브라우저 직접 호출이 생기면 `ALLOWED_ORIGINS`를 확정해야 한다. |

## Findings

### STG-SEC-001: 사용자 경계가 요청 헤더 신뢰에 의존함

상태: Hardened / Needs Platform Confirmation  
영향도: 배포 ingress가 직접 접근 가능하면 High, PlayMCP가 신뢰 경계를 제공하면 Medium/Accepted Risk

관련 코드:

- `server.py:311-318` `user_id_from_headers`
- `server.py:1417-1420` `do_POST`

현재 서버는 `PLAYMCP_USER_ID_HEADERS`가 설정되어 있으면 그 헤더만 사용자 ID로 사용하고, `REQUIRE_USER_ID_HEADER=true`이면 사용자 헤더 없는 MCP 요청을 거절한다. 이 구조는 PlayMCP가 신뢰 가능한 사용자 ID 헤더를 주입하고 외부 사용자가 해당 헤더를 임의 설정하지 못할 때 안전하다.

위험 시나리오:

1. 배포 endpoint가 PlayMCP를 거치지 않고 외부에서 직접 호출 가능하다.
2. 공격자가 임의의 `X-PlayMCP-User-Id`를 넣어 요청한다.
3. 해당 user id에 저장된 생활권/예약을 조회하거나 삭제하거나, OAuth token이 있으면 그 사용자 컨텍스트로 알림 발송을 시도할 수 있다.

현재 완화 요소:

- 로컬과 시뮬레이션에서는 명시 user id로 분리 동작을 검증했다.
- OAuth state는 callback 시점에 user id에 바인딩된다.
- 실제 제출 흐름은 PlayMCP in KC를 통한 Remote MCP 호출을 전제로 한다.

제출 전 조치:

- PlayMCP가 실제로 제공하는 사용자 식별 헤더명을 확인한다.
- `PLAYMCP_USER_ID_HEADERS`를 확정된 헤더 하나로 제한한다.
- `REQUIRE_USER_ID_HEADER=true`를 설정한다.
- 직접 endpoint 접근에서 사용자가 임의 user id 헤더를 넣을 수 있는지 확인한다.
- 직접 접근을 막을 수 없다면, PlayMCP ingress 전용 shared secret 또는 서명된 헤더 검증을 추가해야 한다.

### STG-SEC-002: OAuth token이 SQLite에 평문 JSON으로 저장됨

상태: Implemented when `TOKEN_ENCRYPTION_KEY` is configured  
영향도: Medium

관련 코드:

- `server.py:367-371` `oauth_tokens` table
- `server.py:433-438` `save_oauth_tokens`
- `server.py:573-583` `complete_oauth`

현재 Kakao OAuth `access_token`, `refresh_token`, `expires_in`, `scope`는 `TOKEN_ENCRYPTION_KEY` 설정 시 Fernet 암호문으로 SQLite에 저장된다. 키를 설정하지 않은 로컬 개발 환경에서는 기존 plaintext row를 계속 읽고 쓸 수 있다.

현재 완화 요소:

- `playmcp.db`와 관련 파일은 `.gitignore`에 포함되어 있다.
- 암호화 저장 테스트가 raw `access_token`/`refresh_token` 문자열이 DB row에 남지 않는지 검증한다.
- `/ready`와 일반 응답은 token 값을 반환하지 않는다.
- 저장소 secret 패턴 스캔에서 실제 token literal은 발견되지 않았다.
- 발송 scope는 나에게 보내기이며 친구/단체방 발송은 구현하지 않았다.

제출 전 조치:

- `PLAYMCP_DB_PATH`가 public volume이나 repo mount가 아닌 private runtime storage를 가리키는지 확인한다.
- DB 파일을 제출 zip, Docker context, GitHub commit, 스크린샷에 포함하지 않는다.
- 이미 채팅/스크린샷/로그에 노출된 가능성이 있는 token/key는 회전한다.

후속 하드닝:

- 가능하다면 managed secret storage 또는 platform-provided encrypted storage로 이전한다.

### STG-SEC-003: 일부 예외 경로가 `str(exc)`를 클라이언트에 반환함

상태: Implemented  
영향도: Low to Medium

관련 코드:

- `server.py:1288-1294` `send_self_alert` ValueError 응답
- `server.py:1345-1350` `tools/call` broad exception 응답
- `server.py:1436-1437` POST 처리 broad exception 응답

일부 broad exception 경로가 `str(exc)`를 MCP 응답으로 그대로 반환한다. 지금 관찰된 일반 실패 경로에서는 민감정보가 직접 노출되지 않았지만, 외부 API/라이브러리 예외 문자열에 URL, 파일 경로, 내부 구현 정보가 포함되면 사용자에게 전달될 수 있다. 특히 ODsay 요청 URL에는 `apiKey` query가 들어가므로, 예상하지 못한 예외 문자열 반영은 줄이는 편이 안전하다.

현재 완화 요소:

- ODsay 인증 실패, 서울 API 타임아웃, Kakao OAuth callback 실패 등 주요 경로는 짧은 메시지로 매핑되어 있다.
- 저장소 secret 패턴 스캔에서 실제 key literal은 발견되지 않았다.

권장 조치:

- broad exception handler는 일반 안내 문구만 반환한다.
- OAuth 미연결처럼 사용자 행동이 필요한 예외만 allowlist 메시지로 반환한다.
- 테스트에 “잘못된 요청이 Python exception text나 URL query를 echo하지 않는다” 케이스를 추가한다.

### STG-SEC-004: MCP POST body 크기 제한이 없음

상태: Implemented  
영향도: Low to Medium

관련 코드:

- `server.py:1417-1420`

현재 `Content-Length`가 `MAX_REQUEST_BYTES`를 넘으면 body를 읽기 전에 413으로 거절한다. JSON-RPC batch도 `MAX_BATCH_REQUESTS`를 넘으면 400으로 거절한다.

현재 완화 요소:

- PlayMCP 또는 앞단 platform이 자체 request size limit을 둘 수 있다.
- tool schema는 JSON parsing 이후 입력을 제한한다.

검증:

- oversized body 거절과 oversized batch 거절 테스트가 `test_server.py`에 있다.

### STG-SEC-005: 컨테이너가 root 사용자로 실행됨

상태: Hardening  
영향도: Low

관련 코드:

- `Dockerfile:1-12`

현재 Dockerfile은 `python:3.13-slim` 기본 user인 root로 실행된다. 컨테스트용 단일 Python 서버로는 즉시 차단 이슈는 아니지만, 컨테이너 탈출 또는 런타임 파일 변조 영향 범위를 줄이려면 non-root user로 실행하는 편이 좋다.

권장 조치:

- `/app` 소유권을 non-root user에 부여하고 `USER appuser`로 실행한다.
- `PLAYMCP_DB_PATH`가 non-root user로 쓰기 가능한 경로인지 함께 확인한다.

### STG-SEC-006: `Origin` 없음 요청을 허용함

상태: Contextual Accepted Risk  
영향도: Low to Medium

관련 코드:

- `server.py:262-273`

MCP server-to-server 호출은 `Origin` 헤더가 없을 수 있으므로 현재 구현은 Origin이 없으면 허용한다. 이는 Remote MCP 호환성 측면에서는 타당하다. 다만 브라우저에서 직접 호출되는 surface가 커지면 CORS/CSRF 관점에서 allowlist가 더 중요해진다.

제출 전 조치:

- PlayMCP/ChatGPT for Kakao 호출에서 실제 `Origin`이 붙는지 확인한다.
- 붙는다면 `ALLOWED_ORIGINS`에 확정 origin만 넣는다.
- 직접 브라우저 UI를 제공하지 않는다는 점을 제출 설명과 README의 known limitations에 유지한다.

## 실사용 흐름별 점검

| 흐름 | 주요 위험 | 현재 판단 |
| --- | --- | --- |
| 생활권 등록 | 사용자가 입력한 주소/장소가 DB에 저장됨 | label, 주소명, 좌표, 반경만 저장한다. 과도한 개인정보는 받지 않는 안내가 필요하다. |
| 대중교통 경로 후보 조회 | ODsay key, 출발지/도착지 노출 | API key는 환경 변수이며 응답에는 후보 요약만 반환한다. 출발지/도착지는 사용자가 직접 입력하므로 개인정보 최소 입력을 권장한다. |
| 교통 이슈 조회 | 원본 API payload 과다 노출 | 현재는 최대 5개 요약 라인만 반환한다. |
| Kakao OAuth | state 탈취, callback 오용 | state는 난수이며 in-memory로 저장된다. 재시작 시 OAuth가 실패할 수 있지만 stale state를 오래 보관하지 않는 장점이 있다. |
| 실제 알림 발송 | 오발송, 타 사용자 token 사용 | 기본 dry-run이며 나에게 보내기만 사용한다. 다만 user id 헤더 신뢰 경계 확인이 필요하다. |
| 예약 알림 | 장기 실행/중복/오발송 | 같은 날짜 중복 발송 방지 로직은 있다. 런타임 지속성은 PlayMCP in KC 환경 의존으로 별도 보류 상태다. |

## 제출 전 우선순위

1. `STG-SEC-001` 확인: PlayMCP user id 헤더와 직접 endpoint 접근 가능성을 확인한다.
2. `TOKEN_ENCRYPTION_KEY`를 PlayMCP in KC 환경 변수로 설정한다.
3. `REQUIRE_USER_ID_HEADER=true`와 확정된 `PLAYMCP_USER_ID_HEADERS`를 배포 환경에 설정한다.
4. `STG-SEC-005` 선택 하드닝: Docker non-root 실행으로 전환한다.
5. `STG-SEC-006` 운영 확인: 배포 호출 origin을 확인해 `ALLOWED_ORIGINS`를 확정한다.

## 제출 가능성 판단

현재 범위에서 critical blocker는 발견되지 않았다. broad exception text 제거, MCP request cap, batch cap, per-user rate limit, Seoul API cache, duplicate send guard, OAuth token encryption path는 코드와 테스트에 반영되었다.

사용자별 권한 분리는 현재 가장 중요한 운영 확인 항목이다. PlayMCP in KC가 신뢰 가능한 user id를 제공하고 외부 임의 헤더를 차단한다면 accepted risk로 둘 수 있다. 그렇지 않다면 제출 전 shared ingress secret 또는 signed user header가 필요하다.

## 검증 기록

수행한 점검:

- 서버 코드의 OAuth, 사용자 식별, DB 저장, MCP HTTP handler, 예약 실행 경로 수동 검토
- Dockerfile과 `.gitignore` 검토
- README, 제출 계획, 배포 체크리스트, 개인정보 문서, 사전 평가 문서 검토
- 저장소 secret 패턴 마스킹 스캔
- Codex Security triage 결과 렌더링

마스킹 스캔 결과:

- 실제 하드코딩 secret 패턴: 발견 없음
- 변수명 기반 token 처리 코드: `server.py` 내부 3건

남은 확인:

- PlayMCP in KC가 실제로 전달하는 user id header
- PlayMCP in KC 또는 Kakao Tools가 붙이는 `Origin`
- 배포 endpoint의 외부 직접 접근 가능 여부
- PlayMCP in KC persistent storage의 접근 제어와 백업 정책

## Follow-up Plan After Review

작성일: 2026-06-23

### STG-SEC-001 사용자 식별 헤더

공개 검색 기준으로는 PlayMCP in KC가 어떤 사용자 식별 헤더를 주입하고, 외부 임의 헤더를 제거하는지 확인 가능한 공식 문서를 찾지 못했다. 따라서 현재는 이 헤더를 신뢰 경계로 확정하면 안 된다.

현실적인 해결책은 세 단계다.

1. 제출 전 확인:
   - PlayMCP AI 채팅에서 서버가 받은 헤더 이름만 마스킹 로깅하는 임시 진단을 1회 수행한다.
   - 값은 절대 기록하지 않고, `x-playmcp-user-id present=true`처럼 존재 여부만 본다.
   - 직접 `curl`로 같은 endpoint에 임의 `X-PlayMCP-User-Id`를 넣어 호출했을 때 접근 가능한지 확인한다.
2. 공모전 MVP:
   - `PLAYMCP_USER_ID_HEADERS`를 실제 확인된 헤더 하나로만 설정한다.
   - 헤더가 없으면 `local` 공유 상태로 떨어지는 배포는 금지한다. 로컬 개발에서만 fallback을 허용한다.
3. 실서비스 전환:
   - PlayMCP가 헤더 신뢰성을 보장하지 않으면 자체적으로 완전한 multi-user 보안을 제공하기 어렵다.
   - 이 경우 선택지는 둘뿐이다.
     - PlayMCP/ingress가 추가할 수 있는 shared secret 또는 signed user header를 도입한다.
     - 사용자가 OAuth 후 받은 난수형 `user_key`를 tool 인자로 넘기게 한다. 보안은 낫지만 UX가 나빠져 공모전용으로는 최후 수단이다.

Ponytail 결론: 지금 당장 복잡한 자체 인증계를 만들지 않는다. 먼저 PlayMCP ingress가 신뢰 가능한지 확인하고, 안 되면 `REQUIRE_USER_ID_HEADER=true`와 `TRUSTED_INGRESS_SECRET` 같은 최소 게이트만 추가한다.

### STG-SEC-002 OAuth token at rest

명확한 해결책은 있다. 단, Python 표준 라이브러리에는 안전한 대칭 암호화 구현이 없으므로 직접 암호화를 만들면 안 된다.

선택지는 세 가지다.

1. 현재 방식 유지:
   - SQLite를 private runtime storage로 취급한다.
   - 공모전 MVP에서는 가장 작은 변경이다.
   - 단점: DB 유출 시 token이 평문이다.
2. OAuth token 비영속화:
   - token을 메모리에만 저장한다.
   - 단점: 서버 재시작 시 OAuth를 다시 해야 하고 예약 알림이 깨진다.
   - 현재 제품 목표와 맞지 않다.
3. 검증된 라이브러리로 token JSON만 암호화:
   - `cryptography.fernet.Fernet` 또는 key rotation이 필요하면 `MultiFernet`을 사용한다.
   - `TOKEN_ENCRYPTION_KEY`를 PlayMCP 환경 변수로 둔다.
   - DB에는 `fernet:<ciphertext>`만 저장한다.
   - 기존 평문 row는 최초 로드 시 복호화 실패가 아니라 평문으로 읽고, 다음 저장 때 암호문으로 migration한다.

구현 결과:

1. `cryptography.fernet.Fernet` 기반 `TOKEN_ENCRYPTION_KEY` 암호화를 추가했다.
2. `save_oauth_tokens`와 `load_state`의 `oauth_tokens` 경로만 감쌌다.
3. DB에는 `fernet:<ciphertext>` 형식으로 저장한다.
4. 기존 평문 row도 계속 읽는다.
5. 테스트가 DB row에 token 원문이 저장되지 않는지와 기존 평문 DB를 읽을 수 있는지 검증한다.

Ponytail 결론: 자체 암호화 구현은 만들지 않고 검증된 dependency 하나만 사용한다.

### STG-SEC-003 Raw exception echo

조치 완료:

- `tools/call` broad exception은 일반 메시지로 변경했다.
- POST parsing broad exception은 일반 메시지로 변경했다.
- `send_self_alert`는 OAuth 미연결 안내만 allowlist하고, 나머지 `ValueError`는 일반 전송 실패 메시지로 변경했다.
- 회귀 테스트를 추가했다.

검증:

```bash
python test_server.py
```

결과: `ok`

### STG-SEC-004 Request body size cap

구현 결과:

1. `MAX_REQUEST_BYTES=262144` 기본값을 추가했다.
2. `do_POST`에서 body를 읽기 전에 초과 요청을 413으로 거절한다.
3. `MAX_BATCH_REQUESTS=20` 기본값을 추가했다.
4. JSON-RPC batch 21개 이상은 400으로 거절한다.
5. oversized body와 oversized batch 회귀 테스트를 추가했다.

Ponytail 결론: dependency 없이 표준 라이브러리 handler 경계에서 막는다.

### API 과다 요청 방어

이 프로젝트는 서울 Open API, Kakao Local API, ODsay, KakaoTalk Message API 호출에 의존한다. OWASP API Security Top 10의 `API4:2023 Unrestricted Resource Consumption` 관점에서도 request size, interaction frequency, third-party spending/usage limit을 제한해야 한다.

구현 결과:

1. 사용자별 in-memory rate limit
   - `send_self_alert`: 6/min
   - 그 외 모든 tool 합산: 60/min
2. expensive API cache
   - `fetch_accinfo()`는 30초 TTL cache만 둔다.
   - 같은 사용자가 “다시 확인해줘”를 연속 호출해도 서울 API를 매번 때리지 않는다.
3. KakaoTalk 발송 보호
   - 동일 user가 같은 message hash를 60초 안에 다시 보내면 차단한다.
   - 실수/프롬프트 반복에 의한 중복 발송을 줄인다.
4. 사용자 안내
   - 초과 시 “요청이 많습니다. 잠시 후 다시 시도해 주세요.”만 반환한다.
   - 남은 횟수나 내부 quota 값은 공개하지 않는다.

Ponytail 결론: Redis, DB counter, 외부 gateway는 지금 추가하지 않는다. PlayMCP in KC 단일 프로세스 공모전 환경에서는 in-memory limit이 가장 작은 방어다. 다중 replica가 되면 그때 Redis나 platform gateway rate limit으로 바꾼다.

## 참고 출처

- OWASP API Security Top 10 2023, API4 Unrestricted Resource Consumption: https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/
- Cryptography Fernet documentation: https://cryptography.io/en/latest/fernet/
