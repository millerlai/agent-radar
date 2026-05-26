"""Unit tests for agent_radar.usage.merge."""

from __future__ import annotations

import json


from agent_radar.usage import merge as merge_mod
from agent_radar.usage.merge import (
    GAP_ABS_FLOOR,
    GAP_RATIO_FLOOR,
    _gap_hint,
    _rank_gaps,
    merge,
    scan_context_for,
)


# ---------------------------------------------------------------------------
# scan_context_for — structured arg extraction (no string parsing)
# ---------------------------------------------------------------------------

class TestScanContextFor:
    def test_extracts_mcp_count(self):
        target = {"findings": [
            {"dimension": "mcp", "label_key": "scan.mcp.server_count",
             "detail_args": {"n": 3}, "score": 50},
        ]}
        assert scan_context_for(target) == {"servers_configured": 3}

    def test_extracts_subagent_and_flags_hook_plugin(self):
        target = {"findings": [
            {"dimension": "automation", "label_key": "scan.automation.hooks",
             "detail_args": {}, "score": 30},
            {"dimension": "automation", "label_key": "scan.automation.plugins",
             "detail_args": {}, "score": 15},
            {"dimension": "automation", "label_key": "scan.automation.subagents",
             "detail_args": {"n": 2}, "score": 30},
        ]}
        ctx = scan_context_for(target)
        assert ctx["hooks_registered"] == 1
        assert ctx["plugins_installed"] == 1
        assert ctx["subagents_defined"] == 2

    def test_no_hooks_when_score_zero(self):
        target = {"findings": [
            {"dimension": "automation", "label_key": "scan.automation.hooks",
             "detail_args": {}, "score": 0},
        ]}
        assert "hooks_registered" not in scan_context_for(target)

    def test_empty_findings(self):
        assert scan_context_for({}) == {}


# ---------------------------------------------------------------------------
# _gap_hint — now returns (key, args), not a localized string
# ---------------------------------------------------------------------------

class TestGapHint:
    def test_skills_with_proactive_in_usage(self):
        usage_target = {"findings_by_dim": {"skills": [
            {"label_key": "usage.skills.proactive", "weight": 40, "score": 8},
        ]}}
        key, args = _gap_hint("skills", "my-repo", usage_target)
        assert key == "gap.skills.proactive_low"
        assert args["pct"] == 20  # 8/40 = 20%
        assert args["target"] == "my-repo"

    def test_skills_no_usage_target(self):
        key, args = _gap_hint("skills", "repo", None)
        assert key == "gap.skills.generic"

    def test_mcp_hint(self):
        key, args = _gap_hint("mcp", "repo", None)
        assert key == "gap.mcp"

    def test_automation_hint(self):
        key, args = _gap_hint("automation", "repo", None)
        assert key == "gap.automation"

    def test_unknown_dim_returns_generic(self):
        key, args = _gap_hint("unknown", "repo", None)
        assert key == "gap.generic"
        assert args["dim"] == "unknown"


# ---------------------------------------------------------------------------
# _rank_gaps
# ---------------------------------------------------------------------------

class TestRankGaps:
    def test_sorts_by_gap_desc_drops_small_gaps(self):
        merged = {
            "skills": {"config": 80, "usage": 20, "gap": 60},
            "mcp": {"config": 50, "usage": 30, "gap": 20},
            "automation": {"config": 40, "usage": 35, "gap": 5},  # absolute noise
            "claude_md": {"config": 30, "usage": None, "gap": None},
        }
        gaps = _rank_gaps("repo", None, merged)
        dims = [g["dimension"] for g in gaps]
        assert dims == ["skills", "mcp"]
        assert all("hint_key" in g and "hint_args" in g for g in gaps)
        # Each surviving row carries gap_ratio in 0..1
        for g in gaps:
            assert 0 < g["gap_ratio"] <= 1

    def test_top_n_cap(self):
        # gaps 45/60/75 all pass (ratios 0.45/0.60/0.75); 15/30 are filtered
        # by the ratio floor (0.15/0.30), so only 3 survive even with top_n=5.
        merged = {
            f"dim{i}": {"config": 100, "usage": 100 - (i+1)*15, "gap": (i+1)*15}
            for i in range(5)
        }
        gaps = _rank_gaps("repo", None, merged, top_n=3)
        assert len(gaps) == 3
        assert gaps[0]["gap"] >= gaps[1]["gap"] >= gaps[2]["gap"]

    def test_relative_threshold_filters_low_ratio_at_same_abs_gap(self):
        """Same abs gap, different densities — only the low-density one surfaces."""
        merged = {
            "low_density":  {"config": 30, "usage": 14, "gap": 16},  # ratio 0.53
            "high_density": {"config": 90, "usage": 74, "gap": 16},  # ratio 0.18
        }
        gaps = _rank_gaps("repo", None, merged)
        assert [g["dimension"] for g in gaps] == ["low_density"]
        assert gaps[0]["gap_ratio"] > GAP_RATIO_FLOOR

    def test_abs_gap_floor_blocks_low_score_pairs(self):
        """A 0.6 ratio is meaningless when both sides are tiny — abs floor catches it."""
        merged = {"tiny": {"config": 5, "usage": 1, "gap": 4}}  # ratio 0.8, but gap<=10
        gaps = _rank_gaps("repo", None, merged)
        assert gaps == []

    def test_over_direction_uses_symmetric_denominator(self):
        """gap_ratio uses max(config, usage) so 'over' direction isn't biased
        toward a low-config denominator that would over-inflate the ratio."""
        # config=10, usage=70 → gap=-60, abs=60.
        # Single-side (config): 60/10 = 6.0 — absurd.
        # Symmetric:            60/70 ≈ 0.86 — meaningful.
        merged = {"automation": {"config": 10, "usage": 70, "gap": -60}}
        gaps = _rank_gaps("repo", None, merged)
        assert len(gaps) == 1
        assert gaps[0]["direction"] == "over"
        assert 0 < gaps[0]["gap_ratio"] <= 1
        assert gaps[0]["gap"] == -60


# ---------------------------------------------------------------------------
# merge() top-level
# ---------------------------------------------------------------------------

def _scan_data() -> dict:
    # 0.2.0 five-axis shape (iteration folded into claude_md).
    return {
        "dimensions": [
            "claude_md", "skills", "mcp", "automation", "context_hygiene",
        ],
        "targets": [{
            "name": "demo",
            "path": "/tmp/demo",
            "overall": 60.0,
            "scores": {
                "claude_md": 70.0, "skills": 80.0, "mcp": 50.0,
                "automation": 40.0, "context_hygiene": 60.0,
            },
            "findings": [
                {"dimension": "skills", "label_key": "scan.skills.exists",
                 "weight": 70, "score": 70,
                 "detail_key": "scan.skills.exists.have",
                 "detail_args": {"n": 1}},
            ],
            "blind_spots": [{"key": "scan.blind.config_only", "args": {}}],
        }],
    }


def _usage_data() -> dict:
    return {
        "usage_dimensions": [
            "claude_md", "skills", "mcp", "automation", "context_hygiene",
        ],
        "targets_by_name": {
            "demo": {
                "name": "demo",
                "overall": 45.0,
                "scores": {
                    "claude_md": 90.0, "skills": 20.0, "mcp": 30.0,
                    "automation": 35.0, "context_hygiene": 50.0,
                },
                "findings_by_dim": {
                    "skills": [{"label_key": "usage.skills.proactive",
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
        assert t["scores"]["skills"]["gap"] == 60.0
        # All five axes have a usage value (iteration no longer exists)
        assert all(t["scores"][d]["usage"] is not None
                   for d in ["claude_md", "skills", "mcp", "automation", "context_hygiene"])

    def test_passes_through_metadata(self):
        merged = merge(_scan_data(), _usage_data())
        t = merged["targets"][0]
        assert {"key": "scan.blind.config_only", "args": {}} in t["blind_spots"]
        assert t["notes"] == ["note"]
        assert t["totals"]["session_count"] == 3

    def test_top_gaps_populated(self):
        merged = merge(_scan_data(), _usage_data())
        gaps = merged["targets"][0]["top_gaps"]
        assert gaps, "expected at least one ranked gap"
        assert gaps[0]["dimension"] == "skills"
        # hint travels as key+args
        assert gaps[0]["hint_key"].startswith("gap.skills.")

    def test_unmatched_usage_targets_safe(self):
        scan = _scan_data()
        usage = {"usage_dimensions": [], "targets_by_name": {}}
        merged = merge(scan, usage)
        t = merged["targets"][0]
        assert t["usage_overall"] is None
        for dim, sc in t["scores"].items():
            assert sc["usage"] is None
            assert sc["gap"] is None
        assert t["top_gaps"] == []

    def test_accepts_legacy_dict_dimensions(self):
        """If callers ever pass the old dict-shape dimensions, merge still works."""
        scan = _scan_data()
        scan["dimensions"] = {k: k for k in scan["dimensions"]}
        merged = merge(scan, _usage_data())
        assert merged["dimensions"] == list(scan["dimensions"].keys())


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
