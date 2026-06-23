#!/usr/bin/env python3
from __future__ import annotations

import http.client
import json
import os
import urllib.parse


MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:8000/mcp")


def request(method: str, path: str, body: object | None = None, headers: dict[str, str] | None = None):
    parsed = urllib.parse.urlparse(MCP_URL)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=10)
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    conn.request(method, path, body=payload, headers=headers or {})
    res = conn.getresponse()
    data = res.read()
    conn.close()
    return res.status, dict(res.getheaders()), data


def rpc(method: str, params: dict | None = None, request_id: int = 1):
    parsed = urllib.parse.urlparse(MCP_URL)
    status, headers, data = request(
        "POST",
        parsed.path or "/mcp",
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
        {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    )
    assert status == 200, (method, status, data.decode("utf-8", "replace"))
    return json.loads(data)


def main() -> None:
    parsed = urllib.parse.urlparse(MCP_URL)

    status, _, data = request("GET", parsed.path or "/mcp", headers={"Accept": "text/event-stream"})
    assert status == 405, ("GET /mcp should be 405 when SSE is not supported", status, data)

    status, _, data = request(
        "POST",
        parsed.path or "/mcp",
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    )
    assert status == 202 and data == b"", ("notification-only POST should be 202 empty", status, data)

    initialized = rpc("initialize")["result"]
    assert initialized["protocolVersion"] == "2025-03-26"
    assert initialized["serverInfo"]["name"] == "seoul-traffic-guard"

    tools = rpc("tools/list")["result"]["tools"]
    names = [tool["name"] for tool in tools]
    assert {"set_alert_area", "list_alert_areas", "check_traffic_issues"} <= set(names), names
    assert all("kakao" not in name.lower() for name in names), names
    assert all("annotations" in tool for tool in tools), names

    result = rpc("tools/call", {"name": "list_alert_areas", "arguments": {}})["result"]
    assert result["content"][0]["type"] == "text"

    print("mcp smoke ok")


if __name__ == "__main__":
    main()
