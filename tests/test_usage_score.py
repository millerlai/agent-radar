"""Unit tests for agent_radar.usage.usage_score."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_radar.usage.collectors.base import UsageWindow
from agent_radar.usage.usage_score import USAGE_DIMENSION_KEYS, score_window


def _empty_window() -> UsageWindow:
    return UsageWindow(
        since=datetime.fromtimestamp(0, tz=timezone.utc),
        until=datetime.now(tz=timezone.utc),
    )


def _rich_window() -> UsageWindow:
    w = _empty_window()
    w.session_count = 4
    w.skills = {
        "browse": {
            "total": 5,
            "triggers": {"claude-proactive": 3, "user-slash": 2},
            "sources": {},
        },
        "review": {
            "total": 1,
            "triggers": {"user-slash": 1},
            "sources": {},
        },
    }
    w.mcp = {
        "github": {"connected": 3, "failed": 0,
                   "disconnected": 0, "transports": {}},
        "sentry": {"connected": 0, "failed": 2,
                   "disconnected": 0, "transports": {}},
    }
    w.mcp_invoked = {"github"}
    w.plugins = {"p1": 1}
    w.hooks = {"PreToolUse": {"registered": 2, "executed": 4,
                              "blocking": 0, "errors": 0, "duration_ms": 0}}
    w.subagents = {"Explore"}
    w.mentions = {
        "file": {"success": 6, "fail": 2},
        "agent": {"success": 1, "fail": 0},
    }
    w.decisions = {"accept": 8, "reject": 2, "by_source": {}}
    return w


class TestUsageDimensionsKeys:
    def test_keys_match_scanner_dimensions(self):
        # scoring side MUST mirror scanner dim keys (per usage_score docstring)
        from agent_radar.scanner import DIMENSION_KEYS
        assert set(USAGE_DIMENSION_KEYS) == set(DIMENSION_KEYS)


class TestScoreWindowEmpty:
    def test_iteration_is_none_and_other_dims_numeric(self):
        result = score_window(_empty_window())
        assert result["scores"]["iteration"] is None
        # claude_md scoring uses 1 - reject_ratio which is 1.0 with no events;
        # the remaining dims must be 0 when nothing happened.
        for dim in ("skills", "mcp", "automation", "context_hygiene"):
            assert result["scores"][dim] == 0
        # claude_md falls back to 100 when no decisions exist (degenerate)
        assert result["scores"]["claude_md"] == 100.0
        # overall = mean of numeric dims (iteration excluded)
        assert result["overall"] == round(100 / 5, 1)

    def test_findings_returned_per_dim(self):
        result = score_window(_empty_window())
        for dim in USAGE_DIMENSION_KEYS:
            assert dim in result["findings_by_dim"]


class TestScoreWindowRich:
    def test_skills_score_components(self):
        result = score_window(_rich_window())
        scores = result["scores"]
        assert 0 < scores["skills"] <= 100
        # proactive ratio 3/6 = 0.5 → 20 pts, activation 6/4=1.5 capped → 40 pts,
        # distinct > 0 → 20 pts; total 80
        assert scores["skills"] == 80.0

    def test_mcp_health_and_invoked(self):
        result = score_window(_rich_window())
        # health = connected/(connected+failed) = 3/5 = 0.6 → 30
        # used_ratio with no scan_context: servers_configured = max(len(w.mcp), 1) = 2
        # mcp_invoked length = 1 → ratio 0.5 → 25
        assert result["scores"]["mcp"] == 55.0

    def test_mcp_uses_scan_context_for_denominator(self):
        result = score_window(_rich_window(),
                              scan_context={"servers_configured": 4})
        # used_ratio now 1/4 = 0.25 → 12.5
        assert result["scores"]["mcp"] == pytest.approx(42.5)

    def test_automation_uses_static_hooks_registered(self):
        # static hooks_registered=2, executed=4 → ratio capped at 1.0 → 40
        # plugins loaded 1, installed (max(1,1))=1 → 35
        # subagents present → 25
        result = score_window(_rich_window(),
                              scan_context={"hooks_registered": 2})
        assert result["scores"]["automation"] == 100.0

    def test_context_hygiene_mix(self):
        result = score_window(_rich_window())
        # file_mention_rate = 8/4=2 capped 1.0 → 60
        # success_rate = 7/9 = ~0.778 → ~31.1
        assert result["scores"]["context_hygiene"] == pytest.approx(91.1, abs=0.5)

    def test_claude_md_acceptance(self):
        result = score_window(_rich_window())
        # 8 accepts / (8+2) = 0.8 acceptance → score 80
        assert result["scores"]["claude_md"] == 80.0

    def test_totals_diagnostic_counts(self):
        result = score_window(_rich_window())
        totals = result["totals"]
        assert totals["session_count"] == 4
        assert totals["skills_activated_total"] == 6
        assert totals["mcp_servers_invoked"] == 1
        assert totals["subagents_distinct"] == 1
        assert totals["tool_accepts"] == 8
        assert totals["tool_rejects"] == 2

    def test_window_iso_dates(self):
        result = score_window(_rich_window())
        # iso strings parsable
        datetime.fromisoformat(result["window"]["since"])
        datetime.fromisoformat(result["window"]["until"])


class TestEdgeCases:
    def test_no_decisions_yields_full_acceptance_default(self):
        # decisions all zero → reject_ratio = 0 → score 100
        w = _empty_window()
        result = score_window(w)
        assert result["scores"]["claude_md"] == 100.0

    def test_no_mentions_zero_context_score(self):
        w = _empty_window()
        w.session_count = 1
        result = score_window(w)
        assert result["scores"]["context_hygiene"] == 0
