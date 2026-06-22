#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
import time as time_module
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

SERVER_NAME = "seoul-traffic-guard"
PROTOCOL_VERSION = "2025-03-26"
DEFAULT_USER_ID = "local"
USER_ID_HEADERS = ("x-playmcp-user-id", "x-user-id", "x-forwarded-user")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

ALERT_AREAS: dict[str, dict[str, dict[str, Any]]] = {}
SCHEDULED_ALERTS: dict[str, dict[str, dict[str, Any]]] = {}
OAUTH_TOKENS: dict[str, dict[str, Any]] = {}
OAUTH_STATE: dict[str, str] = {}
SCHEDULER_STARTED = False
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
MCP_ENDPOINTS = {"/", "/mcp"}
REQUIRED_ENV_VARS = ("KAKAO_REST_API_KEY", "KAKAO_REDIRECT_URI", "SEOUL_OPENAPI_KEY")
OPTIONAL_ENV_VARS = ("KAKAO_CLIENT_SECRET", "ALLOWED_ORIGINS", "TASK_RUN_SECRET", "PLAYMCP_DB_PATH", "PLAYMCP_USER_ID_HEADERS")


TOOLS: list[dict[str, Any]] = [
    {
        "name": "set_alert_area",
        "description": "Register a Seoul Traffic Guard alert area from a label, Seoul address or place keyword, and radius.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "User-facing area label, for example home, work, or school."},
                "address": {"type": "string", "description": "Seoul address or place keyword, for example 서울시청 or 을지로입구역."},
                "radius_m": {"type": "integer", "minimum": 100, "maximum": 5000, "default": 1000},
            },
            "required": ["label", "address"],
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Set alert area",
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
            "idempotentHint": True,
        },
    },
    {
        "name": "list_alert_areas",
        "description": "List registered Seoul Traffic Guard alert areas.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {
            "title": "List alert areas",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "check_traffic_issues",
        "description": "Check real-time Seoul traffic issues near registered alert areas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "Optional alert area label to check."},
            },
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Check traffic issues",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
            "idempotentHint": True,
        },
    },
    {
        "name": "preview_alert_message",
        "description": "Preview the notification text before sending it to the user's own chat.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "Alert area label."},
                "issue_summary": {"type": "string", "description": "Traffic issue summary to include."},
            },
            "required": ["label", "issue_summary"],
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Preview alert message",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "send_self_alert",
        "description": "Send a prepared Seoul Traffic Guard alert to the user's own chat after OAuth is implemented.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message text to send."},
                "dry_run": {"type": "boolean", "default": True, "description": "Keep true until OAuth send is wired."},
            },
            "required": ["message"],
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Send self alert",
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
            "idempotentHint": False,
        },
    },
    {
        "name": "set_scheduled_alert",
        "description": "Create or update a scheduled alert for a registered traffic guard area.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "Scheduled alert label."},
                "area_label": {"type": "string", "description": "Existing alert area label to check."},
                "weekdays": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(WEEKDAYS)},
                    "description": "Weekdays to run, for example mon through fri.",
                },
                "time": {"type": "string", "description": "Run time in HH:MM, 24-hour format."},
                "target_day": {"type": "string", "enum": ["today", "tomorrow"], "default": "today"},
                "send_policy": {"type": "string", "enum": ["only_if_issues", "always"], "default": "only_if_issues"},
            },
            "required": ["label", "area_label", "weekdays", "time"],
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Set scheduled alert",
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "list_scheduled_alerts",
        "description": "List registered scheduled traffic guard alerts.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {
            "title": "List scheduled alerts",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "delete_scheduled_alert",
        "description": "Delete a scheduled traffic guard alert by label.",
        "inputSchema": {
            "type": "object",
            "properties": {"label": {"type": "string", "description": "Scheduled alert label to delete."}},
            "required": ["label"],
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Delete scheduled alert",
            "readOnlyHint": False,
            "destructiveHint": True,
            "openWorldHint": False,
            "idempotentHint": True,
        },
    },
]


def text_result(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def env_value(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value

    env_path = Path(__file__).with_name(".env")
    try:
        lines = env_path.read_text().splitlines()
    except FileNotFoundError:
        return ""

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return ""


def origin_allowed(origin: str, host: str) -> bool:
    origin = origin.strip().lower()
    if not origin:
        return True
    allowed = {item.strip().lower() for item in env_value("ALLOWED_ORIGINS").split(",") if item.strip()}
    allowed.update({"http://localhost:8000", "http://127.0.0.1:8000"})

    host_value = host.split(",", 1)[0].strip().lower()
    host_name = host_value[1:].split("]", 1)[0] if host_value.startswith("[") else host_value.split(":", 1)[0]
    if host_name in LOCAL_HOSTS:
        allowed.update({f"http://{host_value}", f"https://{host_value}"})
    return origin in allowed


def accepts_mcp_response(accept: str) -> bool:
    if not accept:
        return True
    values = {part.split(";", 1)[0].strip().lower() for part in accept.split(",")}
    return "*/*" in values or "application/json" in values or "text/event-stream" in values


def task_secret_valid(headers: Any) -> bool:
    configured = env_value("TASK_RUN_SECRET")
    if not configured:
        return False
    header_secret = headers.get("x-task-secret", "")
    auth = headers.get("authorization", "")
    bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    return secrets.compare_digest(header_secret, configured) or secrets.compare_digest(bearer, configured)


def is_json_rpc_request(message: Any) -> bool:
    return isinstance(message, dict) and "method" in message and "id" in message


def db_path() -> Path:
    return Path(env_value("PLAYMCP_DB_PATH") or Path(__file__).with_name("playmcp.db"))


def normalize_user_id(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return DEFAULT_USER_ID
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._@:-")
    if len(value) <= 128 and all(ch in allowed for ch in value):
        return value
    return "u_" + sha256(value.encode("utf-8")).hexdigest()[:24]


def user_id_from_headers(headers: Any) -> str:
    configured = tuple(name.strip().lower() for name in env_value("PLAYMCP_USER_ID_HEADERS").split(",") if name.strip())
    # ponytail: provisional PlayMCP user boundary; env lets deploys add the confirmed header without a code change.
    for name in configured + USER_ID_HEADERS:
        value = headers.get(name)
        if value:
            return normalize_user_id(value)
    return DEFAULT_USER_ID


def user_alert_areas(user_id: str) -> dict[str, dict[str, Any]]:
    return ALERT_AREAS.setdefault(user_id, {})


def user_scheduled_alerts(user_id: str) -> dict[str, dict[str, Any]]:
    return SCHEDULED_ALERTS.setdefault(user_id, {})


def user_oauth_tokens(user_id: str) -> dict[str, Any]:
    return OAUTH_TOKENS.setdefault(user_id, {})


def ensure_user_table(conn: sqlite3.Connection, table: str, create_sql: str, migrate_sql: str) -> None:
    columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
    if not columns:
        conn.execute(create_sql)
        return
    if "user_id" in columns:
        return
    legacy = f"{table}_legacy"
    conn.execute(f"ALTER TABLE {table} RENAME TO {legacy}")
    conn.execute(create_sql)
    conn.execute(migrate_sql.format(legacy=legacy))
    conn.execute(f"DROP TABLE {legacy}")


def db_connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    ensure_user_table(
        conn,
        "alert_areas",
        "CREATE TABLE IF NOT EXISTS alert_areas (user_id TEXT NOT NULL, label TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (user_id, label))",
        "INSERT OR REPLACE INTO alert_areas(user_id, label, data) SELECT 'local', label, data FROM {legacy}",
    )
    ensure_user_table(
        conn,
        "scheduled_alerts",
        "CREATE TABLE IF NOT EXISTS scheduled_alerts (user_id TEXT NOT NULL, label TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (user_id, label))",
        "INSERT OR REPLACE INTO scheduled_alerts(user_id, label, data) SELECT 'local', label, data FROM {legacy}",
    )
    ensure_user_table(
        conn,
        "oauth_tokens",
        "CREATE TABLE IF NOT EXISTS oauth_tokens (user_id TEXT PRIMARY KEY, data TEXT NOT NULL)",
        "INSERT OR REPLACE INTO oauth_tokens(user_id, data) SELECT 'local', data FROM {legacy} WHERE id = 1",
    )
    return conn


def readiness_report() -> tuple[dict[str, Any], int]:
    env_checks = {name: bool(env_value(name)) for name in REQUIRED_ENV_VARS + OPTIONAL_ENV_VARS}
    missing_required = [name for name in REQUIRED_ENV_VARS if not env_checks[name]]
    redirect_uri = env_value("KAKAO_REDIRECT_URI")
    oauth_callback = urllib.parse.urlparse(redirect_uri).path == "/auth/kakao/callback" if redirect_uri else False

    database_ok = False
    try:
        with db_connect() as conn:
            conn.execute("SELECT 1").fetchone()
        database_ok = True
    except (OSError, sqlite3.Error):
        database_ok = False

    ok = not missing_required and oauth_callback and database_ok
    return (
        {
            "status": "ok" if ok else "degraded",
            "server": SERVER_NAME,
            "checks": {
                "environment": env_checks,
                "missing_required": missing_required,
                "oauth_callback": oauth_callback,
                "database": database_ok,
                "mcp_endpoint": "/mcp",
            },
        },
        200 if ok else 503,
    )


def save_alert_area(area: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> None:
    with db_connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO alert_areas(user_id, label, data) VALUES (?, ?, ?)",
            (user_id, area["label"], json.dumps(area, ensure_ascii=False)),
        )


def save_scheduled_alert(schedule: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> None:
    with db_connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO scheduled_alerts(user_id, label, data) VALUES (?, ?, ?)",
            (user_id, schedule["label"], json.dumps(schedule, ensure_ascii=False)),
        )


def delete_scheduled_alert_db(label: str, user_id: str = DEFAULT_USER_ID) -> None:
    with db_connect() as conn:
        conn.execute("DELETE FROM scheduled_alerts WHERE user_id = ? AND label = ?", (user_id, label))


def save_oauth_tokens(tokens: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> None:
    with db_connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO oauth_tokens(user_id, data) VALUES (?, ?)",
            (user_id, json.dumps(tokens, ensure_ascii=False)),
        )


def load_state() -> None:
    with db_connect() as conn:
        ALERT_AREAS.clear()
        SCHEDULED_ALERTS.clear()
        OAUTH_TOKENS.clear()
        for user_id, label, data in conn.execute("SELECT user_id, label, data FROM alert_areas"):
            user_alert_areas(user_id)[label] = json.loads(data)
        for user_id, label, data in conn.execute("SELECT user_id, label, data FROM scheduled_alerts"):
            user_scheduled_alerts(user_id)[label] = json.loads(data)
        for user_id, data in conn.execute("SELECT user_id, data FROM oauth_tokens"):
            OAUTH_TOKENS[user_id] = json.loads(data)


def kakao_json(path: str, query: dict[str, str]) -> dict[str, Any]:
    key = env_value("KAKAO_REST_API_KEY")
    if not key:
        raise ValueError("KAKAO_REST_API_KEY is not configured")
    url = f"https://dapi.kakao.com{path}?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {key}"})
    with urllib.request.urlopen(req, timeout=10) as res:
        return json.loads(res.read().decode("utf-8"))


def app_base_url() -> str:
    redirect_uri = env_value("KAKAO_REDIRECT_URI") or "http://localhost:8000/auth/kakao/callback"
    parsed = urllib.parse.urlparse(redirect_uri)
    return f"{parsed.scheme}://{parsed.netloc}"


def build_kakao_authorize_url(state: str) -> str:
    key = env_value("KAKAO_REST_API_KEY")
    redirect_uri = env_value("KAKAO_REDIRECT_URI")
    if not key or not redirect_uri:
        raise ValueError("KAKAO_REST_API_KEY and KAKAO_REDIRECT_URI are required")
    query = urllib.parse.urlencode(
        {
            "client_id": key,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "talk_message",
            "state": state,
        }
    )
    return f"https://kauth.kakao.com/oauth/authorize?{query}"


def auth_start_url(user_id: str = DEFAULT_USER_ID) -> str:
    base = f"{app_base_url()}/auth/kakao/start"
    if user_id == DEFAULT_USER_ID:
        return base
    return f"{base}?{urllib.parse.urlencode({'user_id': user_id})}"


def form_post(url: str, data: dict[str, str], headers: dict[str, str] | None = None) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers or {}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as res:
        return json.loads(res.read().decode("utf-8") or "{}")


def request_kakao_token(code: str) -> dict[str, Any]:
    data = {
        "grant_type": "authorization_code",
        "client_id": env_value("KAKAO_REST_API_KEY"),
        "redirect_uri": env_value("KAKAO_REDIRECT_URI"),
        "code": code,
    }
    client_secret = env_value("KAKAO_CLIENT_SECRET")
    if client_secret:
        data["client_secret"] = client_secret
    return form_post("https://kauth.kakao.com/oauth/token", data)


def refresh_kakao_token(user_id: str = DEFAULT_USER_ID) -> str:
    tokens = user_oauth_tokens(user_id)
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise ValueError(f"OAuth required. Open {auth_start_url(user_id)} first.")
    data = {
        "grant_type": "refresh_token",
        "client_id": env_value("KAKAO_REST_API_KEY"),
        "refresh_token": str(refresh_token),
    }
    client_secret = env_value("KAKAO_CLIENT_SECRET")
    if client_secret:
        data["client_secret"] = client_secret
    token = form_post("https://kauth.kakao.com/oauth/token", data)
    token.setdefault("refresh_token", refresh_token)
    tokens.update({k: v for k, v in token.items() if k in {"access_token", "refresh_token", "expires_in", "scope"}})
    save_oauth_tokens(tokens, user_id)
    return str(tokens["access_token"])


def complete_oauth(code: str, state: str) -> str:
    if not code:
        raise ValueError("code is required")
    user_id = OAUTH_STATE.pop(state, "")
    if not state or not user_id:
        raise ValueError("invalid OAuth state")
    token = request_kakao_token(code)
    user_oauth_tokens(user_id).update(
        {k: v for k, v in token.items() if k in {"access_token", "refresh_token", "expires_in", "scope"}}
    )
    save_oauth_tokens(user_oauth_tokens(user_id), user_id)
    return "connected"


def post_kakao_api(path: str, data: dict[str, str], token: str) -> dict[str, Any]:
    return form_post(
        f"https://kapi.kakao.com{path}",
        data,
        {"Authorization": f"Bearer {token}", "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
    )


def send_kakao_self_message(message: str, user_id: str = DEFAULT_USER_ID) -> None:
    token = user_oauth_tokens(user_id).get("access_token") or refresh_kakao_token(user_id)
    if not token:
        raise ValueError(f"OAuth required. Open {auth_start_url(user_id)} first.")
    template_object = {
        "object_type": "text",
        "text": message,
        "link": {"web_url": "https://data.seoul.go.kr", "mobile_web_url": "https://data.seoul.go.kr"},
        "button_title": "서울 교통정보 확인",
    }
    data = {"template_object": json.dumps(template_object, ensure_ascii=False)}
    try:
        post_kakao_api("/v2/api/talk/memo/default/send", data, str(token))
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise
        post_kakao_api("/v2/api/talk/memo/default/send", data, refresh_kakao_token(user_id))


def wgs84_to_tm(x: float, y: float, query: str) -> dict[str, float]:
    tm_data = kakao_json(
        "/v2/local/geo/transcoord.json",
        {"x": str(x), "y": str(y), "input_coord": "WGS84", "output_coord": "TM"},
    )
    tm_docs = tm_data.get("documents") or []
    if not tm_docs:
        raise ValueError(f"No Kakao coordinate transform result for address: {query}")
    return {"tm_x": float(tm_docs[0]["x"]), "tm_y": float(tm_docs[0]["y"])}


def geocode_address(address: str) -> dict[str, Any]:
    data = kakao_json("/v2/local/search/keyword.json", {"query": address})
    docs = data.get("documents") or []
    if not docs:
        data = kakao_json("/v2/local/search/address.json", {"query": address})
        docs = data.get("documents") or []
    if not docs:
        raise ValueError(f"No Kakao Local result for address: {address}")

    doc = docs[0]
    x = float(doc["x"])
    y = float(doc["y"])
    tm = wgs84_to_tm(x, y, address)

    return {
        "address_name": doc.get("road_address_name") or doc.get("address_name") or doc.get("place_name") or address,
        "x": x,
        "y": y,
        **tm,
    }


def fetch_accinfo(limit: int = 1000) -> list[dict[str, Any]]:
    key = env_value("SEOUL_OPENAPI_KEY")
    if not key:
        raise ValueError("SEOUL_OPENAPI_KEY is not configured")
    url = f"http://openapi.seoul.go.kr:8088/{urllib.parse.quote(key)}/xml/AccInfo/1/{limit}/"
    with urllib.request.urlopen(url, timeout=10) as res:
        root = ET.fromstring(res.read())

    code = root.findtext(".//CODE") or root.findtext(".//code")
    if code and code != "INFO-000":
        message = root.findtext(".//MESSAGE") or root.findtext(".//message") or "unknown error"
        raise ValueError(f"Seoul AccInfo error: {message}")

    rows = []
    for row in root.findall(".//row"):
        item: dict[str, Any] = {child.tag.lower(): (child.text or "").strip() for child in row}
        for key_name in ("grs80tm_x", "grs80tm_y"):
            try:
                item[key_name] = float(item[key_name])
            except (KeyError, ValueError):
                item[key_name] = None
        rows.append(item)
    return rows


def distance_m(area: dict[str, Any], issue: dict[str, Any]) -> float | None:
    try:
        dx = float(area["tm_x"]) - float(issue["grs80tm_x"])
        dy = float(area["tm_y"]) - float(issue["grs80tm_y"])
    except (KeyError, TypeError, ValueError):
        return None
    return (dx * dx + dy * dy) ** 0.5


def traffic_issue_lines(areas: list[dict[str, Any]], issues: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for area in areas:
        for issue in issues:
            distance = distance_m(area, issue)
            if distance is not None and distance <= int(area["radius_m"]):
                summary = issue.get("acc_info") or "교통 이슈"
                lines.append(f"- {area['label']} {round(distance)}m: {summary}")
    return lines[:5]


def validate_schedule(args: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    label = str(args["label"]).strip()
    area_label = str(args["area_label"]).strip()
    if not label or not area_label:
        raise ValueError("label and area_label are required")
    areas = user_alert_areas(user_id)
    schedules = user_scheduled_alerts(user_id)
    if area_label not in areas:
        raise ValueError(f"No alert area named '{area_label}'.")

    weekdays = args.get("weekdays")
    if not isinstance(weekdays, list) or not weekdays:
        raise ValueError("weekdays must be a non-empty list")
    normalized_weekdays = [str(day).strip().lower() for day in weekdays]
    invalid_weekdays = [day for day in normalized_weekdays if day not in WEEKDAYS]
    if invalid_weekdays:
        raise ValueError(f"Invalid weekdays: {', '.join(invalid_weekdays)}")

    run_time = str(args["time"]).strip()
    try:
        hour_text, minute_text = run_time.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError:
        raise ValueError("time must use HH:MM format") from None
    if len(hour_text) != 2 or len(minute_text) != 2 or hour not in range(24) or minute not in range(60):
        raise ValueError("time must use HH:MM format")

    target_day = str(args.get("target_day", "today")).strip()
    if target_day not in {"today", "tomorrow"}:
        raise ValueError("target_day must be today or tomorrow")
    send_policy = str(args.get("send_policy", "only_if_issues")).strip()
    if send_policy not in {"only_if_issues", "always"}:
        raise ValueError("send_policy must be only_if_issues or always")

    timezone = str(args.get("timezone", "Asia/Seoul")).strip()
    try:
        ZoneInfo(timezone)
    except Exception:
        raise ValueError(f"Unknown timezone: {timezone}") from None

    return {
        "label": label,
        "area_label": area_label,
        "weekdays": normalized_weekdays,
        "time": run_time,
        "timezone": timezone,
        "target_day": target_day,
        "send_policy": send_policy,
        "enabled": bool(args.get("enabled", True)),
        "last_sent_date": schedules.get(label, {}).get("last_sent_date"),
    }


def run_due_alerts(now: datetime | None = None) -> list[str]:
    now = now or datetime.now(ZoneInfo("Asia/Seoul"))
    sent_messages: list[str] = []

    for user_id, schedules in list(SCHEDULED_ALERTS.items()):
        areas = user_alert_areas(user_id)
        for schedule in list(schedules.values()):
            try:
                if not schedule.get("enabled", True):
                    continue
                local_now = now.astimezone(ZoneInfo(schedule.get("timezone", "Asia/Seoul")))
                today = local_now.date().isoformat()
                if schedule.get("last_sent_date") == today:
                    continue
                if WEEKDAYS[local_now.weekday()] not in schedule["weekdays"]:
                    continue
                if local_now.strftime("%H:%M") != schedule["time"]:
                    continue

                area = areas.get(schedule["area_label"])
                if not area:
                    continue
                issue_lines = traffic_issue_lines([area], fetch_accinfo())
                if not issue_lines and schedule["send_policy"] == "only_if_issues":
                    continue

                body = "\n".join(issue_lines) if issue_lines else "등록 지역 주변 확인된 교통 이슈 없음"
                message = f"[서울 교통 이슈 알리미]\n{schedule['area_label']} 예약 알림\n{body}"
                send_kakao_self_message(message, user_id)
                schedule["last_sent_date"] = today
                save_scheduled_alert(schedule, user_id)
                sent_messages.append(message)
            except Exception:
                # ponytail: per-schedule isolation; add persisted failure details only when users need diagnostics.
                continue

    return sent_messages


def scheduler_loop() -> None:
    while True:
        try:
            run_due_alerts()
        except Exception:
            pass
        time_module.sleep(60)


def start_scheduler() -> None:
    global SCHEDULER_STARTED
    if SCHEDULER_STARTED:
        return
    SCHEDULER_STARTED = True
    threading.Thread(target=scheduler_loop, daemon=True).start()


def server_address() -> tuple[str, int]:
    return (os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8000")))


def call_tool(name: str, args: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    areas = user_alert_areas(user_id)
    schedules = user_scheduled_alerts(user_id)

    if name == "set_alert_area":
        label = str(args["label"]).strip()
        address = str(args["address"]).strip()
        radius_m = int(args.get("radius_m", 1000))
        if not label or not address:
            raise ValueError("label and address are required")
        if radius_m < 100 or radius_m > 5000:
            raise ValueError("radius_m must be between 100 and 5000")
        try:
            geo = geocode_address(address)
        except urllib.error.URLError:
            return text_result("주소 조회를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.")
        except ValueError:
            return text_result("장소나 주소를 찾을 수 없습니다. 더 구체적으로 입력해 주세요.")
        areas[label] = {"label": label, "address": address, "radius_m": radius_m, **geo}
        save_alert_area(areas[label], user_id)
        return text_result(f"Registered alert area '{label}' at {geo['address_name']} with radius {radius_m}m.")

    if name == "list_alert_areas":
        if not areas:
            return text_result("No alert areas registered.")
        lines = [
            f"- {area['label']}: {area.get('address_name') or area['address']} ({area['radius_m']}m)"
            for area in areas.values()
        ]
        return text_result("\n".join(lines))

    if name == "check_traffic_issues":
        label = args.get("label")
        if label and label not in areas:
            return text_result(f"No alert area named '{label}'.")
        if not areas:
            return text_result("No alert areas registered.")
        selected_areas = [areas[label]] if label else list(areas.values())
        try:
            matches = traffic_issue_lines(selected_areas, fetch_accinfo())
        except (ValueError, urllib.error.URLError):
            return text_result("교통 정보 조회를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.")
        if not matches:
            return text_result("등록 지역 주변 확인된 교통 이슈 없음")
        return text_result("\n".join(matches))

    if name == "preview_alert_message":
        return text_result(f"[서울 교통 이슈 알리미]\n{args['label']}: {args['issue_summary']}")

    if name == "send_self_alert":
        if args.get("dry_run", True):
            return text_result("Dry run only. Set dry_run=false after OAuth is connected.")
        message = str(args["message"]).strip()
        if not message:
            raise ValueError("message is required")
        try:
            send_kakao_self_message(message, user_id)
            return text_result("Sent alert to your KakaoTalk chat.")
        except ValueError as exc:
            return text_result(str(exc))
        except urllib.error.URLError:
            return text_result("알림 전송에 실패했습니다. OAuth를 다시 연결하거나 잠시 후 다시 시도해 주세요.")

    if name == "set_scheduled_alert":
        schedule = validate_schedule(args, user_id)
        schedules[schedule["label"]] = schedule
        save_scheduled_alert(schedule, user_id)
        return text_result(
            f"Registered scheduled alert '{schedule['label']}' for {schedule['area_label']} at {schedule['time']}."
        )

    if name == "list_scheduled_alerts":
        if not schedules:
            return text_result("No scheduled alerts registered.")
        lines = [
            f"- {item['label']}: {item['area_label']}, {','.join(item['weekdays'])} {item['time']}, {item['send_policy']}"
            for item in schedules.values()
        ]
        return text_result("\n".join(lines))

    if name == "delete_scheduled_alert":
        label = str(args["label"]).strip()
        if not label:
            raise ValueError("label is required")
        schedules.pop(label, None)
        delete_scheduled_alert_db(label, user_id)
        return text_result(f"Deleted scheduled alert '{label}'.")

    raise ValueError(f"Unknown tool: {name}")


def handle_rpc(request: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> dict[str, Any] | None:
    if "id" not in request:
        return None
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": "0.1.0"},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        try:
            result = call_tool(params["name"], params.get("arguments") or {}, user_id)
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": str(exc)}}

    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            self.send_json({"status": "ok", "server": SERVER_NAME})
            return
        if parsed.path == "/ready":
            payload, status = readiness_report()
            self.send_json(payload, status=status)
            return
        if parsed.path in MCP_ENDPOINTS:
            self.send_empty(405, {"allow": "POST"})
            return
        if parsed.path == "/auth/kakao/start":
            query = urllib.parse.parse_qs(parsed.query)
            user_id = normalize_user_id(query.get("user_id", [""])[0]) if query.get("user_id") else user_id_from_headers(self.headers)
            state = secrets.token_urlsafe(24)
            OAUTH_STATE[state] = user_id
            self.send_redirect(build_kakao_authorize_url(state))
            return
        if parsed.path == "/auth/kakao/callback":
            query = urllib.parse.parse_qs(parsed.query)
            try:
                complete_oauth(query.get("code", [""])[0], query.get("state", [""])[0])
                self.send_text("Kakao OAuth connected. You can close this tab.")
            except Exception:
                self.send_text("Kakao OAuth failed. Please start OAuth again from the service.", status=400)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/tasks/run-due-alerts":
            if not env_value("TASK_RUN_SECRET"):
                self.send_error(404)
                return
            if not task_secret_valid(self.headers):
                self.send_json({"error": "forbidden"}, status=403)
                return
            try:
                sent = run_due_alerts()
                self.send_json({"status": "ok", "sent_count": len(sent)})
            except Exception:
                self.send_json({"error": "scheduled alert run failed"}, status=500)
            return

        if parsed.path not in MCP_ENDPOINTS:
            self.send_error(404)
            return
        if not origin_allowed(self.headers.get("origin", ""), self.headers.get("host", "")):
            self.send_json({"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": "Origin not allowed"}}, status=403)
            return
        if not accepts_mcp_response(self.headers.get("accept", "")):
            self.send_json(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": "Unsupported Accept header"}},
                status=406,
            )
            return

        try:
            user_id = user_id_from_headers(self.headers)
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if isinstance(payload, list):
                if not any(is_json_rpc_request(item) for item in payload):
                    self.send_empty(202)
                    return
                responses = [res for item in payload if (res := handle_rpc(item, user_id)) is not None]
                self.send_json(responses)
            else:
                if not is_json_rpc_request(payload):
                    self.send_empty(202)
                    return
                response = handle_rpc(payload, user_id)
                if response is None:
                    self.send_empty(202)
                else:
                    self.send_json(response)
        except Exception as exc:
            self.send_json({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}, status=400)

    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_empty(self, status: int, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("content-length", "0")
        self.end_headers()

    def send_redirect(self, url: str) -> None:
        self.send_response(302)
        self.send_header("location", url)
        self.end_headers()

    def send_text(self, text: str, status: int = 200) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "text/plain; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    load_state()
    start_scheduler()
    host, port = server_address()
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"{SERVER_NAME} listening on http://{host}:{port}/mcp")
    server.serve_forever()


if __name__ == "__main__":
    main()
