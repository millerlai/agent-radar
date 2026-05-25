"""Smoke tests for agent_radar.install_skill — install the coach skill into a tmp dir."""

from __future__ import annotations

import pytest

from agent_radar import cli, install_skill


class TestInstallSkill:
    def test_fresh_install_creates_skill_md(self, tmp_path):
        dst = install_skill.install(tmp_path)
        skill_md = dst / "SKILL.md"
        assert skill_md.is_file()
        text = skill_md.read_text(encoding="utf-8")
        # frontmatter declares the slash-command name
        assert "name: agent-radar-coach" in text
        # description is the trigger surface — must mention agent-radar
        assert "agent-radar" in text.split("---", 2)[1]

    def test_refuses_when_target_exists_without_force(self, tmp_path):
        install_skill.install(tmp_path)
        with pytest.raises(FileExistsError):
            install_skill.install(tmp_path)

    def test_force_overwrites(self, tmp_path):
        install_skill.install(tmp_path)
        dst = tmp_path / install_skill.SKILL_NAME
        sentinel = dst / "stale.txt"
        sentinel.write_text("stale", encoding="utf-8")
        install_skill.install(tmp_path, force=True)
        # the rmtree-then-copy path means our sentinel must be gone
        assert not sentinel.exists()
        assert (dst / "SKILL.md").is_file()

    def test_dry_run_does_not_write(self, tmp_path):
        dst = install_skill.install(tmp_path, dry_run=True)
        assert not dst.exists()

    def test_cli_dispatch(self, tmp_path, capsys):
        rv = cli.main(["agent-radar", "install-skill", "--dest", str(tmp_path)])
        assert rv == 0
        assert (tmp_path / install_skill.SKILL_NAME / "SKILL.md").is_file()
        assert "/agent-radar-coach" in capsys.readouterr().out

    def test_cli_dispatch_refuses_without_force(self, tmp_path, capsys):
        cli.main(["agent-radar", "install-skill", "--dest", str(tmp_path)])
        rv = cli.main(["agent-radar", "install-skill", "--dest", str(tmp_path)])
        assert rv == 1
        assert "already exists" in capsys.readouterr().err
