"""Unit tests for agent_radar.cli — the thin subcommand router."""

from __future__ import annotations

import json


from agent_radar import __version__, cli
from agent_radar.report import _looks_like_merged


class TestCliRouter:
    def test_help_returns_zero(self, capsys):
        rv = cli.main(["agent-radar", "--help"])
        assert rv == 0
        out = capsys.readouterr().out
        assert "scan" in out
        assert "report" in out

    def test_no_args_prints_help(self, capsys):
        rv = cli.main(["agent-radar"])
        assert rv == 0
        assert "Subcommands" in capsys.readouterr().out

    def test_version_flag(self, capsys):
        rv = cli.main(["agent-radar", "--version"])
        assert rv == 0
        assert __version__ in capsys.readouterr().out

    def test_unknown_subcommand_exits_2(self, capsys):
        rv = cli.main(["agent-radar", "bogus"])
        assert rv == 2
        err = capsys.readouterr().err
        assert "unknown subcommand" in err

    def test_dispatches_to_subcommand(self, tmp_path, monkeypatch, capsys):
        # End-to-end: run "agent-radar scan <repo> -o <out>" via the router
        out = tmp_path / "scan.json"
        repo = tmp_path / "r"
        repo.mkdir()
        rv = cli.main(["agent-radar", "scan", str(repo), "-o", str(out)])
        assert rv == 0
        assert out.exists()


class TestReportMergedDetection:
    """Pre-flight check: report should refuse a merged.json passed as the
    positional scan.json argument with a helpful message, instead of
    crashing inside radar_svg."""

    def test_looks_like_merged_recognizes_merge_shape(self):
        merged = {"targets": [{"scores": {"claude_md": {"config": 70,
                                                        "usage": 30,
                                                        "gap": 40}}}]}
        assert _looks_like_merged(merged) is True

    def test_looks_like_merged_rejects_scan_shape(self):
        scan = {"targets": [{"scores": {"claude_md": 70.0, "skills": 80.0}}]}
        assert _looks_like_merged(scan) is False

    def test_looks_like_merged_safe_on_empty(self):
        assert _looks_like_merged({}) is False
        assert _looks_like_merged({"targets": []}) is False
        assert _looks_like_merged({"targets": [{}]}) is False

    def test_report_cli_rejects_merged_as_positional(self, tmp_path, capsys):
        merged = tmp_path / "merged.json"
        merged.write_text(json.dumps({
            "dimensions": ["claude_md"],
            "usage_dimensions": ["claude_md"],
            "targets": [{
                "name": "demo",
                "scores": {"claude_md": {"config": 70, "usage": 30, "gap": 40}},
            }],
        }), encoding="utf-8")
        out = tmp_path / "report.html"
        rv = cli.main(["agent-radar", "report", str(merged), "-o", str(out),
                       "--lang", "en"])
        assert rv == 2
        err = capsys.readouterr().err
        assert "merged.json" in err
        assert "--merged" in err
        assert not out.exists()
