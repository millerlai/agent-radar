"""Smoke tests for agent_radar.install_skill — install bundled skills into a tmp dir."""

from __future__ import annotations

import pytest

from agent_radar import cli, install_skill


class TestInstallSkill:
    def test_fresh_install_creates_all_skill_mds(self, tmp_path):
        installed = install_skill.install(tmp_path)
        assert len(installed) == len(install_skill.SKILL_NAMES)
        for name, dst in zip(install_skill.SKILL_NAMES, installed):
            assert dst == tmp_path / name
            skill_md = dst / "SKILL.md"
            assert skill_md.is_file(), f"missing SKILL.md for {name}"
            text = skill_md.read_text(encoding="utf-8")
            # frontmatter declares the slash-command name
            assert f"name: {name}" in text
            # description is the trigger surface
            assert "agent-radar" in text.split("---", 2)[1]

    def test_refuses_when_any_target_exists_without_force(self, tmp_path):
        install_skill.install(tmp_path)
        with pytest.raises(FileExistsError):
            install_skill.install(tmp_path)

    def test_conflict_check_is_atomic(self, tmp_path):
        """If only the SECOND skill already exists, install should refuse BEFORE
        overwriting the first one — caller should never see a half-applied state."""
        # Pre-create just the second skill's target dir.
        first, second = install_skill.SKILL_NAMES
        (tmp_path / second).mkdir(parents=True)
        sentinel = tmp_path / second / "preexisting.txt"
        sentinel.write_text("keep me", encoding="utf-8")

        with pytest.raises(FileExistsError):
            install_skill.install(tmp_path)

        # First skill must NOT have been written, because conflict was checked first.
        assert not (tmp_path / first).exists()
        # Second skill's preexisting content must be untouched.
        assert sentinel.read_text(encoding="utf-8") == "keep me"

    def test_force_overwrites_all(self, tmp_path):
        install_skill.install(tmp_path)
        for name in install_skill.SKILL_NAMES:
            sentinel = tmp_path / name / "stale.txt"
            sentinel.write_text("stale", encoding="utf-8")
        install_skill.install(tmp_path, force=True)
        for name in install_skill.SKILL_NAMES:
            dst = tmp_path / name
            # the rmtree-then-copy path means stale files must be gone
            assert not (dst / "stale.txt").exists()
            assert (dst / "SKILL.md").is_file()

    def test_dry_run_does_not_write(self, tmp_path):
        targets = install_skill.install(tmp_path, dry_run=True)
        assert len(targets) == len(install_skill.SKILL_NAMES)
        for dst in targets:
            assert not dst.exists()

    def test_cli_dispatch(self, tmp_path, capsys):
        rv = cli.main(["agent-radar", "install-skill", "--dest", str(tmp_path)])
        assert rv == 0
        out = capsys.readouterr().out
        for name in install_skill.SKILL_NAMES:
            assert (tmp_path / name / "SKILL.md").is_file()
            assert name in out
        # CLI footer advertises both slash commands
        assert "/agent-radar-coach" in out
        assert "/agent-radar-feedback" in out

    def test_cli_dispatch_refuses_without_force(self, tmp_path, capsys):
        cli.main(["agent-radar", "install-skill", "--dest", str(tmp_path)])
        rv = cli.main(["agent-radar", "install-skill", "--dest", str(tmp_path)])
        assert rv == 1
        assert "already exists" in capsys.readouterr().err
