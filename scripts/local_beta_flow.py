#!/usr/bin/env python3
from __future__ import annotations

import http.client
import json
import os
import urllib.parse


MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:8000/mcp")
BETA_USER_ID = os.environ.get("BETA_USER_ID", "beta-local")
AREA_LABEL = os.environ.get("BETA_AREA_LABEL", "demo_commute")
AREA_ADDRESS = os.environ.get("BETA_AREA_ADDRESS", "서울특별시 중구 세종대로 110")
AREA_RADIUS_M = int(os.environ.get("BETA_AREA_RADIUS_M", "1000"))


def rpc(method: str, params: dict | None = None, request_id: int = 1) -> dict:
    parsed = urllib.parse.urlparse(MCP_URL)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=20)
    body = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}).encode()
    conn.request(
        "POST",
        parsed.path or "/mcp",
        body=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "X-PlayMCP-User-Id": BETA_USER_ID,
        },
    )
    res = conn.getresponse()
    data = res.read()
    conn.close()
    assert res.status == 200, (method, res.status, data.decode("utf-8", "replace"))
    payload = json.loads(data)
    assert "error" not in payload, payload
    return payload["result"]


def call_tool(name: str, arguments: dict | None = None, request_id: int = 1) -> str:
    result = rpc("tools/call", {"name": name, "arguments": arguments or {}}, request_id)
    return result["content"][0]["text"]


def main() -> None:
    rpc("initialize")
    registered = call_tool(
        "set_alert_area",
        {"label": AREA_LABEL, "address": AREA_ADDRESS, "radius_m": AREA_RADIUS_M},
        2,
    )
    listed = call_tool("list_alert_areas", {}, 3)
    issues = call_tool("check_traffic_issues", {"label": AREA_LABEL}, 4)
    dry_run = call_tool("send_self_alert", {"message": f"[서울 교통 이슈 알리미]\n{issues.splitlines()[0]}", "dry_run": True}, 5)

    assert AREA_LABEL in registered
    assert AREA_LABEL in listed
    assert "Dry run only" in dry_run
    print("local beta flow ok")
    print(issues)


if __name__ == "__main__":
    main()
