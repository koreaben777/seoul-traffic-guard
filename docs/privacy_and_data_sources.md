# Privacy And Data Sources

## Stored Data

The server stores only the data needed for the traffic alert workflow:

| Data | Purpose | Storage |
| --- | --- | --- |
| User id | Separate each user's data | SQLite key |
| Alert area label | User-facing area name | SQLite |
| Alert area coordinates and radius | Traffic issue matching | SQLite |
| Scheduled alert settings | Automatic checks | SQLite |
| Kakao OAuth token fields | KakaoTalk self-alert delivery | SQLite |

Local development uses `local` as the fallback user id. Deployed PlayMCP usage must use the platform-provided user identity or a confirmed request header.

## Not Collected

- KakaoTalk chat history
- KakaoTalk chat room list
- KakaoTalk attachments
- KakaoTalk local cache or app storage
- KakaoMap saved places or recent searches
- Friend or group chat recipient data

## Data Sources

| Source | Use |
| --- | --- |
| Seoul Open Data `AccInfo` | Real-time traffic incident/control information |
| Kakao Local API | Address search and coordinate transform |
| Kakao Login | User consent and OAuth token issuance |
| KakaoTalk Message API | Send-to-me alert delivery |

## User Consent

KakaoTalk alert delivery requires Kakao Login consent for `talk_message`. If consent or token refresh fails, the server should return a short reconnect instruction instead of attempting delivery.

## Submission Notes

- Do not commit `.env`, `playmcp.db`, API keys, OAuth tokens, or client secrets.
- User-facing responses should summarize only relevant traffic issue details.
- Raw Seoul Open Data payloads should not be returned directly to users.
- The service sends alerts only to the user's own KakaoTalk chat.
