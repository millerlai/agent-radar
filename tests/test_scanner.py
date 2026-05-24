"""Unit tests for agent_radar.scanner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


from agent_radar import scanner
from agent_radar.scanner import (
    DIMENSION_KEYS,
    LEVEL_THRESHOLDS,
    Finding,
    _clamp,
    _exists,
    _git_log_count,
    _read,
    detect_automation,
    detect_claude_md,
    detect_context_hygiene,
    detect_iteration,
    detect_mcp,
    detect_skills,
    score_target,
)


def _write(p: Path, content: str = "") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _by_key(findings):
    """Index findings by label_key for terser asserts."""
    return {f.label_key: f for f in findings}


# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------

class TestClamp:
    def test_within_range(self):
        assert _clamp(5, 0, 10) == 5

    def test_below_low(self):
        assert _clamp(-3, 0, 10) == 0

    def test_above_high(self):
        assert _clamp(99, 0, 10) == 10

    def test_no_hi(self):
        assert _clamp(1000) == 1000

    def test_float(self):
        assert _clamp(3.7, 0, 5) == 3.7


class TestRead:
    def test_reads_existing(self, tmp_path):
        f = _write(tmp_path / "a.txt", "hello")
        assert _read(f) == "hello"

    def test_missing_returns_empty(self, tmp_path):
        assert _read(tmp_path / "ghost.txt") == ""

    def test_respects_limit(self, tmp_path):
        f = _write(tmp_path / "big.txt", "x" * 1000)
        assert _read(f, limit=100) == "x" * 100


class TestExists:
    def test_existing(self, tmp_path):
        assert _exists(tmp_path) is True

    def test_missing(self, tmp_path):
        assert _exists(tmp_path / "no") is False


# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------

class TestFinding:
    def test_ratio(self):
        f = Finding("x", "y.key", weight=10, score=3)
        assert f.ratio == 0.3

    def test_zero_weight(self):
        f = Finding("x", "y.key", weight=0, score=0)
        assert f.ratio == 0.0


# ---------------------------------------------------------------------------
# CLAUDE.md detection
# ---------------------------------------------------------------------------

class TestDetectClaudeMd:
    def test_missing_zero(self, tmp_path):
        findings = detect_claude_md(tmp_path, is_home=False)
        assert all(f.score == 0 for f in findings)
        # the "exists" finding signals absence via its detail_key
        by = _by_key(findings)
        assert by["scan.claude_md.exists"].detail_key == "scan.claude_md.exists.none"

    def test_minimal_present_gets_exists_credit(self, tmp_path):
        _write(tmp_path / "CLAUDE.md", "hi")
        findings = detect_claude_md(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.claude_md.exists"].score == 25

    def test_well_structured_md_scores_high(self, tmp_path):
        body = """# Build
## Test
## Code style
- Use small functions.
- Do not commit secrets.
- Never push without review.
- Always run tests.
@docs/style.md
@docs/conventions.md
"""
        _write(tmp_path / "CLAUDE.md", body)
        findings = detect_claude_md(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.claude_md.exists"].score == 25
        assert by["scan.claude_md.structure"].score > 0
        assert by["scan.claude_md.imperative"].score > 0
        assert by["scan.claude_md.import"].score > 0
        assert by["scan.claude_md.lint_size"].score == 15

    def test_huge_md_size_lint_zero(self, tmp_path):
        big = "word " * 8000  # ~40 000 chars
        _write(tmp_path / "CLAUDE.md", big)
        findings = detect_claude_md(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.claude_md.lint_size"].score == 0
        assert by["scan.claude_md.concise"].score == 5

    def test_nested_claude_md_recognised(self, tmp_path):
        _write(tmp_path / ".claude" / "CLAUDE.md", "# hi\nuse foo.")
        findings = detect_claude_md(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.claude_md.exists"].score == 25


# ---------------------------------------------------------------------------
# Skills detection
# ---------------------------------------------------------------------------

class TestDetectSkills:
    def test_no_skills(self, tmp_path):
        findings = detect_skills(tmp_path, is_home=False)
        assert all(f.score == 0 for f in findings)

    def test_skill_with_quality_description(self, tmp_path):
        skill_dir = tmp_path / ".claude" / "skills" / "browse"
        _write(
            skill_dir / "SKILL.md",
            "---\n"
            "name: browse\n"
            "description: Use this skill when the user asks to open a browser "
            "or trigger headless QA testing on a deployed URL.\n"
            "---\n"
            "# browse\nshort body\n",
        )
        _write(skill_dir / "helper.md", "more details")
        findings = detect_skills(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.skills.exists"].score == 35
        assert by["scan.skills.description"].score > 0
        assert by["scan.skills.progressive"].score == 15
        assert by["scan.skills.lint_hygiene"].score > 0

    def test_decorative_ascii_art_penalises_lint(self, tmp_path):
        skill_dir = tmp_path / ".claude" / "skills" / "x"
        body = (
            "---\nname: x\ndescription: use when ...\n---\n"
            + "=" * 60 + "\n"
            + "content\n"
        )
        _write(skill_dir / "SKILL.md", body)
        findings = detect_skills(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.skills.lint_hygiene"].score < 20
        # decor violation surfaces as a _suffixes entry
        suffixes = by["scan.skills.lint_hygiene"].detail_args.get("_suffixes", [])
        assert any(s[0] == "scan.skills.lint.decor_suffix" for s in suffixes)


# ---------------------------------------------------------------------------
# MCP detection
# ---------------------------------------------------------------------------

class TestDetectMcp:
    def test_no_mcp(self, tmp_path):
        findings = detect_mcp(tmp_path, is_home=False)
        assert all(f.score == 0 for f in findings)

    def test_servers_from_mcp_json(self, tmp_path):
        servers = {
            "mcpServers": {
                "github": {"command": "npx"},
                "postgres": {"command": "npx"},
                "slack": {"command": "npx"},
            }
        }
        _write(tmp_path / ".mcp.json", json.dumps(servers))
        findings = detect_mcp(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.mcp.server_count"].score == 50
        assert by["scan.mcp.server_count"].detail_args["n"] == 3
        cats = by["scan.mcp.category_breadth"].detail_args.get("cats", "")
        assert "data" in cats or "saas" in cats

    def test_settings_json_also_recognised(self, tmp_path):
        _write(
            tmp_path / ".claude" / "settings.json",
            json.dumps({"mcpServers": {"sentry": {}}}),
        )
        findings = detect_mcp(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.mcp.server_count"].score > 0


# ---------------------------------------------------------------------------
# Automation detection
# ---------------------------------------------------------------------------

class TestDetectAutomation:
    def test_nothing(self, tmp_path):
        findings = detect_automation(tmp_path, is_home=False)
        assert all(f.score == 0 for f in findings)

    def test_hooks_via_settings(self, tmp_path):
        _write(
            tmp_path / ".claude" / "settings.json",
            json.dumps({"hooks": {"PreToolUse": []}}),
        )
        findings = detect_automation(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.automation.hooks"].score == 30
        assert by["scan.automation.hooks"].detail_key == "scan.automation.hooks.have"

    def test_invalid_settings_json_flagged(self, tmp_path):
        _write(tmp_path / ".claude" / "settings.json", "{not json")
        findings = detect_automation(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.automation.hooks"].score == 0
        assert by["scan.automation.hooks"].detail_key == "scan.automation.hooks.invalid"

    def test_subagents_and_commands_count(self, tmp_path):
        for n in ("a", "b"):
            _write(tmp_path / ".claude" / "agents" / f"{n}.md", "")
        for n in ("c", "d", "e"):
            _write(tmp_path / ".claude" / "commands" / f"{n}.md", "")
        findings = detect_automation(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.automation.subagents"].score == 30
        assert by["scan.automation.subagents"].detail_args["n"] == 2
        assert by["scan.automation.commands"].score == 25
        assert by["scan.automation.commands"].detail_args["n"] == 3

    def test_plugin_signal_via_settings_text(self, tmp_path):
        _write(
            tmp_path / ".claude" / "settings.json",
            json.dumps({"enabledPlugins": ["foo"]}),
        )
        findings = detect_automation(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.automation.plugins"].score == 15


# ---------------------------------------------------------------------------
# Context hygiene
# ---------------------------------------------------------------------------

class TestDetectContextHygiene:
    def test_no_split_no_gitignore(self, tmp_path):
        findings = detect_context_hygiene(tmp_path, is_home=False, home_seen=False)
        assert all(f.score == 0 for f in findings)

    def test_project_only_split(self, tmp_path):
        _write(tmp_path / "CLAUDE.md", "x")
        findings = detect_context_hygiene(tmp_path, is_home=False, home_seen=False)
        by = _by_key(findings)
        assert by["scan.context.split"].score == 20

    def test_full_split(self, tmp_path):
        _write(tmp_path / "CLAUDE.md", "x\n@docs/a.md\n@docs/b.md")
        _write(tmp_path / ".gitignore", "node_modules\n.claude/settings.local.json")
        findings = detect_context_hygiene(tmp_path, is_home=False, home_seen=True)
        by = _by_key(findings)
        assert by["scan.context.split"].score == 40
        assert by["scan.context.shared_personal"].score == 30
        assert by["scan.context.modular"].score == 30


# ---------------------------------------------------------------------------
# Iteration detection
# ---------------------------------------------------------------------------

class TestDetectIteration:
    def test_non_git(self, tmp_path):
        findings = detect_iteration(tmp_path, is_home=False)
        assert all(f.score == 0 for f in findings)
        # the iteration.git finding signals non-git via its detail_key
        by = _by_key(findings)
        assert by["scan.iteration.git"].detail_key == "scan.iteration.non_git"

    def test_git_with_history(self, tmp_path):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@e"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
        for i in range(3):
            (tmp_path / "CLAUDE.md").write_text(f"v{i}\n", encoding="utf-8")
            subprocess.run(["git", "add", "CLAUDE.md"], cwd=tmp_path, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", f"v{i}"],
                cwd=tmp_path, check=True,
            )
        findings = detect_iteration(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.iteration.git"].score > 0
        assert by["scan.iteration.diversity"].score > 0


class TestGitLogCount:
    def test_non_git_returns_zero(self, tmp_path):
        assert _git_log_count(tmp_path, "anything") == 0


# ---------------------------------------------------------------------------
# end-to-end score_target
# ---------------------------------------------------------------------------

class TestScoreTarget:
    def test_empty_repo(self, tmp_path):
        rep = score_target(tmp_path, name="empty", is_home=False, home_seen=False)
        assert rep.name == "empty"
        assert set(rep.scores.keys()) == set(DIMENSION_KEYS)
        assert rep.overall == 0.0
        # lowest level threshold
        assert rep.level_threshold == LEVEL_THRESHOLDS[0]
        # findings serialised as plain dicts (asdict-ified Finding)
        assert all(isinstance(f, dict) for f in rep.findings)
        # each finding carries label_key (not the old `label`)
        assert all("label_key" in f for f in rep.findings)

    def test_overall_is_dimension_average(self, tmp_path):
        _write(tmp_path / "CLAUDE.md",
               "# Build\n## Test\nuse foo.\n@docs/a.md")
        _write(tmp_path / ".mcp.json", json.dumps({"mcpServers": {"github": {}}}))
        rep = score_target(tmp_path, name="x", is_home=False, home_seen=False)
        manual = round(sum(rep.scores.values()) / len(rep.scores), 1)
        assert rep.overall == manual

    def test_blind_spot_for_non_git(self, tmp_path):
        _write(tmp_path / "CLAUDE.md", "x")
        rep = score_target(tmp_path, name="x", is_home=False, home_seen=False)
        # blind_spots are now keyed dicts, not raw strings
        keys = [b["key"] for b in rep.blind_spots]
        assert "scan.blind.non_git" in keys


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

class TestScannerMainCli:
    def test_main_writes_json(self, tmp_path, monkeypatch, capsys):
        out = tmp_path / "scan.json"
        target = tmp_path / "repo"
        _write(target / "CLAUDE.md", "x")
        monkeypatch.setattr(
            "sys.argv",
            ["scanner", str(target), "-o", str(out)],
        )
        scanner.main()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "dimensions" in data
        assert data["dimensions"] == DIMENSION_KEYS
        assert "level_thresholds" in data
        assert len(data["targets"]) == 1
