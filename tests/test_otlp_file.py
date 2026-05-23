"""Unit tests for agent_radar.usage.collectors.otlp_file."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agent_radar.usage.collectors.otlp_file import (
    OTLPFileCollector,
    _kv_list_to_dict,
    _normalise,
)


def _write_log(path: Path, lines: list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for ln in lines:
            f.write(json.dumps(ln) + "\n")
    return path


# ---------------------------------------------------------------------------
# _normalise — shape tolerance
# ---------------------------------------------------------------------------

class TestNormalise:
    def test_flat_event(self):
        obj = {"event_name": "claude_code.skill_activated",
               "attributes": {"skill.name": "x"}}
        result = list(_normalise(obj))
        assert result == [("event", "claude_code.skill_activated",
                          {"skill.name": "x"}, None)]

    def test_flat_metric(self):
        obj = {"metric": "claude_code.session.count", "value": 3,
               "attributes": {}}
        kind, name, attrs, value = next(iter(_normalise(obj)))
        assert kind == "metric"
        assert name == "claude_code.session.count"
        assert value == 3

    def test_logrecord_with_body(self):
        obj = {"body": "claude_code.tool_decision",
               "attributes": {"decision": "accept"}}
        result = list(_normalise(obj))
        assert result == [("event", "claude_code.tool_decision",
                          {"decision": "accept"}, None)]

    def test_logrecord_with_event_name_attr(self):
        obj = {"body": "", "attributes": {
            "event.name": "claude_code.at_mention",
            "mention_type": "file",
        }}
        result = list(_normalise(obj))
        assert result[0][0] == "event"
        assert result[0][1] == "claude_code.at_mention"

    def test_resource_metrics_shape(self):
        obj = {"resource_metrics": [{
            "scope_metrics": [{
                "metrics": [{
                    "name": "claude_code.session.count",
                    "data": {"data_points": [
                        {"value": 5, "attributes": {"session.id": "s1"}},
                    ]},
                }],
            }],
        }]}
        result = list(_normalise(obj))
        assert len(result) == 1
        kind, name, attrs, value = result[0]
        assert kind == "metric"
        assert value == 5

    def test_resource_metrics_with_kv_attrs(self):
        obj = {"resourceMetrics": [{
            "scopeMetrics": [{
                "metrics": [{
                    "name": "claude_code.session.count",
                    "data": {"dataPoints": [
                        {"asInt": "2",
                         "attributes": [
                             {"key": "session.id",
                              "value": {"stringValue": "sX"}},
                         ]},
                    ]},
                }],
            }],
        }]}
        result = list(_normalise(obj))
        kind, name, attrs, value = result[0]
        assert attrs == {"session.id": "sX"}
        assert value == 2.0

    def test_unknown_shape_yields_nothing(self):
        assert list(_normalise({"random": "thing"})) == []

    def test_non_dict_input(self):
        assert list(_normalise("not a dict")) == []


class TestKvListToDict:
    def test_basic(self):
        kv = [
            {"key": "a", "value": {"stringValue": "x"}},
            {"key": "b", "value": {"intValue": 42}},
            {"key": "c", "value": "literal"},
        ]
        assert _kv_list_to_dict(kv) == {"a": "x", "b": 42, "c": "literal"}

    def test_ignores_malformed(self):
        kv = [{"no_key": "x"}, "not a dict"]
        assert _kv_list_to_dict(kv) == {}


# ---------------------------------------------------------------------------
# OTLPFileCollector.fetch — end-to-end with the project fixture
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "fixtures" / "otel-events.log"


class TestOtlpFileCollector:
    def test_missing_file_returns_empty_window_with_note(self, tmp_path):
        c = OTLPFileCollector(tmp_path / "missing.log")
        w = c.fetch()
        assert w.session_count == 0
        assert any("not found" in n for n in w.notes)

    def test_fixture_aggregates_known_signals(self):
        assert FIXTURE.exists(), "fixture missing"
        c = OTLPFileCollector(FIXTURE)
        w = c.fetch()

        # session count metric was 2
        assert w.session_count == 2
        assert w.active_seconds == 5400

        # skills: 3 ars-plan + 1 browse → 4 total triggers
        assert "ars-plan" in w.skills
        assert w.skills["ars-plan"]["total"] == 3
        assert w.skills["browse"]["total"] == 1
        assert w.skills["ars-plan"]["triggers"]["claude-proactive"] >= 1
        assert w.skills["ars-plan"]["triggers"]["user-slash"] >= 1

        # MCP: github connected 2x, sentry failed 1x, playwright connected 1x
        assert w.mcp["github"]["connected"] == 2
        assert w.mcp["sentry"]["failed"] == 1
        assert w.mcp["playwright"]["connected"] == 1
        # only github was actually invoked (via mcp__github__* tool_result)
        assert "github" in w.mcp_invoked

        # plugins
        assert w.plugins["academic-research-skills"] == 1
        assert w.plugins["financial-analysis"] == 1

        # subagents detected via Task tool_parameters
        assert "Explore" in w.subagents
        assert "claude-code-guide" in w.subagents

        # hooks: 3 registered, 3 executed for PreToolUse
        assert w.hooks["PreToolUse"]["registered"] >= 1
        assert w.hooks["PreToolUse"]["executed"] == 3

        # at_mention
        assert w.mentions["file"]["success"] == 3
        assert w.mentions["file"]["fail"] == 1

        # tool_decision: 8 accepts, 2 rejects
        assert w.decisions["accept"] == 8
        assert w.decisions["reject"] == 2

        # token attribution
        assert w.token_by_skill["ars-plan"] == 12480
        assert w.token_by_agent["Explore"] == 88500

    def test_account_filter(self, tmp_path):
        log = _write_log(tmp_path / "log", [
            {"event_name": "claude_code.skill_activated",
             "attributes": {"skill.name": "x", "user.email": "alice@e"}},
            {"event_name": "claude_code.skill_activated",
             "attributes": {"skill.name": "y", "user.email": "bob@e"}},
        ])
        c = OTLPFileCollector(log)
        w = c.fetch(account_filter="alice@e")
        assert "x" in w.skills
        assert "y" not in w.skills

    def test_garbage_lines_skipped(self, tmp_path):
        log = tmp_path / "noisy.log"
        log.write_text(
            "this is not json\n"
            "junk\n"
            '{"event_name": "claude_code.plugin_loaded", "attributes": {"plugin.name": "p"}}\n',
            encoding="utf-8",
        )
        w = OTLPFileCollector(log).fetch()
        assert w.plugins["p"] == 1

    def test_embedded_json_in_log_line(self, tmp_path):
        log = tmp_path / "embedded.log"
        log.write_text(
            'INFO 2025-01-01 {"event_name": "claude_code.plugin_loaded", '
            '"attributes": {"plugin.name": "p"}} trailing\n',
            encoding="utf-8",
        )
        w = OTLPFileCollector(log).fetch()
        assert w.plugins["p"] == 1

    def test_session_id_fallback_when_no_session_metric(self, tmp_path):
        log = _write_log(tmp_path / "log", [
            {"event_name": "claude_code.skill_activated",
             "attributes": {"skill.name": "x", "session.id": "s1"}},
            {"event_name": "claude_code.skill_activated",
             "attributes": {"skill.name": "x", "session.id": "s2"}},
        ])
        w = OTLPFileCollector(log).fetch()
        # no session.count metric → falls back to distinct session.id count
        assert w.session_count == 2

    def test_tool_details_note_when_redacted(self, tmp_path):
        # Only an event with no skill.name / server_name → note added
        log = _write_log(tmp_path / "log", [
            {"event_name": "claude_code.tool_decision",
             "attributes": {"decision": "accept"}},
        ])
        w = OTLPFileCollector(log).fetch()
        assert any("OTEL_LOG_TOOL_DETAILS" in n for n in w.notes)
