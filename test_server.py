from datetime import datetime
import http.client
import json
import os
import tempfile
import threading
import urllib.error
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from zoneinfo import ZoneInfo

TEST_TMP = tempfile.TemporaryDirectory()
os.environ["PLAYMCP_DB_PATH"] = os.path.join(TEST_TMP.name, "test.db")

from server import (
    ALERT_AREAS,
    Handler,
    OAUTH_STATE,
    OAUTH_TOKENS,
    SCHEDULED_ALERTS,
    TOOLS,
    build_kakao_authorize_url,
    complete_oauth,
    handle_rpc,
    load_state,
    normalize_user_id,
    readiness_report,
    refresh_kakao_token,
    run_due_alerts,
    save_oauth_tokens,
    server_address,
    user_id_from_headers,
)


def rpc(method, params=None, request_id=1, user_id="local"):
    return handle_rpc({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}, user_id=user_id)


def areas(user_id="local"):
    return ALERT_AREAS.setdefault(user_id, {})


def schedules(user_id="local"):
    return SCHEDULED_ALERTS.setdefault(user_id, {})


def tokens(user_id="local"):
    return OAUTH_TOKENS.setdefault(user_id, {})


def test_tool_contract():
    names = [tool["name"] for tool in TOOLS]
    assert names == [
        "set_alert_area",
        "list_alert_areas",
        "check_traffic_issues",
        "preview_alert_message",
        "send_self_alert",
        "set_scheduled_alert",
        "list_scheduled_alerts",
        "delete_scheduled_alert",
    ]
    assert all("kakao" not in name.lower() for name in names)
    assert all("annotations" in tool for tool in TOOLS)


def test_server_address_uses_deploy_env():
    with patch.dict(os.environ, {"HOST": "0.0.0.0", "PORT": "8080"}):
        assert server_address() == ("0.0.0.0", 8080)


def test_readiness_report_masks_config_values():
    values = {
        "KAKAO_REST_API_KEY": "rest-secret",
        "KAKAO_REDIRECT_URI": "http://localhost:8000/auth/kakao/callback",
        "SEOUL_OPENAPI_KEY": "seoul-secret",
        "KAKAO_CLIENT_SECRET": "client-secret",
    }

    with patch("server.env_value", side_effect=lambda name: values.get(name, os.environ.get(name, ""))):
        payload, status = readiness_report()

    rendered = json.dumps(payload)
    assert status == 200
    assert payload["status"] == "ok"
    assert payload["checks"]["environment"]["KAKAO_REST_API_KEY"] is True
    assert payload["checks"]["missing_required"] == []
    assert "rest-secret" not in rendered
    assert "seoul-secret" not in rendered
    assert "client-secret" not in rendered


def test_readiness_report_degraded_when_required_env_missing():
    with patch("server.env_value", side_effect=lambda name: os.environ.get(name, "") if name == "PLAYMCP_DB_PATH" else ""):
        payload, status = readiness_report()

    assert status == 503
    assert payload["status"] == "degraded"
    assert payload["checks"]["missing_required"] == ["KAKAO_REST_API_KEY", "KAKAO_REDIRECT_URI", "SEOUL_OPENAPI_KEY"]


def test_user_id_from_headers():
    assert user_id_from_headers({"x-playmcp-user-id": "user-a"}) == "user-a"
    assert user_id_from_headers({}) == "local"
    assert normalize_user_id("bad/user").startswith("u_")
    with patch("server.env_value", side_effect=lambda name: "x-custom-user" if name == "PLAYMCP_USER_ID_HEADERS" else ""):
        assert user_id_from_headers({"x-custom-user": "user-b"}) == "user-b"


def test_http_transport_edges():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    def request(method, path, payload=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps(payload).encode() if payload is not None else None
        conn.request(method, path, body=body, headers=headers or {})
        res = conn.getresponse()
        data = res.read()
        conn.close()
        return res.status, dict(res.getheaders()), data

    try:
        values = {
            "KAKAO_REST_API_KEY": "rest-secret",
            "KAKAO_REDIRECT_URI": "http://localhost:8000/auth/kakao/callback",
            "SEOUL_OPENAPI_KEY": "seoul-secret",
        }
        with patch("server.env_value", side_effect=lambda name: values.get(name, os.environ.get(name, ""))):
            status, headers, body = request("GET", "/ready")
        assert status == 200
        assert headers["content-type"].startswith("application/json")
        assert json.loads(body)["checks"]["database"] is True

        status, headers, body = request("GET", "/auth/kakao/callback?code=bad&state=bad")
        callback_text = body.decode()
        assert status == 400
        assert "Kakao OAuth failed" in callback_text
        assert "invalid OAuth state" not in callback_text

        status, headers, body = request("GET", "/mcp", headers={"Accept": "text/event-stream"})
        assert status == 405
        assert body == b""

        status, headers, body = request(
            "POST",
            "/mcp",
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        )
        assert status == 202
        assert body == b""

        status, headers, body = request(
            "POST",
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Origin": "https://evil.example",
            },
        )
        assert status == 403

        status, headers, body = request(
            "POST",
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Origin": "https://evil.example",
                "Host": "evil.example",
            },
        )
        assert status == 403

        local_origin = f"http://127.0.0.1:{port}"
        status, headers, body = request(
            "POST",
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Origin": local_origin,
                "Host": f"127.0.0.1:{port}",
            },
        )
        assert status == 200

        status, headers, body = request(
            "POST",
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        )
        assert status == 200
        assert headers["content-type"].startswith("application/json")
        assert json.loads(body)["result"]["protocolVersion"] == "2025-03-26"
    finally:
        server.shutdown()
        server.server_close()


def test_task_run_due_alerts_endpoint_requires_secret():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    def request(headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", "/tasks/run-due-alerts", headers=headers or {})
        res = conn.getresponse()
        data = res.read()
        conn.close()
        return res.status, data

    try:
        with patch.dict(os.environ, {}, clear=True):
            status, _ = request()
            assert status == 404

        with patch.dict(os.environ, {"TASK_RUN_SECRET": "secret"}):
            status, _ = request({"X-Task-Secret": "wrong"})
            assert status == 403

        with (
            patch.dict(os.environ, {"TASK_RUN_SECRET": "secret"}),
            patch("server.run_due_alerts", return_value=["sent"]),
        ):
            status, body = request({"Authorization": "Bearer secret"})
            assert status == 200
            assert json.loads(body)["sent_count"] == 1
    finally:
        server.shutdown()
        server.server_close()


def test_rpc_flow():
    ALERT_AREAS.clear()
    initialized = rpc("initialize")["result"]
    assert initialized["serverInfo"]["name"] == "seoul-traffic-guard"

    listed = rpc("tools/list")["result"]["tools"]
    assert len(listed) == 8

    with patch(
        "server.geocode_address",
        return_value={
            "address_name": "서울 중구 세종대로 110",
            "x": 126.978,
            "y": 37.566,
            "tm_x": 198000.0,
            "tm_y": 451000.0,
        },
    ):
        result = rpc(
            "tools/call",
            {
                "name": "set_alert_area",
                "arguments": {"label": "school", "address": "서울시 중구 세종대로 110", "radius_m": 1000},
            },
        )["result"]["content"][0]["text"]
    assert "school" in result

    areas = rpc("tools/call", {"name": "list_alert_areas", "arguments": {}})["result"]["content"][0]["text"]
    assert "서울 중구 세종대로 110" in areas


def test_rpc_user_data_isolated():
    ALERT_AREAS.clear()
    SCHEDULED_ALERTS.clear()
    OAUTH_TOKENS.clear()

    def fake_geocode(address):
        return {
            "address_name": address,
            "x": 126.978,
            "y": 37.566,
            "tm_x": 198000.0,
            "tm_y": 451000.0,
        }

    with patch("server.geocode_address", side_effect=fake_geocode):
        rpc(
            "tools/call",
            {"name": "set_alert_area", "arguments": {"label": "home", "address": "사용자A 주소"}},
            user_id="user-a",
        )
        rpc(
            "tools/call",
            {"name": "set_alert_area", "arguments": {"label": "home", "address": "사용자B 주소"}},
            user_id="user-b",
        )

    a_list = rpc("tools/call", {"name": "list_alert_areas", "arguments": {}}, user_id="user-a")["result"]["content"][0][
        "text"
    ]
    b_list = rpc("tools/call", {"name": "list_alert_areas", "arguments": {}}, user_id="user-b")["result"]["content"][0][
        "text"
    ]

    assert "사용자A 주소" in a_list
    assert "사용자B 주소" not in a_list
    assert "사용자B 주소" in b_list
    assert "사용자A 주소" not in b_list


def test_set_alert_area_stores_geocoded_coordinates():
    ALERT_AREAS.clear()
    with patch(
        "server.geocode_address",
        return_value={
            "address_name": "서울 중구 세종대로 110",
            "x": 126.978,
            "y": 37.566,
            "tm_x": 198000.0,
            "tm_y": 451000.0,
        },
    ):
        rpc(
            "tools/call",
            {
                "name": "set_alert_area",
                "arguments": {"label": "work", "address": "서울시 중구 세종대로 110", "radius_m": 500},
            },
        )

    assert areas()["work"]["address_name"] == "서울 중구 세종대로 110"
    assert areas()["work"]["tm_x"] == 198000.0
    assert areas()["work"]["tm_y"] == 451000.0


def test_check_traffic_issues_filters_accinfo_near_area():
    ALERT_AREAS.clear()
    areas()["work"] = {
        "label": "work",
        "address": "서울시 중구 세종대로 110",
        "address_name": "서울 중구 세종대로 110",
        "radius_m": 100,
        "tm_x": 198000.0,
        "tm_y": 451000.0,
    }

    with patch(
        "server.fetch_accinfo",
        return_value=[
            {"acc_info": "시청 인근 공사", "grs80tm_x": 198030.0, "grs80tm_y": 451040.0},
            {"acc_info": "먼 지역 사고", "grs80tm_x": 205000.0, "grs80tm_y": 460000.0},
        ],
    ):
        result = rpc("tools/call", {"name": "check_traffic_issues", "arguments": {"label": "work"}})["result"][
            "content"
        ][0]["text"]

    assert "시청 인근 공사" in result
    assert "먼 지역 사고" not in result


def test_check_traffic_issues_returns_short_external_error():
    ALERT_AREAS.clear()
    areas()["work"] = {
        "label": "work",
        "address": "x",
        "radius_m": 100,
        "tm_x": 198000.0,
        "tm_y": 451000.0,
    }

    with patch("server.fetch_accinfo", side_effect=urllib.error.URLError("raw network detail")):
        result = rpc("tools/call", {"name": "check_traffic_issues", "arguments": {"label": "work"}})["result"][
            "content"
        ][0]["text"]

    assert "교통 정보 조회" in result
    assert "raw network detail" not in result


def test_fetch_accinfo_normalizes_uppercase_xml_tags():
    from server import fetch_accinfo

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return """
            <AccInfo>
              <RESULT><CODE>INFO-000</CODE></RESULT>
              <row><ACC_INFO>공사</ACC_INFO><GRS80TM_X>198030</GRS80TM_X><GRS80TM_Y>451040</GRS80TM_Y></row>
            </AccInfo>
            """.encode()

    with (
        patch("server.env_value", return_value="key"),
        patch("urllib.request.urlopen", return_value=FakeResponse()),
    ):
        rows = fetch_accinfo(1)

    assert rows == [{"acc_info": "공사", "grs80tm_x": 198030.0, "grs80tm_y": 451040.0}]


def test_schedule_tools_register_list_delete():
    ALERT_AREAS.clear()
    SCHEDULED_ALERTS.clear()
    areas()["commute"] = {"label": "commute", "address": "x", "radius_m": 1000, "tm_x": 198000, "tm_y": 451000}

    created = rpc(
        "tools/call",
        {
            "name": "set_scheduled_alert",
            "arguments": {
                "label": "weekday_morning",
                "area_label": "commute",
                "weekdays": ["mon", "tue", "wed", "thu", "fri"],
                "time": "07:00",
                "target_day": "today",
                "send_policy": "only_if_issues",
            },
        },
    )["result"]["content"][0]["text"]
    assert "weekday_morning" in created
    assert schedules()["weekday_morning"]["area_label"] == "commute"

    listed = rpc("tools/call", {"name": "list_scheduled_alerts", "arguments": {}})["result"]["content"][0]["text"]
    assert "weekday_morning" in listed
    assert "07:00" in listed

    deleted = rpc(
        "tools/call", {"name": "delete_scheduled_alert", "arguments": {"label": "weekday_morning"}}
    )["result"]["content"][0]["text"]
    assert "weekday_morning" in deleted
    assert "weekday_morning" not in schedules()


def test_run_due_alerts_sends_once_per_day_when_issues_match():
    ALERT_AREAS.clear()
    SCHEDULED_ALERTS.clear()
    areas()["commute"] = {
        "label": "commute",
        "address": "x",
        "radius_m": 100,
        "tm_x": 198000.0,
        "tm_y": 451000.0,
    }
    schedules()["weekday_morning"] = {
        "label": "weekday_morning",
        "area_label": "commute",
        "weekdays": ["fri"],
        "time": "07:00",
        "timezone": "Asia/Seoul",
        "target_day": "today",
        "send_policy": "only_if_issues",
        "enabled": True,
        "last_sent_date": None,
    }

    now = datetime(2026, 6, 19, 7, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    delivered = []

    def fake_send(message, user_id="local"):
        delivered.append(message)

    with (
        patch("server.fetch_accinfo", return_value=[{"acc_info": "시청 인근 공사", "grs80tm_x": 198030, "grs80tm_y": 451040}]),
        patch("server.send_kakao_self_message", side_effect=fake_send),
    ):
        sent = run_due_alerts(now)
        sent_again = run_due_alerts(now)

    assert len(sent) == 1
    assert delivered == sent
    assert "시청 인근 공사" in sent[0]
    assert sent_again == []
    assert schedules()["weekday_morning"]["last_sent_date"] == "2026-06-19"


def test_run_due_alerts_continues_after_one_schedule_fails():
    ALERT_AREAS.clear()
    SCHEDULED_ALERTS.clear()
    for label in ("bad", "good"):
        areas()[label] = {
            "label": label,
            "address": "x",
            "radius_m": 100,
            "tm_x": 198000.0,
            "tm_y": 451000.0,
        }
        schedules()[f"{label}_morning"] = {
            "label": f"{label}_morning",
            "area_label": label,
            "weekdays": ["fri"],
            "time": "07:00",
            "timezone": "Asia/Seoul",
            "target_day": "today",
            "send_policy": "only_if_issues",
            "enabled": True,
            "last_sent_date": None,
        }

    delivered = []

    def fake_send(message, user_id="local"):
        if "bad 예약 알림" in message:
            raise RuntimeError("send failed")
        delivered.append(message)

    with (
        patch("server.fetch_accinfo", return_value=[{"acc_info": "시청 인근 공사", "grs80tm_x": 198030, "grs80tm_y": 451040}]),
        patch("server.send_kakao_self_message", side_effect=fake_send),
    ):
        sent = run_due_alerts(datetime(2026, 6, 19, 7, 0, tzinfo=ZoneInfo("Asia/Seoul")))

    assert len(sent) == 1
    assert delivered == sent
    assert "good 예약 알림" in sent[0]
    assert schedules()["bad_morning"]["last_sent_date"] is None
    assert schedules()["good_morning"]["last_sent_date"] == "2026-06-19"


def test_kakao_authorize_url_requests_talk_message_scope():
    url = build_kakao_authorize_url("state-123")

    assert "response_type=code" in url
    assert "scope=talk_message" in url
    assert "state=state-123" in url


def test_complete_oauth_stores_tokens():
    OAUTH_TOKENS.clear()
    OAUTH_STATE.clear()
    OAUTH_STATE["state-123"] = "local"

    with patch(
        "server.request_kakao_token",
        return_value={"access_token": "access-1", "refresh_token": "refresh-1", "scope": "talk_message"},
    ):
        result = complete_oauth("code-123", "state-123")

    assert result == "connected"
    assert tokens()["access_token"] == "access-1"
    assert tokens()["refresh_token"] == "refresh-1"


def test_complete_oauth_stores_tokens_per_user():
    OAUTH_TOKENS.clear()
    OAUTH_STATE.clear()
    OAUTH_STATE["state-a"] = "user-a"
    OAUTH_STATE["state-b"] = "user-b"

    with patch(
        "server.request_kakao_token",
        side_effect=[
            {"access_token": "access-a", "refresh_token": "refresh-a", "scope": "talk_message"},
            {"access_token": "access-b", "refresh_token": "refresh-b", "scope": "talk_message"},
        ],
    ):
        complete_oauth("code-a", "state-a")
        complete_oauth("code-b", "state-b")

    assert tokens("user-a")["access_token"] == "access-a"
    assert tokens("user-b")["access_token"] == "access-b"


def test_send_self_alert_posts_kakao_message_when_connected():
    OAUTH_TOKENS.clear()
    tokens()["access_token"] = "access-1"
    calls = []

    def fake_post(path, data, token):
        calls.append((path, data, token))
        return {"result_code": 0}

    with patch("server.post_kakao_api", side_effect=fake_post):
        result = rpc(
            "tools/call",
            {"name": "send_self_alert", "arguments": {"message": "테스트 알림", "dry_run": False}},
        )["result"]["content"][0]["text"]

    assert "sent" in result.lower()
    assert calls[0][0] == "/v2/api/talk/memo/default/send"
    assert calls[0][2] == "access-1"
    assert "테스트 알림" in calls[0][1]["template_object"]


def test_send_self_alert_returns_short_external_error():
    OAUTH_TOKENS.clear()
    tokens()["access_token"] = "access-1"

    with patch("server.post_kakao_api", side_effect=urllib.error.URLError("raw token detail")):
        result = rpc(
            "tools/call",
            {"name": "send_self_alert", "arguments": {"message": "테스트 알림", "dry_run": False}},
        )["result"]["content"][0]["text"]

    assert "알림 전송에 실패" in result
    assert "raw token detail" not in result


def test_send_self_alert_requires_oauth_when_not_connected():
    OAUTH_TOKENS.clear()

    result = rpc(
        "tools/call",
        {"name": "send_self_alert", "arguments": {"message": "테스트 알림", "dry_run": False}},
    )["result"]["content"][0]["text"]

    assert "OAuth" in result
    assert "/auth/kakao/start" in result


def test_sqlite_persists_alert_area_schedule_and_tokens():
    ALERT_AREAS.clear()
    SCHEDULED_ALERTS.clear()
    OAUTH_TOKENS.clear()

    areas()["commute"] = {
        "label": "commute",
        "address": "서울시 중구 세종대로 110",
        "address_name": "서울 중구 세종대로 110",
        "radius_m": 500,
        "x": 126.978,
        "y": 37.566,
        "tm_x": 198000.0,
        "tm_y": 451000.0,
    }
    schedules()["weekday_morning"] = {
        "label": "weekday_morning",
        "area_label": "commute",
        "weekdays": ["mon", "tue", "wed", "thu", "fri"],
        "time": "07:00",
        "timezone": "Asia/Seoul",
        "target_day": "today",
        "send_policy": "only_if_issues",
        "enabled": True,
        "last_sent_date": None,
    }
    tokens().update({"access_token": "access-1", "refresh_token": "refresh-1", "scope": "talk_message"})

    from server import save_alert_area, save_scheduled_alert

    save_alert_area(areas()["commute"])
    save_scheduled_alert(schedules()["weekday_morning"])
    save_oauth_tokens(tokens())
    ALERT_AREAS.clear()
    SCHEDULED_ALERTS.clear()
    OAUTH_TOKENS.clear()

    load_state()

    assert areas()["commute"]["address_name"] == "서울 중구 세종대로 110"
    assert schedules()["weekday_morning"]["area_label"] == "commute"
    assert tokens()["refresh_token"] == "refresh-1"


def test_refresh_kakao_token_updates_saved_tokens():
    OAUTH_TOKENS.clear()
    tokens()["refresh_token"] = "refresh-1"

    with patch(
        "server.form_post",
        return_value={"access_token": "access-2", "expires_in": 21599},
    ):
        token = refresh_kakao_token()

    OAUTH_TOKENS.clear()
    load_state()

    assert token == "access-2"
    assert tokens()["access_token"] == "access-2"
    assert tokens()["refresh_token"] == "refresh-1"


def test_send_self_alert_refreshes_when_access_token_missing():
    OAUTH_TOKENS.clear()
    tokens()["refresh_token"] = "refresh-1"
    calls = []

    def fake_post(path, data, token):
        calls.append((path, token))
        return {"result_code": 0}

    with (
        patch("server.form_post", return_value={"access_token": "access-2", "expires_in": 21599}),
        patch("server.post_kakao_api", side_effect=fake_post),
    ):
        result = rpc(
            "tools/call",
            {"name": "send_self_alert", "arguments": {"message": "테스트 알림", "dry_run": False}},
        )["result"]["content"][0]["text"]

    assert "sent" in result.lower()
    assert calls[0][1] == "access-2"


if __name__ == "__main__":
    test_tool_contract()
    test_server_address_uses_deploy_env()
    test_readiness_report_masks_config_values()
    test_readiness_report_degraded_when_required_env_missing()
    test_user_id_from_headers()
    test_http_transport_edges()
    test_task_run_due_alerts_endpoint_requires_secret()
    test_rpc_flow()
    test_rpc_user_data_isolated()
    test_set_alert_area_stores_geocoded_coordinates()
    test_check_traffic_issues_filters_accinfo_near_area()
    test_check_traffic_issues_returns_short_external_error()
    test_fetch_accinfo_normalizes_uppercase_xml_tags()
    test_schedule_tools_register_list_delete()
    test_run_due_alerts_sends_once_per_day_when_issues_match()
    test_run_due_alerts_continues_after_one_schedule_fails()
    test_kakao_authorize_url_requests_talk_message_scope()
    test_complete_oauth_stores_tokens()
    test_complete_oauth_stores_tokens_per_user()
    test_send_self_alert_posts_kakao_message_when_connected()
    test_send_self_alert_returns_short_external_error()
    test_send_self_alert_requires_oauth_when_not_connected()
    test_sqlite_persists_alert_area_schedule_and_tokens()
    test_refresh_kakao_token_updates_saved_tokens()
    test_send_self_alert_refreshes_when_access_token_missing()
    print("ok")
