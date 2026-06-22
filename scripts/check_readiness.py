#!/usr/bin/env python3
from __future__ import annotations

import http.client
import json
import os
import urllib.parse


READY_URL = os.environ.get("READY_URL", "http://127.0.0.1:8000/ready")
REQUIRED_ENV_VARS = ("KAKAO_REST_API_KEY", "KAKAO_REDIRECT_URI", "SEOUL_OPENAPI_KEY")


def get_json(url: str) -> tuple[int, dict]:
    parsed = urllib.parse.urlparse(url)
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    conn = conn_cls(parsed.hostname, port, timeout=10)
    path = parsed.path or "/ready"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    conn.request("GET", path)
    res = conn.getresponse()
    data = res.read()
    conn.close()
    return res.status, json.loads(data.decode("utf-8"))


def main() -> None:
    status, payload = get_json(READY_URL)
    checks = payload.get("checks", {})
    env = checks.get("environment", {})

    assert status == 200, (status, payload)
    assert payload.get("status") == "ok", payload
    assert checks.get("database") is True, payload
    assert checks.get("oauth_callback") is True, payload
    assert checks.get("missing_required") == [], payload
    for name in REQUIRED_ENV_VARS:
        assert env.get(name) is True, payload

    print("ready ok")


if __name__ == "__main__":
    main()
