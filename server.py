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
REGION_CACHE: dict[tuple[int, int], dict[str, Any]] = {}
TRANSIT_ROUTE_OPTIONS: dict[str, dict[str, list[dict[str, Any]]]] = {}
RATE_LIMITS: dict[tuple[str, str], list[float]] = {}
ACCINFO_CACHE: dict[str, Any] = {}
SENT_MESSAGE_GUARD: dict[tuple[str, str], float] = {}
SCHEDULER_STARTED = False
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
MCP_ENDPOINTS = {"/", "/mcp"}
REQUIRED_ENV_VARS = ("KAKAO_REST_API_KEY", "KAKAO_REDIRECT_URI", "SEOUL_OPENAPI_KEY")
OPTIONAL_ENV_VARS = (
    "KAKAO_CLIENT_SECRET",
    "ALLOWED_ORIGINS",
    "TASK_RUN_SECRET",
    "PLAYMCP_DB_PATH",
    "PLAYMCP_USER_ID_HEADERS",
    "REQUIRE_USER_ID_HEADER",
    "MAX_REQUEST_BYTES",
    "MAX_BATCH_REQUESTS",
    "TOKEN_ENCRYPTION_KEY",
    "ODSAY_API_KEY",
)
GENERIC_TOOL_ERROR = "도구 호출을 처리할 수 없습니다. 입력값을 확인해 주세요."
GENERIC_REQUEST_ERROR = "잘못된 MCP 요청입니다."
MAX_REQUEST_BYTES = int(os.environ.get("MAX_REQUEST_BYTES", "262144"))
MAX_BATCH_REQUESTS = int(os.environ.get("MAX_BATCH_REQUESTS", "20"))
BATCH_TOO_LARGE_ERROR = "MCP batch request is too large."
RATE_LIMIT_WINDOW_SECONDS = 60
SEND_SELF_ALERT_RATE_LIMIT = 6
OTHER_TOOL_CALL_RATE_LIMIT = 60
OTHER_TOOL_RATE_KEY = "__other_tools__"
RATE_LIMIT_MESSAGE = "요청이 많습니다. 잠시 후 다시 시도해 주세요."
ACCINFO_CACHE_TTL_SECONDS = 30
DUPLICATE_SEND_WINDOW_SECONDS = 60
DUPLICATE_SEND_MESSAGE = "이미 같은 알림을 방금 보냈습니다. 잠시 후 다시 시도해 주세요."


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
        "name": "delete_alert_area",
        "description": "Delete a registered Seoul Traffic Guard alert area by label.",
        "inputSchema": {
            "type": "object",
            "properties": {"label": {"type": "string", "description": "Alert area label to delete."}},
            "required": ["label"],
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Delete alert area",
            "readOnlyHint": False,
            "destructiveHint": True,
            "openWorldHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "find_transit_route_options",
        "description": "Find selectable public-transit route options from origin and destination using ODsay.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "User-facing route label to save after selection."},
                "origin": {"type": "string", "description": "Route origin place keyword."},
                "destination": {"type": "string", "description": "Route destination place keyword."},
            },
            "required": ["label", "origin", "destination"],
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Find transit route options",
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
            "idempotentHint": True,
        },
    },
    {
        "name": "set_selected_transit_route_alert_area",
        "description": "Register selected public-transit route options after the user chooses route ids.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "Label used in find_transit_route_options."},
                "route_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "radius_m": {"type": "integer", "minimum": 100, "maximum": 5000, "default": 500},
            },
            "required": ["label", "route_ids"],
            "additionalProperties": False,
        },
        "annotations": {
            "title": "Set selected transit route alert area",
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
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
                "skip_dates": {"type": "array", "items": {"type": "string"}, "description": "YYYY-MM-DD dates to skip, including holidays."},
                "pause_start_date": {"type": "string", "description": "YYYY-MM-DD temporary pause start date."},
                "pause_end_date": {"type": "string", "description": "YYYY-MM-DD temporary pause end date."},
                "start_date": {"type": "string", "description": "YYYY-MM-DD schedule start date."},
                "end_date": {"type": "string", "description": "YYYY-MM-DD schedule end date."},
                "interval_days": {"type": "integer", "minimum": 1, "maximum": 365, "description": "Run every N days from start_date."},
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


class UserIdentityRequired(ValueError):
    pass


def env_bool(name: str) -> bool:
    return env_value(name).strip().lower() in {"1", "true", "yes", "on"}


def user_id_from_headers(headers: Any) -> str:
    configured = tuple(name.strip().lower() for name in env_value("PLAYMCP_USER_ID_HEADERS").split(",") if name.strip())
    # ponytail: header trust still depends on PlayMCP ingress stripping spoofed external headers.
    for name in configured or USER_ID_HEADERS:
        value = headers.get(name)
        if value:
            return normalize_user_id(value)
    if env_bool("REQUIRE_USER_ID_HEADER"):
        raise UserIdentityRequired("user identity header is required")
    return DEFAULT_USER_ID


def user_alert_areas(user_id: str) -> dict[str, dict[str, Any]]:
    return ALERT_AREAS.setdefault(user_id, {})


def user_transit_route_options(user_id: str) -> dict[str, list[dict[str, Any]]]:
    return TRANSIT_ROUTE_OPTIONS.setdefault(user_id, {})


def user_scheduled_alerts(user_id: str) -> dict[str, dict[str, Any]]:
    return SCHEDULED_ALERTS.setdefault(user_id, {})


def user_oauth_tokens(user_id: str) -> dict[str, Any]:
    return OAUTH_TOKENS.setdefault(user_id, {})


def rate_limited(user_id: str, tool_name: str, now: float | None = None) -> bool:
    now = now or time_module.time()
    bucket = "send_self_alert" if tool_name == "send_self_alert" else OTHER_TOOL_RATE_KEY
    limit = SEND_SELF_ALERT_RATE_LIMIT if tool_name == "send_self_alert" else OTHER_TOOL_CALL_RATE_LIMIT
    key = (user_id, bucket)
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    recent = [stamp for stamp in RATE_LIMITS.get(key, []) if stamp > cutoff]
    if len(recent) >= limit:
        RATE_LIMITS[key] = recent
        return True
    recent.append(now)
    RATE_LIMITS[key] = recent
    return False


def duplicate_send_key(user_id: str, message: str) -> tuple[str, str]:
    return user_id, sha256(message.encode("utf-8")).hexdigest()


def duplicate_send_blocked(user_id: str, message: str, now: float | None = None) -> bool:
    now = now or time_module.time()
    last_sent = SENT_MESSAGE_GUARD.get(duplicate_send_key(user_id, message))
    return bool(last_sent and now - last_sent <= DUPLICATE_SEND_WINDOW_SECONDS)


def remember_sent_message(user_id: str, message: str, now: float | None = None) -> None:
    SENT_MESSAGE_GUARD[duplicate_send_key(user_id, message)] = now or time_module.time()


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


def delete_alert_area_db(label: str, user_id: str = DEFAULT_USER_ID) -> None:
    with db_connect() as conn:
        conn.execute("DELETE FROM alert_areas WHERE user_id = ? AND label = ?", (user_id, label))


def save_scheduled_alert(schedule: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> None:
    with db_connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO scheduled_alerts(user_id, label, data) VALUES (?, ?, ?)",
            (user_id, schedule["label"], json.dumps(schedule, ensure_ascii=False)),
        )


def delete_scheduled_alert_db(label: str, user_id: str = DEFAULT_USER_ID) -> None:
    with db_connect() as conn:
        conn.execute("DELETE FROM scheduled_alerts WHERE user_id = ? AND label = ?", (user_id, label))


def token_cipher() -> Any:
    key = env_value("TOKEN_ENCRYPTION_KEY")
    if not key:
        return None
    from cryptography.fernet import Fernet

    return Fernet(key.encode("utf-8"))


def encode_oauth_data(tokens: dict[str, Any]) -> str:
    raw = json.dumps(tokens, ensure_ascii=False)
    cipher = token_cipher()
    if not cipher:
        return raw
    return "fernet:" + cipher.encrypt(raw.encode("utf-8")).decode("utf-8")


def decode_oauth_data(data: str) -> dict[str, Any]:
    if not data.startswith("fernet:"):
        return json.loads(data)
    cipher = token_cipher()
    if not cipher:
        raise ValueError("TOKEN_ENCRYPTION_KEY is required to read OAuth tokens")
    return json.loads(cipher.decrypt(data.removeprefix("fernet:").encode("utf-8")).decode("utf-8"))


def save_oauth_tokens(tokens: dict[str, Any], user_id: str = DEFAULT_USER_ID) -> None:
    with db_connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO oauth_tokens(user_id, data) VALUES (?, ?)",
            (user_id, encode_oauth_data(tokens)),
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
            OAUTH_TOKENS[user_id] = decode_oauth_data(data)


def kakao_json(path: str, query: dict[str, str]) -> dict[str, Any]:
    key = env_value("KAKAO_REST_API_KEY")
    if not key:
        raise ValueError("KAKAO_REST_API_KEY is not configured")
    url = f"https://dapi.kakao.com{path}?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {key}"})
    with urllib.request.urlopen(req, timeout=10) as res:
        return json.loads(res.read().decode("utf-8"))


def kakao_mobility_json(path: str, query: dict[str, str]) -> dict[str, Any]:
    key = env_value("KAKAO_REST_API_KEY")
    if not key:
        raise ValueError("KAKAO_REST_API_KEY is not configured")
    url = f"https://apis-navi.kakaomobility.com{path}?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {key}"})
    with urllib.request.urlopen(req, timeout=10) as res:
        return json.loads(res.read().decode("utf-8"))


def odsay_json(path: str, query: dict[str, str]) -> dict[str, Any]:
    key = env_value("ODSAY_API_KEY")
    if not key:
        raise ValueError("ODSAY_API_KEY is not configured")
    url = f"https://api.odsay.com/v1/api{path}?{urllib.parse.urlencode({**query, 'apiKey': key})}"
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=30) as res:
                data = json.loads(res.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            try:
                data = json.loads(exc.read().decode("utf-8"))
                break
            except (UnicodeDecodeError, json.JSONDecodeError):
                last_error = exc
        except (TimeoutError, urllib.error.URLError) as exc:
            last_error = exc
        if attempt < 4:
            # ponytail: fixed delay; make it exponential only if ODsay rate-limits retries.
            time_module.sleep(2)
    else:
        raise last_error or urllib.error.URLError("ODsay API failed")
    if any("ApiKeyAuthFailed" in str(error.get("message", "")) for error in data.get("error") or []):
        raise ValueError("ODSAY_AUTH_FAILED")
    return data


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


def validate_radius(radius_m: Any, default: int = 1000) -> int:
    radius = int(radius_m or default)
    if radius < 100 or radius > 5000:
        raise ValueError("radius_m must be between 100 and 5000")
    return radius


def is_bare_road_name(query: str) -> bool:
    compact = "".join(query.split())
    return bool(compact) and not any(ch.isdigit() for ch in compact) and compact.endswith(("대로", "로", "길"))


def geocode_address(address: str) -> dict[str, Any]:
    if is_bare_road_name(address):
        raise ValueError(f"Address is too broad; use a more specific Seoul address or place name: {address}")
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


def region_for_coords(x: float, y: float, input_coord: str = "WGS84") -> dict[str, Any]:
    data = kakao_json(
        "/v2/local/geo/coord2regioncode.json",
        {"x": str(x), "y": str(y), "input_coord": input_coord},
    )
    for doc in data.get("documents") or []:
        if doc.get("region_type") == "H":
            return doc
    raise ValueError("No administrative dong for coordinate")


def admin_dong_for_text(district: str) -> dict[str, Any]:
    geo = geocode_address(district)
    region = region_for_coords(float(geo["x"]), float(geo["y"]))
    if region.get("region_1depth_name") not in {"서울", "서울특별시"}:
        raise ValueError("Only Seoul administrative dongs are supported")
    return {
        **geo,
        "address_name": region["address_name"],
        "region_code": region["code"],
        "region_1depth_name": region["region_1depth_name"],
        "region_2depth_name": region["region_2depth_name"],
        "region_3depth_name": region["region_3depth_name"],
    }


def admin_dong_for_issue(issue: dict[str, Any]) -> dict[str, Any]:
    x = float(issue["grs80tm_x"])
    y = float(issue["grs80tm_y"])
    key = (round(x), round(y))
    if key not in REGION_CACHE:
        REGION_CACHE[key] = region_for_coords(x, y, "TM")
    return REGION_CACHE[key]


def route_vertices(origin: dict[str, Any], destination: dict[str, Any]) -> list[tuple[float, float]]:
    try:
        data = kakao_mobility_json(
            "/v1/directions",
            {
                "origin": f"{origin['x']},{origin['y']}",
                "destination": f"{destination['x']},{destination['y']}",
                "priority": "RECOMMEND",
                "summary": "false",
            },
        )
    except (KeyError, urllib.error.URLError, ValueError):
        return []

    coords: list[tuple[float, float]] = []
    for route in data.get("routes") or []:
        for section in route.get("sections") or []:
            for road in section.get("roads") or []:
                values = road.get("vertexes") or []
                coords.extend((float(values[i]), float(values[i + 1])) for i in range(0, len(values) - 1, 2))
        if coords:
            break
    return coords


def route_points(origin: dict[str, Any], destination: dict[str, Any], samples: int = 10) -> list[dict[str, float]]:
    coords = route_vertices(origin, destination)
    if not coords:
        # ponytail: straight corridor fallback; replace with mandatory Mobility route if precision matters.
        coords = [
            (
                float(origin["x"]) + (float(destination["x"]) - float(origin["x"])) * i / (samples - 1),
                float(origin["y"]) + (float(destination["y"]) - float(origin["y"])) * i / (samples - 1),
            )
            for i in range(samples)
        ]

    step = max(1, len(coords) // samples)
    picked = coords[::step][:samples]
    if coords[-1] not in picked:
        picked.append(coords[-1])
    return [wgs84_to_tm(x, y, "route") for x, y in picked]


def transit_points(stops: list[str]) -> list[dict[str, Any]]:
    points = []
    for stop in stops[:20]:
        name = str(stop).strip()
        if not name:
            continue
        geo = geocode_address(name)
        points.append({"stop": name, "tm_x": geo["tm_x"], "tm_y": geo["tm_y"]})
    if not points:
        raise ValueError("stops must include at least one stop name")
    return points


def normalize_stop_names(values: list[Any]) -> list[str]:
    stops: list[str] = []
    seen: set[str] = set()
    for value in values:
        stop = str(value).strip()
        if stop and stop not in seen:
            stops.append(stop)
            seen.add(stop)
    return stops


def odsay_lane_name(lane: Any) -> str:
    lanes = lane if isinstance(lane, list) else [lane]
    names = []
    for item in lanes:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("busNo") or item.get("busNoKor") or "").strip()
        if name and name not in names:
            names.append(name)
    return "/".join(names) if names else "대중교통"


def odsay_station_name(name: Any, traffic_type: int, suffix: bool = False) -> str:
    text = str(name or "").strip()
    if suffix and traffic_type == 1 and text and not text.endswith("역"):
        return f"{text}역"
    return text


def odsay_segment_summary(segment: dict[str, Any], suffix: bool = False) -> str:
    traffic_type = int(segment.get("trafficType") or 0)
    lane = odsay_lane_name(segment.get("lane"))
    start = odsay_station_name(segment.get("startName"), traffic_type, suffix)
    end = odsay_station_name(segment.get("endName"), traffic_type, suffix)
    if suffix:
        return f"{lane} {start}부터 {end}까지"
    return f"{lane} {start}-{end}"


def odsay_transit_segments(path: dict[str, Any]) -> list[dict[str, Any]]:
    segments = []
    for segment in path.get("subPath") or []:
        if int(segment.get("trafficType") or 0) in (1, 2):
            segments.append(segment)
    return segments


def odsay_route_points(map_obj: str) -> list[dict[str, float]]:
    data = odsay_json("/loadLane", {"mapObject": map_obj if "@" in map_obj else f"0:0@{map_obj}"})
    points: list[dict[str, float]] = []
    for lane in (data.get("result") or {}).get("lane") or []:
        for section in lane.get("section") or []:
            for pos in section.get("graphPos") or []:
                tm = wgs84_to_tm(float(pos["x"]), float(pos["y"]), "odsay-route")
                points.append({"tm_x": tm["tm_x"], "tm_y": tm["tm_y"]})
    if not points:
        raise ValueError("ODsay route geometry is empty")
    return points


def odsay_segment_points(segments: list[dict[str, Any]]) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for segment in segments:
        stations = (segment.get("passStopList") or {}).get("stations") or []
        candidates = stations or [
            {"x": segment.get("startX"), "y": segment.get("startY")},
            {"x": segment.get("endX"), "y": segment.get("endY")},
        ]
        for item in candidates:
            try:
                tm = wgs84_to_tm(float(item["x"]), float(item["y"]), "odsay-route")
            except (KeyError, TypeError, ValueError):
                continue
            points.append({"tm_x": tm["tm_x"], "tm_y": tm["tm_y"]})
    return points


def build_transit_route_options(args: dict[str, Any]) -> list[dict[str, Any]]:
    origin = str(args["origin"]).strip()
    destination = str(args["destination"]).strip()
    if not origin or not destination:
        raise ValueError("origin and destination are required")
    if not env_value("ODSAY_API_KEY"):
        raise ValueError("ODSAY_API_KEY is not configured")

    origin_geo = geocode_address(origin)
    destination_geo = geocode_address(destination)
    data = odsay_json(
        "/searchPubTransPathT",
        {"SX": str(origin_geo["x"]), "SY": str(origin_geo["y"]), "EX": str(destination_geo["x"]), "EY": str(destination_geo["y"]), "OPT": "0"},
    )
    if any("ApiKeyAuthFailed" in str(error.get("message", "")) for error in data.get("error") or []):
        raise ValueError("ODSAY_AUTH_FAILED")

    options: list[dict[str, Any]] = []
    for index, path in enumerate(((data.get("result") or {}).get("path") or [])[:5], start=1):
        segments = odsay_transit_segments(path)
        if not segments:
            continue
        info = path.get("info") or {}
        map_obj = str(info.get("mapObj") or "").strip()
        if not map_obj:
            continue
        summary = ", ".join(odsay_segment_summary(segment) for segment in segments)
        options.append(
            {
                "route_id": str(index),
                "name": summary,
                "segments": segments,
                "map_obj": map_obj,
                "total_time": info.get("totalTime"),
                "payment": info.get("payment"),
            }
        )

    if not options:
        raise ValueError("route options must include at least one stop list")
    return options


def transit_route_options_text(options: list[dict[str, Any]]) -> str:
    lines = ["후보 대중교통 경로입니다."]
    for option in options:
        time_text = f" / 약 {option['total_time']}분" if option.get("total_time") is not None else ""
        lines.append(f"{option['route_id']}. {option['name']}{time_text}")
    lines.append("원하는 번호를 말하면 해당 경로를 등록할 수 있습니다.")
    return "\n".join(lines)


def selected_transit_points(options: list[dict[str, Any]], route_ids: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    wanted = {str(route_id).strip().removeprefix("route-") for route_id in route_ids if str(route_id).strip()}
    selected = [option for option in options if option["route_id"] in wanted]
    if not selected:
        raise ValueError("selected route ids were not found")

    points: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    selected_names: list[str] = []
    for option in selected:
        selected_names.extend(odsay_segment_summary(segment, suffix=True) for segment in option.get("segments") or [])
        try:
            route_points = odsay_route_points(option["map_obj"])
        except (urllib.error.URLError, ValueError):
            # ponytail: passStopList fallback keeps route selection usable when loadLane is unavailable.
            route_points = []
        route_points = route_points or odsay_segment_points(option.get("segments") or [])
        for point in route_points:
            key = (round(float(point["tm_x"])), round(float(point["tm_y"])))
            if key in seen:
                continue
            points.append(point)
            seen.add(key)
    return points, selected_names


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


def fetch_accinfo_cached(limit: int = 1000) -> list[dict[str, Any]]:
    now = time_module.time()
    cached_at = float(ACCINFO_CACHE.get("cached_at") or 0)
    if ACCINFO_CACHE.get("limit") == limit and now - cached_at <= ACCINFO_CACHE_TTL_SECONDS:
        return list(ACCINFO_CACHE["rows"])
    rows = fetch_accinfo(limit)
    ACCINFO_CACHE.update({"limit": limit, "cached_at": now, "rows": rows})
    return rows


def fetch_accinfo_retry(limit: int = 1000, attempts: int = 3) -> tuple[list[dict[str, Any]], int]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fetch_accinfo_cached(limit), attempt
        except (TimeoutError, urllib.error.URLError) as exc:
            last_error = exc
            # ponytail: no backoff; add one only if the public API starts rate-limiting retries.
    raise last_error or urllib.error.URLError("traffic API retry failed")


def point_distance_m(point: dict[str, Any], issue: dict[str, Any]) -> float | None:
    try:
        dx = float(point["tm_x"]) - float(issue["grs80tm_x"])
        dy = float(point["tm_y"]) - float(issue["grs80tm_y"])
    except (KeyError, TypeError, ValueError):
        return None
    return (dx * dx + dy * dy) ** 0.5


def segment_distance_m(a: dict[str, Any], b: dict[str, Any], issue: dict[str, Any]) -> float | None:
    try:
        ax, ay = float(a["tm_x"]), float(a["tm_y"])
        bx, by = float(b["tm_x"]), float(b["tm_y"])
        px, py = float(issue["grs80tm_x"]), float(issue["grs80tm_y"])
    except (KeyError, TypeError, ValueError):
        return None
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    x, y = ax + t * dx, ay + t * dy
    return ((px - x) ** 2 + (py - y) ** 2) ** 0.5


def distance_m(area: dict[str, Any], issue: dict[str, Any]) -> float | None:
    if area.get("area_type") == "admin_dong":
        try:
            return 0.0 if admin_dong_for_issue(issue).get("code") == area.get("region_code") else None
        except (KeyError, TypeError, ValueError):
            return None
    points = area.get("points")
    if isinstance(points, list) and points:
        if area.get("area_type") == "transit_route_polyline" and len(points) > 1:
            distances = [
                distance
                for a, b in zip(points, points[1:])
                if (distance := segment_distance_m(a, b, issue)) is not None
            ]
            return min(distances) if distances else None
        distances = [distance for point in points if (distance := point_distance_m(point, issue)) is not None]
        return min(distances) if distances else None
    return point_distance_m(area, issue)


def traffic_issue_lines(areas: list[dict[str, Any]], issues: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for area in areas:
        for issue in issues:
            distance = distance_m(area, issue)
            if distance is not None and distance <= int(area["radius_m"]):
                summary = issue.get("acc_info") or "교통 이슈"
                if area.get("area_type") == "admin_dong":
                    lines.append(f"- {area['label']} 행정동: {summary}")
                else:
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

    def date_value(name: str) -> str | None:
        value = str(args.get(name, "")).strip()
        if not value:
            return None
        datetime.fromisoformat(value)
        return value

    raw_skip_dates = args.get("skip_dates", [])
    if raw_skip_dates is None:
        raw_skip_dates = []
    if not isinstance(raw_skip_dates, list):
        raise ValueError("skip_dates must be a list")
    skip_dates = []
    for item in raw_skip_dates:
        value = str(item).strip()
        datetime.fromisoformat(value)
        skip_dates.append(value)

    interval_days = int(args.get("interval_days", 0) or 0)
    if interval_days < 0 or interval_days > 365:
        raise ValueError("interval_days must be between 1 and 365")
    start_date = date_value("start_date")
    end_date = date_value("end_date")
    pause_start_date = date_value("pause_start_date")
    pause_end_date = date_value("pause_end_date")
    if interval_days and not start_date:
        raise ValueError("start_date is required when interval_days is set")
    if start_date and end_date and datetime.fromisoformat(end_date) < datetime.fromisoformat(start_date):
        raise ValueError("end_date must be on or after start_date")
    if pause_start_date and pause_end_date and datetime.fromisoformat(pause_end_date) < datetime.fromisoformat(pause_start_date):
        raise ValueError("pause_end_date must be on or after pause_start_date")

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
        "skip_dates": skip_dates,
        "pause_start_date": pause_start_date,
        "pause_end_date": pause_end_date,
        "start_date": start_date,
        "end_date": end_date,
        "interval_days": interval_days,
    }


def schedule_due_on(schedule: dict[str, Any], local_now: datetime) -> bool:
    today = local_now.date()
    today_text = today.isoformat()
    if schedule.get("last_sent_date") == today_text:
        return False
    if today_text in set(schedule.get("skip_dates") or []):
        return False
    if start := schedule.get("start_date"):
        if today < datetime.fromisoformat(start).date():
            return False
    if end := schedule.get("end_date"):
        if today > datetime.fromisoformat(end).date():
            return False
    if pause_start := schedule.get("pause_start_date"):
        pause_end = schedule.get("pause_end_date") or pause_start
        if datetime.fromisoformat(pause_start).date() <= today <= datetime.fromisoformat(pause_end).date():
            return False
    if WEEKDAYS[local_now.weekday()] not in schedule["weekdays"]:
        return False
    if local_now.strftime("%H:%M") != schedule["time"]:
        return False
    interval_days = int(schedule.get("interval_days") or 0)
    if interval_days:
        anchor_text = schedule.get("start_date") or today_text
        if (today - datetime.fromisoformat(anchor_text).date()).days % interval_days:
            return False
    return True


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
                if not schedule_due_on(schedule, local_now):
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
    if rate_limited(user_id, name):
        return text_result(RATE_LIMIT_MESSAGE)

    areas = user_alert_areas(user_id)
    transit_options = user_transit_route_options(user_id)
    schedules = user_scheduled_alerts(user_id)

    if name == "set_alert_area":
        label = str(args["label"]).strip()
        address = str(args["address"]).strip()
        radius_m = validate_radius(args.get("radius_m"), 1000)
        if not label or not address:
            raise ValueError("label and address are required")
        try:
            geo = geocode_address(address)
        except urllib.error.URLError:
            return text_result("주소 조회를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.")
        except ValueError:
            return text_result("장소나 주소를 찾을 수 없습니다. 더 구체적으로 입력해 주세요.")
        areas[label] = {"label": label, "area_type": "point_circle", "address": address, "radius_m": radius_m, **geo}
        save_alert_area(areas[label], user_id)
        return text_result(f"Registered alert area '{label}' at {geo['address_name']} with radius {radius_m}m.")

    if name == "find_transit_route_options":
        label = str(args["label"]).strip()
        if not label:
            raise ValueError("label is required")
        try:
            options = build_transit_route_options(args)
        except urllib.error.URLError:
            return text_result("ODsay 대중교통 경로 API 응답이 지연되어 5번 재시도했지만 실패했습니다. 잠시 후 다시 시도해 주세요.")
        except ValueError as exc:
            if "ODSAY_API_KEY" in str(exc):
                return text_result("대중교통 경로 조회에는 ODSAY_API_KEY 설정이 필요합니다.")
            if "ODSAY_AUTH_FAILED" in str(exc):
                return text_result("ODsay API 인증에 실패했습니다. .env의 ODSAY_API_KEY가 Server API Key인지, ODsay 설정의 Server IP 허용 목록에 현재 호출 서버의 공인 IP가 들어있는지 확인해 주세요.")
            return text_result("대중교통 후보 경로를 만들 수 없습니다. 출발지와 도착지를 더 구체적으로 입력해 주세요.")
        transit_options[label] = options
        return text_result(transit_route_options_text(options))

    if name == "set_selected_transit_route_alert_area":
        label = str(args["label"]).strip()
        route_ids = args.get("route_ids")
        radius_m = validate_radius(args.get("radius_m"), 500)
        if not label or not isinstance(route_ids, list) or not route_ids:
            raise ValueError("label and route_ids are required")
        options = transit_options.get(label)
        if not options:
            return text_result("먼저 find_transit_route_options로 후보 경로를 조회해 주세요.")
        try:
            points, selected_names = selected_transit_points(options, route_ids)
            selected_number = str(route_ids[0]).strip().removeprefix("route-")
        except ValueError:
            return text_result("선택한 route_id를 찾을 수 없습니다. 후보 목록의 route_id를 그대로 선택해 주세요.")
        area = {
            "label": label,
            "area_type": "transit_route_polyline",
            "address": ", ".join(selected_names),
            "address_name": ", ".join(selected_names),
            "radius_m": radius_m,
            "tm_x": points[0]["tm_x"],
            "tm_y": points[0]["tm_y"],
            "points": points,
        }
        areas[label] = area
        save_alert_area(area, user_id)
        return text_result(f"{selected_number}번 경로를 {label}로 등록했습니다. {', '.join(selected_names)}가 등록되었습니다.")

    if name == "list_alert_areas":
        if not areas:
            return text_result("No alert areas registered.")
        lines = [
            f"- {area['label']}: {area.get('address_name') or area['address']} ({area.get('area_type', 'point_circle')}, {area['radius_m']}m)"
            for area in areas.values()
        ]
        return text_result("\n".join(lines))

    if name == "delete_alert_area":
        label = str(args["label"]).strip()
        if not label:
            raise ValueError("label is required")
        areas.pop(label, None)
        delete_alert_area_db(label, user_id)
        return text_result(f"Deleted alert area '{label}'.")

    if name == "check_traffic_issues":
        label = args.get("label")
        if label and label not in areas:
            return text_result(f"No alert area named '{label}'.")
        if not areas:
            return text_result("No alert areas registered.")
        selected_areas = [areas[label]] if label else list(areas.values())
        try:
            issues, attempt = fetch_accinfo_retry()
            matches = traffic_issue_lines(selected_areas, issues)
        except ValueError:
            return text_result("교통 정보 조회를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.")
        except (TimeoutError, urllib.error.URLError):
            return text_result("교통 정보 API 응답이 지연되어 3번 재시도했지만 실패했습니다. 잠시 후 다시 시도해 주세요.")
        prefix = "교통 정보 API 응답 지연으로 재시도 후 조회했습니다.\n" if attempt > 1 else ""
        if not matches:
            return text_result(prefix + "등록 지역 주변 확인된 교통 이슈 없음")
        return text_result(prefix + "\n".join(matches))

    if name == "send_self_alert":
        if args.get("dry_run", True):
            return text_result("Dry run only. Set dry_run=false after OAuth is connected.")
        message = str(args["message"]).strip()
        if not message:
            raise ValueError("message is required")
        if duplicate_send_blocked(user_id, message):
            return text_result(DUPLICATE_SEND_MESSAGE)
        try:
            send_kakao_self_message(message, user_id)
            remember_sent_message(user_id, message)
            return text_result("Sent alert to your KakaoTalk chat.")
        except ValueError as exc:
            message_text = str(exc)
            if message_text.startswith("OAuth required."):
                return text_result(message_text)
            return text_result("알림 전송에 실패했습니다. OAuth를 다시 연결하거나 잠시 후 다시 시도해 주세요.")
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
        except Exception:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": GENERIC_TOOL_ERROR}}

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
            try:
                user_id = user_id_from_headers(self.headers)
            except UserIdentityRequired:
                self.send_json({"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": "User identity is required."}}, status=401)
                return
            length = int(self.headers.get("content-length", "0"))
            if length > MAX_REQUEST_BYTES:
                self.send_json({"error": "request too large"}, status=413)
                return
            payload = json.loads(self.rfile.read(length) or b"{}")
            if isinstance(payload, list):
                if len(payload) > MAX_BATCH_REQUESTS:
                    self.send_json({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": BATCH_TOO_LARGE_ERROR}}, status=400)
                    return
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
        except Exception:
            self.send_json({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": GENERIC_REQUEST_ERROR}}, status=400)

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
