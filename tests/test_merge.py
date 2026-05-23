"""Unit tests for agent_radar.usage.merge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_radar.usage import merge as merge_mod
from agent_radar.usage.merge import (
    _gap_hint,
    _rank_gaps,
    merge,
    scan_context_for,
)


# ---------------------------------------------------------------------------
# scan_context_for — regex extraction of denominators
# ---------------------------------------------------------------------------

class TestScanContextFor:
    def test_extracts_mcp_count(self):
        target = {"findings": [
            {"dimension": "mcp", "label": "MCP server 數量",
             "detail": "3 個 MCP server", "score": 50},
        ]}
        assert scan_context_for(target) == {"servers_configured": 3}

    def test_extracts_subagent_and_flags_hook_plugin(self):
        target = {"findings": [
            {"dimension": "automation", "label": "Hooks",
             "detail": "偵測到 hooks 設定", "score": 30},
            {"dimension": "automation", "label": "Plugins",
             "detail": "偵測到 plugin 使用", "score": 15},
            {"dimension": "automation", "label": "Subagents",
             "detail": "2 個 subagent", "score": 30},
        ]}
        ctx = scan_context_for(target)
        assert ctx["hooks_registered"] == 1
        assert ctx["plugins_installed"] == 1
        assert ctx["subagents_defined"] == 2

    def test_no_hooks_when_score_zero(self):
        target = {"findings": [
            {"dimension": "automation", "label": "Hooks",
             "detail": "未使用 hooks", "score": 0},
        ]}
        assert "hooks_registered" not in scan_context_for(target)

    def test_empty_findings(self):
        assert scan_context_for({}) == {}


# ---------------------------------------------------------------------------
# _gap_hint
# ---------------------------------------------------------------------------

class TestGapHint:
    def test_skills_with_proactive_in_usage(self):
        usage_target = {"findings_by_dim": {"skills": [
            {"label": "proactive 觸發比例", "weight": 40, "score": 8},
        ]}}
        hint = _gap_hint("skills", "my-repo", {"findings": []}, usage_target)
        assert "Skills" in hint
        assert "20%" in hint  # 8/40 = 20%

    def test_skills_no_usage_target(self):
        hint = _gap_hint("skills", "repo", {"findings": []}, None)
        assert "Skills" in hint

    def test_mcp_hint(self):
        hint = _gap_hint("mcp", "repo", {"findings": []}, None)
        assert "MCP" in hint

    def test_automation_hint(self):
        hint = _gap_hint("automation", "repo", {"findings": []}, None)
        assert "自動化" in hint

    def test_unknown_dim_returns_generic(self):
        hint = _gap_hint("unknown", "repo", {"findings": []}, None)
        assert "落差" in hint


# ---------------------------------------------------------------------------
# _rank_gaps
# ---------------------------------------------------------------------------

class TestRankGaps:
    def test_sorts_by_gap_desc_drops_small_gaps(self):
        merged = {
            "skills": {"config": 80, "usage": 20, "gap": 60},
            "mcp": {"config": 50, "usage": 30, "gap": 20},
            "automation": {"config": 40, "usage": 35, "gap": 5},  # below noise
            "iteration": {"config": 30, "usage": None, "gap": None},
        }
        gaps = _rank_gaps("repo", {"findings": []}, None, merged)
        # automation below noise floor (10) → excluded; iteration None → excluded
        dims = [g["dimension"] for g in gaps]
        assert dims == ["skills", "mcp"]

    def test_top_n_cap(self):
        merged = {
            f"dim{i}": {"config": 100, "usage": 100 - (i+1)*15, "gap": (i+1)*15}
            for i in range(5)
        }
        gaps = _rank_gaps("repo", {"findings": []}, None, merged, top_n=3)
        assert len(gaps) == 3
        # highest gap first
        assert gaps[0]["gap"] >= gaps[1]["gap"] >= gaps[2]["gap"]


# ---------------------------------------------------------------------------
# merge() top-level
# ---------------------------------------------------------------------------

def _scan_data() -> dict:
    return {
        "dimensions": {
            "claude_md": "CLAUDE.md",
            "skills": "Skills",
            "mcp": "MCP",
            "automation": "Automation",
            "context_hygiene": "Hygiene",
            "iteration": "Iteration",
        },
        "levels": [[0, "L0"], [60, "L3"]],
        "targets": [{
            "name": "demo",
            "path": "/tmp/demo",
            "level": "L3 · 進階",
            "overall": 60.0,
            "scores": {
                "claude_md": 70.0,
                "skills": 80.0,
                "mcp": 50.0,
                "automation": 40.0,
                "context_hygiene": 60.0,
                "iteration": 30.0,
            },
            "findings": [
                {"dimension": "skills", "label": "Skills 存在",
                 "weight": 35, "score": 35, "detail": "1 個"},
            ],
            "blind_spots": ["bs"],
        }],
    }


def _usage_data() -> dict:
    return {
        "usage_dimensions": {"skills": "Skills 運用"},
        "targets_by_name": {
            "demo": {
                "name": "demo",
                "overall": 45.0,
                "scores": {
                    "claude_md": 90.0,
                    "skills": 20.0,
                    "mcp": 30.0,
                    "automation": 35.0,
                    "context_hygiene": 50.0,
                    "iteration": None,
                },
                "findings_by_dim": {
                    "skills": [{"label": "proactive 觸發比例",
                                "weight": 40, "score": 4}],
                },
                "totals": {"session_count": 3},
                "notes": ["note"],
            },
        },
    }


class TestMerge:
    def test_merges_scores_and_gap(self):
        merged = merge(_scan_data(), _usage_data())
        assert len(merged["targets"]) == 1
        t = merged["targets"][0]
        assert t["config_overall"] == 60.0
        assert t["usage_overall"] == 45.0
        # gap = config - usage; iteration usage None → gap None
        assert t["scores"]["skills"]["gap"] == 60.0
        assert t["scores"]["iteration"]["gap"] is None

    def test_passes_through_metadata(self):
        merged = merge(_scan_data(), _usage_data())
        t = merged["targets"][0]
        assert t["blind_spots"] == ["bs"]
        assert t["notes"] == ["note"]
        assert t["totals"]["session_count"] == 3

    def test_top_gaps_populated(self):
        merged = merge(_scan_data(), _usage_data())
        gaps = merged["targets"][0]["top_gaps"]
        assert gaps, "expected at least one ranked gap"
        # skills gap (60) is largest
        assert gaps[0]["dimension"] == "skills"

    def test_unmatched_usage_targets_safe(self):
        scan = _scan_data()
        usage = {"usage_dimensions": {}, "targets_by_name": {}}
        merged = merge(scan, usage)
        t = merged["targets"][0]
        assert t["usage_overall"] is None
        # gaps for unmatched → all None
        for dim, sc in t["scores"].items():
            assert sc["usage"] is None
            assert sc["gap"] is None
        assert t["top_gaps"] == []


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------

class TestMergeMainCli:
    def test_cli_writes_output(self, tmp_path, monkeypatch, capsys):
        scan = tmp_path / "scan.json"
        usage = tmp_path / "usage.json"
        out = tmp_path / "merged.json"
        scan.write_text(json.dumps(_scan_data()), encoding="utf-8")
        usage.write_text(json.dumps(_usage_data()), encoding="utf-8")

        monkeypatch.setattr(
            "sys.argv",
            ["merge", str(scan), str(usage), "-o", str(out)],
        )
        merge_mod.main()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["targets"][0]["name"] == "demo"
