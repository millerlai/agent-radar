"""Unit tests for agent_radar.cli — the thin subcommand router."""

from __future__ import annotations

import pytest

from agent_radar import __version__, cli


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
