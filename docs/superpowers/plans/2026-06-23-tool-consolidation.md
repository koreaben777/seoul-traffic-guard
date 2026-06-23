# Tool Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the public PlayMCP tool surface from 15 tools to 10 submission-facing tools while preserving the core demo flow.

**Architecture:** Keep the existing single-file server shape. Do not add a router or abstraction layer. Shrink `TOOLS`, delete public dispatch branches for removed tools, and keep `set_alert_area` limited to address/place radius registration.

**Tech Stack:** Python stdlib HTTP server, in-memory + SQLite state in `server.py`, assert-style tests in `test_server.py`.

---

## Current Review

Current public tools in `server.py`:

1. `set_alert_area`
2. `list_alert_areas`
3. `delete_alert_area`
4. `set_route_alert_area`
5. `set_transit_route_alert_area`
6. `find_transit_route_options`
7. `set_selected_transit_route_alert_area`
8. `set_district_alert_area`
9. `set_alert_areas`
10. `check_traffic_issues`
11. `preview_alert_message`
12. `send_self_alert`
13. `set_scheduled_alert`
14. `list_scheduled_alerts`
15. `delete_scheduled_alert`

Target submission tools:

1. `set_alert_area`
2. `list_alert_areas`
3. `delete_alert_area`
4. `find_transit_route_options`
5. `set_selected_transit_route_alert_area`
6. `check_traffic_issues`
7. `send_self_alert`
8. `set_scheduled_alert`
9. `list_scheduled_alerts`
10. `delete_scheduled_alert`

Removed from public surface:

- `set_route_alert_area`: drop for submission; ODsay transit path is the stronger route story.
- `set_transit_route_alert_area`: replaced by ODsay route candidate selection.
- `set_district_alert_area`: remove for submission; administrative-dong whole-area registration is out of scope.
- `set_alert_areas`: repeated `set_alert_area` calls are good enough.
- `preview_alert_message`: use `send_self_alert` with `dry_run=true`.

---

### Task 1: Lock The 10-Tool Contract In Tests

**Files:**
- Modify: `/Users/june_kim/Documents/PlayMCP/test_server.py`

- [ ] **Step 1: Update `test_tool_contract` expected names**

Replace the expected list in `test_tool_contract` with:

```python
    assert names == [
        "set_alert_area",
        "list_alert_areas",
        "delete_alert_area",
        "find_transit_route_options",
        "set_selected_transit_route_alert_area",
        "check_traffic_issues",
        "send_self_alert",
        "set_scheduled_alert",
        "list_scheduled_alerts",
        "delete_scheduled_alert",
    ]
```

- [ ] **Step 2: Update `test_rpc_flow` tool count**

Change:

```python
    assert len(listed) == 15
```

to:

```python
    assert len(listed) == 10
```

- [ ] **Step 3: Run the test and verify it fails before implementation**

Run:

```bash
python3 test_server.py
```

Expected: FAIL because `TOOLS` still exposes 15 tools.

---

### Task 2: Drop Administrative Dong Registration

**Files:**
- Modify: `/Users/june_kim/Documents/PlayMCP/server.py`
- Modify: `/Users/june_kim/Documents/PlayMCP/test_server.py`

- [ ] **Step 1: Delete the district-specific test**

Delete this test from `/Users/june_kim/Documents/PlayMCP/test_server.py`:

```python
test_set_district_alert_area_registers_area
```

Also remove this `__main__` call:

```python
    test_set_district_alert_area_registers_area()
```

- [ ] **Step 2: Keep `set_alert_area` schema address-radius only**

Do not add `area_type`. The `set_alert_area` input schema should remain:

```python
            "properties": {
                "label": {"type": "string", "description": "User-facing area label, for example home, work, or school."},
                "address": {"type": "string", "description": "Seoul address or place keyword, for example 서울시청 or 을지로입구역."},
                "radius_m": {"type": "integer", "minimum": 100, "maximum": 5000, "default": 1000},
            },
            "required": ["label", "address"],
```

- [ ] **Step 3: Keep `set_alert_area` implementation address-radius only**

The `if name == "set_alert_area":` branch should keep this shape:

```python
        try:
            geo = geocode_address(address)
        except urllib.error.URLError:
            return text_result("주소 조회를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.")
        except ValueError:
            return text_result("장소나 주소를 찾을 수 없습니다. 더 구체적으로 입력해 주세요.")
        areas[label] = {"label": label, "area_type": "point_circle", "address": address, "radius_m": radius_m, **geo}
        save_alert_area(areas[label], user_id)
        return text_result(f"Registered alert area '{label}' at {geo['address_name']} with radius {radius_m}m.")
```

- [ ] **Step 4: Run the test**

Run:

```bash
python3 test_server.py
```

Expected: FAIL because `TOOLS` still exposes the removed public tools until Task 3.

---

### Task 3: Remove Redundant Public Tools

**Files:**
- Modify: `/Users/june_kim/Documents/PlayMCP/server.py`
- Modify: `/Users/june_kim/Documents/PlayMCP/test_server.py`

- [ ] **Step 1: Delete five tool schema entries from `TOOLS`**

Remove these dictionaries from `TOOLS`:

```python
"set_route_alert_area"
"set_transit_route_alert_area"
"set_district_alert_area"
"set_alert_areas"
"preview_alert_message"
```

- [ ] **Step 2: Delete matching `call_tool` branches**

Remove these branches from `call_tool`:

```python
    if name == "set_route_alert_area":
        ...

    if name == "set_transit_route_alert_area":
        ...

    if name == "set_district_alert_area":
        ...

    if name == "set_alert_areas":
        ...

    if name == "preview_alert_message":
        ...
```

Do not delete helper functions in this task. They can be removed later only if `rg` proves they are unused.

- [ ] **Step 3: Remove obsolete tests and `__main__` calls**

Delete these tests from `/Users/june_kim/Documents/PlayMCP/test_server.py`:

```python
test_set_route_alert_area_matches_issue_near_route_point
test_set_transit_route_alert_area_matches_station_issue
test_set_alert_areas_registers_multiple_places
```

Remove these `__main__` calls:

```python
    test_set_route_alert_area_matches_issue_near_route_point()
    test_set_transit_route_alert_area_matches_station_issue()
    test_set_alert_areas_registers_multiple_places()
```

- [ ] **Step 4: Verify removed names are gone from public tests**

Run:

```bash
rg -n "set_route_alert_area|set_transit_route_alert_area|set_district_alert_area|set_alert_areas|preview_alert_message" server.py test_server.py
```

Expected: no matches for tool schema names or dispatch branches. Helper function names like `route_points` may remain.

- [ ] **Step 5: Run full self-check**

Run:

```bash
python3 test_server.py
```

Expected: `ok`.

---

### Task 4: Update Docs To Match 10 Tools

**Files:**
- Modify: `/Users/june_kim/Documents/PlayMCP/README.md`
- Modify: `/Users/june_kim/Documents/PlayMCP/docs/agentic_player_10_submission_plan.md`
- Modify: `/Users/june_kim/Documents/PlayMCP/docs/playmcp_deployment_checklist.md`

- [ ] **Step 1: Update README tool table**

The README `## Tools` table should list exactly:

```markdown
| `set_alert_area` | Register or update a point-radius alert area from a Seoul address or place keyword. |
| `list_alert_areas` | List the current user's alert areas. |
| `delete_alert_area` | Delete an alert area by label. |
| `find_transit_route_options` | Find selectable public-transit route candidates with ODsay. |
| `set_selected_transit_route_alert_area` | Register the route candidate selected by the user. |
| `check_traffic_issues` | Check Seoul traffic issues near the current user's registered areas. |
| `send_self_alert` | Send a prepared alert to the current user's own KakaoTalk chat. |
| `set_scheduled_alert` | Create or update a scheduled traffic alert. |
| `list_scheduled_alerts` | List scheduled traffic alerts. |
| `delete_scheduled_alert` | Delete a scheduled traffic alert. |
```

- [ ] **Step 2: Update submission plan counts**

In `/Users/june_kim/Documents/PlayMCP/docs/agentic_player_10_submission_plan.md`, replace text saying current implementation exposes 15 tools with:

```markdown
현재 제출용 구현은 PlayMCP 권장 범위에 맞춰 10개 tool만 노출한다.
```

Update the tool classification and current tool contract tables to the same 10-tool list from Step 1.

- [ ] **Step 3: Update checklist**

In `/Users/june_kim/Documents/PlayMCP/docs/playmcp_deployment_checklist.md`, replace the tool-count review item with:

```markdown
- [ ] Tool count is 10 and stays within the PlayMCP recommended 3-10 range.
```

- [ ] **Step 4: Search for stale counts**

Run:

```bash
rg -n "15개|15-tool|set_route_alert_area|set_transit_route_alert_area|set_district_alert_area|set_alert_areas|preview_alert_message" README.md docs
```

Expected: no stale public-tool claims. Historical notes may remain only if explicitly marked as old history.

---

### Task 5: Final Verification

**Files:**
- Check: `/Users/june_kim/Documents/PlayMCP/server.py`
- Check: `/Users/june_kim/Documents/PlayMCP/test_server.py`
- Check: `/Users/june_kim/Documents/PlayMCP/README.md`
- Check: `/Users/june_kim/Documents/PlayMCP/docs/agentic_player_10_submission_plan.md`
- Check: `/Users/june_kim/Documents/PlayMCP/docs/playmcp_deployment_checklist.md`

- [ ] **Step 1: Run self-check**

Run:

```bash
python3 test_server.py
```

Expected: `ok`.

- [ ] **Step 2: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 3: Confirm public tool count from code**

Run:

```bash
python3 - <<'PY'
import server
print(len(server.TOOLS))
print([tool["name"] for tool in server.TOOLS])
PY
```

Expected output:

```text
10
['set_alert_area', 'list_alert_areas', 'delete_alert_area', 'find_transit_route_options', 'set_selected_transit_route_alert_area', 'check_traffic_issues', 'send_self_alert', 'set_scheduled_alert', 'list_scheduled_alerts', 'delete_scheduled_alert']
```

- [ ] **Step 4: Review changed files**

Run:

```bash
git status --short
git diff --stat
```

Expected: only intended files changed. Do not push unless the user explicitly asks.

---

## Self-Review

Spec coverage:

- Current tool review is included.
- Public tool count goes from 15 to 10.
- Administrative-dong whole-area registration is deliberately removed.
- ODsay candidate/selection flow remains available.
- KakaoTalk send and scheduled alert flow remain available.

Deliberate simplification:

- Road corridor registration is removed from the submission surface. Add it back only if the final demo explicitly needs non-transit driving or walking route monitoring.
- Manual station/stop route registration is removed. ODsay selected route is more accurate and less ambiguous.
- Administrative-dong whole-area registration is removed. Address-radius registration is simpler and enough for the submission demo.
- Multi-area registration is removed. Repeated `set_alert_area` calls are simpler and keep the tool contract smaller.

Plan complete and saved to `docs/superpowers/plans/2026-06-23-tool-consolidation.md`. Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks.
2. Inline Execution - execute tasks in this session using executing-plans, with checkpoints.
