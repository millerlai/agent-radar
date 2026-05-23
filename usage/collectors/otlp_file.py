"""Offline collector: reads OTel console exporter output from a log file.

Why this is the MVP: a user can opt into telemetry with

    export CLAUDE_CODE_ENABLE_TELEMETRY=1
    export OTEL_LOGS_EXPORTER=console
    export OTEL_METRICS_EXPORTER=console
    export OTEL_LOG_TOOL_DETAILS=1
    claude 2>> ~/.agent-radar/otel-events.log

and then point this collector at the file. Zero backend dependency.

Format tolerance
----------------
Real-world console exporters emit different shapes depending on language and
version. We accept three:

  1. Flat normalised (what our fixtures use; easiest to author by hand):
       {"event_name": "claude_code.skill_activated",
        "attributes": {"skill.name": "foo", "invocation_trigger": "user-slash", ...}}
       {"metric": "claude_code.session.count", "value": 1,
        "attributes": {...}}

  2. OTel LogRecord JSON (Python/Node SDK ConsoleLogExporter):
       {"body": "claude_code.skill_activated",
        "attributes": {...}, "resource": {...}}

  3. OTel ResourceMetrics JSON (Python SDK ConsoleMetricExporter):
       {"resource_metrics": [{"scope_metrics": [{"metrics": [{"name": ...,
        "data": {"data_points": [{"value": 1, "attributes": {...}}]}}]}]}]}

Anything that doesn't parse / doesn't match is silently skipped — this collector
is meant to digest noisy real-world logs without aborting.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .base import (
    UsageWindow,
    bump,
    ensure_hook,
    ensure_mcp,
    ensure_mention,
    ensure_skill,
)


_EVENT_PREFIX = "claude_code."


# ---------------------------------------------------------------------------
# normalisation: any input shape → (kind, name, attrs, value_for_metrics)
# ---------------------------------------------------------------------------

def _normalise(line_obj: dict):
    """Yield (kind, name, attrs, value) tuples.

    kind ∈ {"event", "metric"}; for events `value` is None.
    A single line may yield multiple records (ResourceMetrics wrappers do).
    """
    if not isinstance(line_obj, dict):
        return

    # ---- flat shapes ----
    if "event_name" in line_obj:
        name = line_obj.get("event_name")
        if isinstance(name, str) and name.startswith(_EVENT_PREFIX):
            attrs = line_obj.get("attributes") or {}
            if isinstance(attrs, dict):
                yield "event", name, attrs, None
        return

    if "metric" in line_obj:
        name = line_obj.get("metric")
        if isinstance(name, str) and name.startswith(_EVENT_PREFIX):
            attrs = line_obj.get("attributes") or {}
            value = line_obj.get("value", 0)
            if isinstance(attrs, dict):
                yield "metric", name, attrs, value
        return

    # ---- OTel LogRecord shape (event = log record with name in body) ----
    if "body" in line_obj or "attributes" in line_obj:
        body = line_obj.get("body")
        attrs = line_obj.get("attributes") or {}
        name = None
        if isinstance(body, str) and body.startswith(_EVENT_PREFIX):
            name = body
        elif isinstance(body, dict):
            # OTLP/JSON encoding sometimes wraps in {"string_value": "..."}
            sv = body.get("string_value") or body.get("stringValue")
            if isinstance(sv, str) and sv.startswith(_EVENT_PREFIX):
                name = sv
        if name is None and isinstance(attrs, dict):
            evn = attrs.get("event.name")
            if isinstance(evn, str) and evn.startswith(_EVENT_PREFIX):
                name = evn
        if name and isinstance(attrs, dict):
            yield "event", name, attrs, None
        # fall through to also try metrics inside same payload — unusual but cheap

    # ---- OTel ResourceMetrics shape ----
    rms = line_obj.get("resource_metrics") or line_obj.get("resourceMetrics")
    if isinstance(rms, list):
        for rm in rms:
            sms = (rm or {}).get("scope_metrics") or (rm or {}).get("scopeMetrics") or []
            for sm in sms:
                metrics = (sm or {}).get("metrics") or []
                for m in metrics:
                    mname = m.get("name")
                    if not (isinstance(mname, str) and mname.startswith(_EVENT_PREFIX)):
                        continue
                    data = m.get("data") or {}
                    points = (
                        data.get("data_points") or data.get("dataPoints")
                        or m.get("data_points") or []
                    )
                    for pt in points:
                        attrs = pt.get("attributes") or {}
                        # attributes from OTLP JSON come as list-of-kv pairs
                        if isinstance(attrs, list):
                            attrs = _kv_list_to_dict(attrs)
                        if not isinstance(attrs, dict):
                            attrs = {}
                        value = (
                            pt.get("as_int") or pt.get("asInt")
                            or pt.get("as_double") or pt.get("asDouble")
                            or pt.get("value") or 0
                        )
                        try:
                            value = float(value)
                        except Exception:
                            value = 0.0
                        yield "metric", mname, attrs, value


def _kv_list_to_dict(kv: list) -> dict:
    """OTLP JSON encodes attributes as [{"key": k, "value": {"stringValue": v}}, ...]."""
    out = {}
    for item in kv:
        if not isinstance(item, dict):
            continue
        k = item.get("key")
        v = item.get("value")
        if not isinstance(k, str):
            continue
        if isinstance(v, dict):
            # pick the first concrete typed value
            for tv in ("stringValue", "string_value", "intValue", "int_value",
                       "doubleValue", "double_value", "boolValue", "bool_value"):
                if tv in v:
                    out[k] = v[tv]
                    break
            else:
                out[k] = v
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# per-event handlers
# ---------------------------------------------------------------------------

def _handle_skill_activated(w: UsageWindow, attrs: dict) -> None:
    name = attrs.get("skill.name") or attrs.get("skill_name") or "<unknown>"
    bucket = ensure_skill(w, name)
    bucket["total"] += 1
    trig = attrs.get("invocation_trigger") or "unknown"
    bump(bucket["triggers"], trig)
    src = attrs.get("skill.source") or attrs.get("skill_source")
    if src:
        bump(bucket["sources"], src)


def _handle_mcp_connection(w: UsageWindow, attrs: dict) -> None:
    name = attrs.get("server_name") or attrs.get("mcp_server_name") or "<unknown>"
    bucket = ensure_mcp(w, name)
    status = attrs.get("status")
    if status in ("connected", "failed", "disconnected"):
        bucket[status] += 1
    transport = attrs.get("transport_type")
    if transport:
        bump(bucket["transports"], transport)


def _handle_plugin_loaded(w: UsageWindow, attrs: dict) -> None:
    name = attrs.get("plugin.name") or attrs.get("plugin_name") or "<unknown>"
    bump(w.plugins, name)


def _handle_hook_registered(w: UsageWindow, attrs: dict) -> None:
    event = attrs.get("hook_event") or attrs.get("event") or "<unknown>"
    ensure_hook(w, event)["registered"] += 1


def _handle_hook_executed(w: UsageWindow, attrs: dict) -> None:
    # hook_execution_complete doesn't always carry hook_event — fall back to a
    # synthetic bucket so totals still count.
    event = attrs.get("hook_event") or attrs.get("event") or "*"
    bucket = ensure_hook(w, event)
    bucket["executed"] += int(attrs.get("num_success", 1) or 1)
    bucket["blocking"] += int(attrs.get("num_blocking", 0) or 0)
    bucket["errors"] += int(attrs.get("num_non_blocking_error", 0) or 0)
    try:
        bucket["duration_ms"] += int(attrs.get("total_duration_ms", 0) or 0)
    except (TypeError, ValueError):
        pass


def _handle_at_mention(w: UsageWindow, attrs: dict) -> None:
    mtype = attrs.get("mention_type") or "unknown"
    bucket = ensure_mention(w, mtype)
    if attrs.get("success") in (True, "true", 1, "1"):
        bucket["success"] += 1
    else:
        bucket["fail"] += 1


def _handle_tool_decision(w: UsageWindow, attrs: dict) -> None:
    decision = attrs.get("decision")
    if decision == "accept":
        w.decisions["accept"] += 1
    elif decision == "reject":
        w.decisions["reject"] += 1
    src = attrs.get("source")
    if src:
        bump(w.decisions["by_source"], src)


def _handle_tool_result(w: UsageWindow, attrs: dict) -> None:
    """Captures MCP server invocation (counts toward servers_invoked) and
    subagent dispatch (Task tool with subagent_type)."""
    tool = attrs.get("tool_name")
    if tool and tool.startswith("mcp__"):
        # mcp__<server>__<tool>
        parts = tool.split("__", 2)
        if len(parts) >= 2:
            w.mcp_invoked.add(parts[1])
    params = attrs.get("tool_parameters") or {}
    if isinstance(params, dict):
        srv = params.get("mcp_server_name")
        if srv:
            w.mcp_invoked.add(srv)
        sub = params.get("subagent_type")
        if sub:
            w.subagents.add(sub)


_EVENT_HANDLERS = {
    "claude_code.skill_activated": _handle_skill_activated,
    "claude_code.mcp_server_connection": _handle_mcp_connection,
    "claude_code.plugin_loaded": _handle_plugin_loaded,
    "claude_code.hook_registered": _handle_hook_registered,
    "claude_code.hook_execution_complete": _handle_hook_executed,
    "claude_code.at_mention": _handle_at_mention,
    "claude_code.tool_decision": _handle_tool_decision,
    "claude_code.tool_result": _handle_tool_result,
}


# ---------------------------------------------------------------------------
# per-metric handlers
# ---------------------------------------------------------------------------

def _handle_metric(w: UsageWindow, name: str, attrs: dict, value: float) -> None:
    if name == "claude_code.session.count":
        w.session_count += int(value or 0)
    elif name == "claude_code.active_time.total":
        w.active_seconds += float(value or 0)
    elif name == "claude_code.token.usage":
        skill = attrs.get("skill.name")
        plugin = attrs.get("plugin.name")
        agent = attrs.get("agent.name")
        if skill:
            w.token_by_skill[skill] = w.token_by_skill.get(skill, 0) + value
        if plugin:
            w.token_by_plugin[plugin] = w.token_by_plugin.get(plugin, 0) + value
        if agent:
            w.token_by_agent[agent] = w.token_by_agent.get(agent, 0) + value
            w.subagents.add(agent)
    elif name == "claude_code.cost.usage":
        skill = attrs.get("skill.name")
        plugin = attrs.get("plugin.name")
        agent = attrs.get("agent.name")
        if skill:
            w.cost_by_skill[skill] = w.cost_by_skill.get(skill, 0) + value
        if plugin:
            w.cost_by_plugin[plugin] = w.cost_by_plugin.get(plugin, 0) + value
        if agent:
            w.cost_by_agent[agent] = w.cost_by_agent.get(agent, 0) + value


# ---------------------------------------------------------------------------
# main collector
# ---------------------------------------------------------------------------

# `claude` may interleave its own stderr lines with JSON. We extract any JSON
# object embedded in a line so noisy logs still parse.
_JSON_OBJECT_RE = re.compile(r"\{.*\}")


class OTLPFileCollector:
    """Reads a file (one OTel record per line) and yields a UsageWindow."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def fetch(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        account_filter: str | None = None,
    ) -> UsageWindow:
        since = since or datetime.fromtimestamp(0, tz=timezone.utc)
        until = until or datetime.now(tz=timezone.utc)
        w = UsageWindow(since=since, until=until)

        observed_sessions: set[str] = set()
        seen_tool_details = False

        if not self.path.exists():
            w.notes.append(f"OTel log file not found: {self.path}")
            return w

        with self.path.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = self._parse_line(line)
                if obj is None:
                    continue

                for kind, name, attrs, value in _normalise(obj):
                    if account_filter and not self._account_matches(attrs, account_filter):
                        continue
                    sid = attrs.get("session.id")
                    if isinstance(sid, str):
                        observed_sessions.add(sid)
                    # presence of detail attrs implies OTEL_LOG_TOOL_DETAILS=1
                    if any(k in attrs for k in (
                            "skill.name", "skill_name",
                            "server_name", "mcp_server_name", "tool_parameters")):
                        seen_tool_details = True

                    if kind == "event":
                        handler = _EVENT_HANDLERS.get(name)
                        if handler:
                            handler(w, attrs)
                    elif kind == "metric":
                        _handle_metric(w, name, attrs, value)

        # session.count metric is authoritative; fall back to distinct session.id
        # observed across events when the metric isn't present.
        if w.session_count == 0 and observed_sessions:
            w.session_count = len(observed_sessions)

        if not seen_tool_details:
            w.notes.append(
                "OTEL_LOG_TOOL_DETAILS=1 not detected in events; skill / MCP "
                "names may be redacted. Re-export with detail flag for precise "
                "attribution.")

        return w

    @staticmethod
    def _parse_line(line: str):
        # Fast path: whole line is JSON.
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            pass
        # Fallback: extract first JSON object embedded in the line.
        m = _JSON_OBJECT_RE.search(line)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _account_matches(attrs: dict, account_filter: str) -> bool:
        for k in ("user.account_uuid", "user.account_id", "user.email"):
            if attrs.get(k) == account_filter:
                return True
        return False
