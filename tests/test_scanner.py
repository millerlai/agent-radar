"""Unit tests for agent_radar.scanner (0.2.0 — activation-gap framing)."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path


from agent_radar import scanner
from agent_radar.scanner import (
    DIMENSION_KEYS,
    Finding,
    _clamp,
    _exists,
    _find_nested_candidates,
    _git_log_count,
    _interactive_checkbox_picker,
    _is_git_repo,
    _NestedCandidate,
    _read,
    _resolve_scan_targets,
    detect_automation,
    detect_claude_md,
    detect_context_hygiene,
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


class TestFinding:
    def test_ratio(self):
        f = Finding("x", "y.key", weight=10, score=3)
        assert f.ratio == 0.3

    def test_zero_weight(self):
        f = Finding("x", "y.key", weight=0, score=0)
        assert f.ratio == 0.0


# ---------------------------------------------------------------------------
# CLAUDE.md detection (0.2.0: facts only, no quality heuristics)
# ---------------------------------------------------------------------------

class TestDetectClaudeMd:
    def test_missing_only_emits_exists_zero(self, tmp_path):
        findings = detect_claude_md(tmp_path, is_home=False)
        # 0.2.0: no placeholder fake-zero findings — only the exists.none
        assert len(findings) == 1
        assert findings[0].label_key == "scan.claude_md.exists"
        assert findings[0].score == 0
        assert findings[0].detail_key == "scan.claude_md.exists.none"

    def test_minimal_present_gets_exists_credit(self, tmp_path):
        _write(tmp_path / "CLAUDE.md", "hi")
        findings = detect_claude_md(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.claude_md.exists"].score == 50

    def test_full_observable_facts(self, tmp_path):
        body = ("# Build\n"
                "## Test\n"
                "@docs/style.md\n"
                "@docs/conventions.md\n")
        _write(tmp_path / "CLAUDE.md", body)
        findings = detect_claude_md(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.claude_md.exists"].score == 50
        assert by["scan.claude_md.import"].score > 0   # @ refs counted
        assert by["scan.claude_md.lint_size"].score == 15
        # iteration is a fact, may be 0 if not a git repo / no iteration markers
        assert "scan.claude_md.iteration" in by

    def test_iteration_content_signals(self, tmp_path):
        body = ("# Tips\n"
                "## Lessons Learned\n"
                "do not repeat the bug from [2025-04-15]\n"
                "when I corrected you about X, remember it\n")
        _write(tmp_path / "CLAUDE.md", body)
        findings = detect_claude_md(tmp_path, is_home=False)
        by = _by_key(findings)
        # Even without git, content regex picks up iteration signals
        assert by["scan.claude_md.iteration"].score > 0
        assert by["scan.claude_md.iteration"].detail_args["hits"] >= 3

    def test_huge_md_size_lint_zero(self, tmp_path):
        _write(tmp_path / "CLAUDE.md", "x" * 25_000)
        findings = detect_claude_md(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.claude_md.lint_size"].score == 0

    def test_nested_claude_md_recognised(self, tmp_path):
        _write(tmp_path / ".claude" / "CLAUDE.md", "# hi")
        findings = detect_claude_md(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.claude_md.exists"].score == 50


# ---------------------------------------------------------------------------
# Skills detection (0.2.0: count + lint only, no description quality grade)
# ---------------------------------------------------------------------------

class TestDetectSkills:
    def test_no_skills(self, tmp_path):
        findings = detect_skills(tmp_path, is_home=False)
        # 0.2.0: only exists.none, no placeholder fake-zero findings
        assert len(findings) == 1
        assert findings[0].label_key == "scan.skills.exists"
        assert findings[0].score == 0

    def test_skill_present_gets_count_credit(self, tmp_path):
        skill_dir = tmp_path / ".claude" / "skills" / "browse"
        _write(
            skill_dir / "SKILL.md",
            "---\nname: browse\ndescription: use when X\n---\n# browse\nbody\n",
        )
        findings = detect_skills(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.skills.exists"].score > 0
        assert by["scan.skills.lint_hygiene"].score > 0

    def test_decorative_ascii_art_penalises_lint(self, tmp_path):
        skill_dir = tmp_path / ".claude" / "skills" / "x"
        body = ("---\nname: x\ndescription: use when ...\n---\n"
                + "=" * 60 + "\ncontent\n")
        _write(skill_dir / "SKILL.md", body)
        findings = detect_skills(tmp_path, is_home=False)
        by = _by_key(findings)
        suffixes = by["scan.skills.lint_hygiene"].detail_args.get("_suffixes", [])
        assert any(s[0] == "scan.skills.lint.decor_suffix" for s in suffixes)


# ---------------------------------------------------------------------------
# MCP detection (mostly unchanged from 0.1.x)
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
# Automation detection (mostly unchanged)
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
        assert by["scan.automation.subagents"].detail_args["n"] == 2
        assert by["scan.automation.commands"].detail_args["n"] == 3


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
# Iteration evidence (now folded into claude_md, no separate dimension)
# ---------------------------------------------------------------------------

class TestIterationInClaudeMd:
    def test_git_iteration_picked_up(self, tmp_path):
        _write(tmp_path / "CLAUDE.md", "# hi\nplain content\n")
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@e"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
        for i in range(3):
            (tmp_path / "CLAUDE.md").write_text(f"# v{i}\n", encoding="utf-8")
            subprocess.run(["git", "add", "CLAUDE.md"], cwd=tmp_path, check=True)
            subprocess.run(["git", "commit", "-q", "-m", f"v{i}"],
                           cwd=tmp_path, check=True)
        findings = detect_claude_md(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.claude_md.iteration"].detail_args["commits"] >= 3
        assert by["scan.claude_md.iteration"].score > 0


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
        # 0.2.0: five axes (iteration folded into claude_md)
        assert set(rep.scores.keys()) == set(DIMENSION_KEYS)
        assert "iteration" not in rep.scores
        assert rep.overall == 0.0
        # findings serialised as plain dicts
        assert all(isinstance(f, dict) for f in rep.findings)
        assert all("label_key" in f for f in rep.findings)

    def test_overall_is_dimension_average(self, tmp_path):
        _write(tmp_path / "CLAUDE.md", "# Build\n@docs/a.md")
        _write(tmp_path / ".mcp.json", json.dumps({"mcpServers": {"github": {}}}))
        rep = score_target(tmp_path, name="x", is_home=False, home_seen=False)
        manual = round(sum(rep.scores.values()) / len(rep.scores), 1)
        assert rep.overall == manual

    def test_dimensions_are_five(self, tmp_path):
        rep = score_target(tmp_path, name="x", is_home=False, home_seen=False)
        assert len(DIMENSION_KEYS) == 5
        assert DIMENSION_KEYS == [
            "claude_md", "skills", "mcp", "automation", "context_hygiene",
        ]
        # ``iteration`` axis must not leak back as an emitted score key
        assert set(rep.scores.keys()) == set(DIMENSION_KEYS)


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

class TestScannerMainCli:
    def test_main_writes_json(self, tmp_path, monkeypatch):
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
        # 0.2.0: no level_thresholds anymore
        assert "level_thresholds" not in data
        assert len(data["targets"]) == 1


# ---------------------------------------------------------------------------
# Nested-repo resolution (parent-of-repos UX)
# ---------------------------------------------------------------------------

def _make_git_repo(p: Path) -> Path:
    """Make ``p`` look like a git repo (no real git init needed)."""
    p.mkdir(parents=True, exist_ok=True)
    (p / ".git").mkdir()
    return p


def _make_claude_dir(p: Path) -> Path:
    """Make ``p`` look like it has a Claude Code .claude/ folder."""
    p.mkdir(parents=True, exist_ok=True)
    (p / ".claude").mkdir()
    return p


def _make_claude_md(p: Path) -> Path:
    """Make ``p`` contain a CLAUDE.md."""
    p.mkdir(parents=True, exist_ok=True)
    (p / "CLAUDE.md").write_text("# notes\n", encoding="utf-8")
    return p


def _fake_tty(content: str):
    """Return a stdin-like object with isatty()->True and given content."""
    s = io.StringIO(content)
    s.isatty = lambda: True  # type: ignore[assignment]
    return s


def _force_text_picker(monkeypatch):
    """Pin _resolve_scan_targets to the legacy text picker path.

    The new interactive picker uses platform raw-key reads (msvcrt.getch /
    termios) which can't be mocked through ``sys.stdin``. Tests that fake
    stdin with text content target the text fallback; call this from those
    tests so routing actually lands there.
    """
    monkeypatch.setattr(
        "agent_radar.scanner._can_use_interactive_picker", lambda: False,
    )


class TestIsGitRepo:
    def test_dir_with_dotgit_dir_is_repo(self, tmp_path):
        _make_git_repo(tmp_path / "r")
        assert _is_git_repo(tmp_path / "r") is True

    def test_dir_with_dotgit_file_is_repo(self, tmp_path):
        # git worktrees use a `.git` *file*, not a dir.
        r = tmp_path / "r"
        r.mkdir()
        (r / ".git").write_text("gitdir: /elsewhere", encoding="utf-8")
        assert _is_git_repo(r) is True

    def test_dir_without_dotgit_is_not_repo(self, tmp_path):
        d = tmp_path / "plain"
        d.mkdir()
        assert _is_git_repo(d) is False


class TestNestedCandidate:
    def test_default_requires_claude_signal(self, tmp_path):
        # git-only candidate → not default
        c = _NestedCandidate(path=tmp_path, has_git=True)
        assert c.is_default is False
        # any Claude signal → default
        assert _NestedCandidate(path=tmp_path, has_claude_md=True).is_default
        assert _NestedCandidate(path=tmp_path, has_claude_dir=True).is_default

    def test_signals_label(self, tmp_path):
        c = _NestedCandidate(
            path=tmp_path, has_git=True, has_claude_dir=True, has_claude_md=True,
        )
        assert c.signals_label() == "CLAUDE.md, .claude/, git"
        # all-false produces a dash sentinel — should not normally happen but
        # the function shouldn't blow up on a constructed-empty candidate.
        assert _NestedCandidate(path=tmp_path).signals_label() == "—"


class TestFindNestedCandidates:
    def test_picks_up_git_claude_dir_and_claude_md(self, tmp_path):
        _make_git_repo(tmp_path / "git-only")           # has .git only
        _make_claude_dir(tmp_path / "claude-dir-only")  # has .claude/ only
        _make_claude_md(tmp_path / "claude-md-only")    # has CLAUDE.md only
        # mixed signals
        mixed = tmp_path / "mixed"
        _make_git_repo(mixed)
        _make_claude_dir(mixed)
        _make_claude_md(mixed)
        # bare dir — should NOT be a candidate
        (tmp_path / "bare").mkdir()
        # loose file at parent — never a candidate
        (tmp_path / "loose.txt").write_text("x", encoding="utf-8")

        cands = _find_nested_candidates(tmp_path)
        by_name = {c.path.name: c for c in cands}
        assert set(by_name) == {"git-only", "claude-dir-only", "claude-md-only", "mixed"}
        assert by_name["git-only"].has_git and not by_name["git-only"].has_claude_signal
        assert by_name["claude-dir-only"].has_claude_dir
        assert by_name["claude-md-only"].has_claude_md
        m = by_name["mixed"]
        assert m.has_git and m.has_claude_dir and m.has_claude_md

    def test_sorted_case_insensitive(self, tmp_path):
        _make_git_repo(tmp_path / "Zeta")
        _make_claude_md(tmp_path / "alpha")
        _make_git_repo(tmp_path / "Mango")
        names = [c.path.name for c in _find_nested_candidates(tmp_path)]
        assert names == ["alpha", "Mango", "Zeta"]

    def test_does_not_recurse(self, tmp_path):
        _make_git_repo(tmp_path / "intermediate" / "deep-repo")
        # intermediate itself has neither .git nor .claude/ nor CLAUDE.md
        assert _find_nested_candidates(tmp_path) == []

    def test_empty_dir_returns_empty(self, tmp_path):
        assert _find_nested_candidates(tmp_path) == []


class TestResolveScanTargets:
    def test_path_with_own_claude_md_returns_itself(self, tmp_path):
        p = _make_claude_md(tmp_path / "project")
        assert _resolve_scan_targets(p) == [p]

    def test_path_with_own_claude_dir_returns_itself(self, tmp_path):
        p = _make_claude_dir(tmp_path / "project")
        assert _resolve_scan_targets(p) == [p]

    def test_own_claude_signal_short_circuits_picker_even_with_nested(
        self, tmp_path, monkeypatch
    ):
        """If the user pointed at a configured project, scan THAT — not its children.

        E.g. `agent-radar scan ./my-claude-project` should never trigger the
        picker just because the project contains nested git submodules etc.
        """
        p = _make_claude_md(tmp_path / "project")
        # Add a nested candidate that WOULD otherwise trigger the picker.
        _make_claude_md(p / "submodule")
        monkeypatch.setattr("sys.stdin", _fake_tty("q\n"))
        # No prompt should fire — the parent's Claude signal wins.
        assert _resolve_scan_targets(p) == [p]

    def test_path_with_git_only_and_nested_triggers_picker(
        self, tmp_path, monkeypatch, capsys
    ):
        """Reproduces the D:\\project bug.

        Parent has a `.git` (e.g. an accidental stale one) but no Claude
        signal of its own. It contains scannable subdirs. The picker MUST
        fire — the `.git` at parent level should not short-circuit the
        nested-candidate flow.
        """
        parent = tmp_path / "projects"
        _make_git_repo(parent)
        claude_child = _make_claude_md(parent / "active-project")
        _make_git_repo(parent / "plain-child")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))  # non-TTY
        result = _resolve_scan_targets(parent)
        assert result == [claude_child]
        assert "Auto-scanning" in capsys.readouterr().err

    def test_path_with_git_only_no_nested_returns_itself_as_fallback(self, tmp_path):
        """Bare git repo with no Claude content and no nested candidates →
        scan as-is (fallback). The freshly-init'd repo case."""
        repo = _make_git_repo(tmp_path / "r")
        assert _resolve_scan_targets(repo) == [repo]

    def test_no_candidates_returns_itself_as_fallback(self, tmp_path):
        d = tmp_path / "plain"
        d.mkdir()
        assert _resolve_scan_targets(d) == [d]

    def test_non_tty_auto_scans_claude_signal_dirs(
        self, tmp_path, monkeypatch, capsys
    ):
        claude_md_dir = _make_claude_md(tmp_path / "active")
        # git-only (no Claude signals) → should be skipped, not scanned
        _make_git_repo(tmp_path / "plain-git")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        result = _resolve_scan_targets(tmp_path)
        assert result == [claude_md_dir]
        err = capsys.readouterr().err
        assert "Auto-scanning" in err
        assert "active" in err
        assert "skipped 1 dir" in err

    def test_non_tty_no_claude_signals_skips_with_warning(
        self, tmp_path, monkeypatch, capsys
    ):
        _make_git_repo(tmp_path / "a")
        _make_git_repo(tmp_path / "b")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        result = _resolve_scan_targets(tmp_path)
        assert result == []
        err = capsys.readouterr().err
        assert "none have Claude Code signals" in err

    # ------------------------------------------------------------------
    # Text-picker fallback path — exercised when the keyboard-driven
    # interactive picker isn't available (e.g. niche platform without
    # msvcrt / termios). Tests force the fallback so we can drive it via
    # mocked stdin text.
    # ------------------------------------------------------------------

    def test_tty_enter_accepts_defaults(self, tmp_path, monkeypatch):
        claude_dir_a = _make_claude_md(tmp_path / "with-claude")
        _make_git_repo(tmp_path / "plain-git")
        _force_text_picker(monkeypatch)
        # Empty input == press Enter == accept defaults
        monkeypatch.setattr("sys.stdin", _fake_tty("\n"))
        result = _resolve_scan_targets(tmp_path)
        assert result == [claude_dir_a]

    def test_tty_eof_treated_as_accept_defaults(self, tmp_path, monkeypatch):
        claude_md_dir = _make_claude_md(tmp_path / "with-claude")
        _make_git_repo(tmp_path / "plain-git")
        _force_text_picker(monkeypatch)
        # No newline, immediate EOF → defaults applied
        monkeypatch.setattr("sys.stdin", _fake_tty(""))
        result = _resolve_scan_targets(tmp_path)
        assert result == [claude_md_dir]

    def test_tty_user_overrides_defaults_with_indices(self, tmp_path, monkeypatch):
        _make_claude_md(tmp_path / "alpha")          # would be default
        beta = _make_git_repo(tmp_path / "beta")     # NOT a default
        _make_claude_dir(tmp_path / "gamma")         # would be default
        _force_text_picker(monkeypatch)
        # User explicitly picks ONLY beta
        monkeypatch.setattr("sys.stdin", _fake_tty("2\n"))
        result = _resolve_scan_targets(tmp_path)
        assert result == [beta]

    def test_tty_all_returns_all_candidates(self, tmp_path, monkeypatch):
        a = _make_claude_md(tmp_path / "alpha")
        b = _make_git_repo(tmp_path / "beta")
        _force_text_picker(monkeypatch)
        monkeypatch.setattr("sys.stdin", _fake_tty("a\n"))
        assert _resolve_scan_targets(tmp_path) == [a, b]

    def test_tty_none_returns_empty(self, tmp_path, monkeypatch):
        _make_claude_md(tmp_path / "alpha")
        _force_text_picker(monkeypatch)
        monkeypatch.setattr("sys.stdin", _fake_tty("n\n"))
        assert _resolve_scan_targets(tmp_path) == []

    def test_tty_quit_returns_empty(self, tmp_path, monkeypatch):
        _make_claude_md(tmp_path / "alpha")
        _force_text_picker(monkeypatch)
        monkeypatch.setattr("sys.stdin", _fake_tty("q\n"))
        assert _resolve_scan_targets(tmp_path) == []

    def test_tty_reprompts_on_garbage(self, tmp_path, monkeypatch, capsys):
        a = _make_claude_md(tmp_path / "alpha")
        _force_text_picker(monkeypatch)
        # First "nope" rejected → re-prompt → "1" succeeds
        monkeypatch.setattr("sys.stdin", _fake_tty("nope\n1\n"))
        assert _resolve_scan_targets(tmp_path) == [a]
        assert "invalid input" in capsys.readouterr().err

    def test_prompt_shows_checkbox_markers(self, tmp_path, monkeypatch, capsys):
        _make_claude_md(tmp_path / "alpha")
        _make_git_repo(tmp_path / "beta")
        _force_text_picker(monkeypatch)
        monkeypatch.setattr("sys.stdin", _fake_tty("\n"))
        _resolve_scan_targets(tmp_path)
        err = capsys.readouterr().err
        # pre-selected gets [*], not pre-selected gets [ ]
        assert "[*]" in err
        assert "[ ]" in err


class TestScannerMainNestedFlow:
    def test_main_via_picker_accepts_defaults(self, tmp_path, monkeypatch):
        """CLI: non-repo parent + TTY + Enter → scans only Claude-signal dirs."""
        _write(tmp_path / "claude-active" / "CLAUDE.md", "x")
        _make_git_repo(tmp_path / "plain-git")
        out = tmp_path / "scan.json"

        # Drive via the text fallback (interactive picker uses raw key reads
        # that bypass sys.stdin and would hang in tests).
        _force_text_picker(monkeypatch)
        monkeypatch.setattr("sys.stdin", _fake_tty("\n"))
        monkeypatch.setattr("sys.argv", ["scanner", str(tmp_path), "-o", str(out)])

        scanner.main()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert [t["name"] for t in data["targets"]] == ["claude-active"]


# ---------------------------------------------------------------------------
# Interactive (keyboard) checkbox picker — unit tests via injected key stream.
# ---------------------------------------------------------------------------

class TestInteractiveCheckboxPicker:
    def _keys(self, *seq):
        """Make a _read_key_fn that yields the given key names in order."""
        it = iter(seq)
        return lambda: next(it)

    def test_enter_returns_defaults(self, tmp_path):
        a = _make_claude_md(tmp_path / "active")
        _make_git_repo(tmp_path / "plain")  # not default
        cands = _find_nested_candidates(tmp_path)
        result = _interactive_checkbox_picker(
            tmp_path, cands, _read_key_fn=self._keys("ENTER"),
        )
        assert result == [a]

    def test_space_toggles_off_a_default(self, tmp_path):
        _make_claude_md(tmp_path / "a")
        b = _make_claude_md(tmp_path / "b")
        cands = _find_nested_candidates(tmp_path)
        # Cursor starts at 0 (=a, default-on). SPACE toggles off, ENTER returns.
        result = _interactive_checkbox_picker(
            tmp_path, cands, _read_key_fn=self._keys("SPACE", "ENTER"),
        )
        assert result == [b]

    def test_down_then_space_toggles_on_a_non_default(self, tmp_path):
        a = _make_claude_md(tmp_path / "active")
        b = _make_git_repo(tmp_path / "plain")  # not default
        cands = _find_nested_candidates(tmp_path)
        # cursor 0=active(on); DOWN→1=plain(off); SPACE→on; ENTER.
        result = _interactive_checkbox_picker(
            tmp_path, cands,
            _read_key_fn=self._keys("DOWN", "SPACE", "ENTER"),
        )
        assert result == [a, b]

    def test_all_key_selects_everything(self, tmp_path):
        a = _make_claude_md(tmp_path / "a")
        b = _make_git_repo(tmp_path / "b")
        cands = _find_nested_candidates(tmp_path)
        result = _interactive_checkbox_picker(
            tmp_path, cands, _read_key_fn=self._keys("ALL", "ENTER"),
        )
        assert result == [a, b]

    def test_none_key_deselects_everything(self, tmp_path):
        _make_claude_md(tmp_path / "a")
        _make_claude_md(tmp_path / "b")
        cands = _find_nested_candidates(tmp_path)
        result = _interactive_checkbox_picker(
            tmp_path, cands, _read_key_fn=self._keys("NONE", "ENTER"),
        )
        assert result == []

    def test_quit_returns_empty(self, tmp_path):
        _make_claude_md(tmp_path / "a")
        cands = _find_nested_candidates(tmp_path)
        result = _interactive_checkbox_picker(
            tmp_path, cands, _read_key_fn=self._keys("QUIT"),
        )
        assert result == []

    def test_up_wraps_around_to_last(self, tmp_path):
        a = _make_claude_md(tmp_path / "a")
        _make_claude_md(tmp_path / "b")  # default-on; toggled off via wrap-up
        cands = _find_nested_candidates(tmp_path)
        # cursor 0=a; UP wraps to last index (1=b); SPACE toggles off b; ENTER.
        result = _interactive_checkbox_picker(
            tmp_path, cands,
            _read_key_fn=self._keys("UP", "SPACE", "ENTER"),
        )
        assert result == [a]

    def test_unknown_key_is_no_op(self, tmp_path):
        a = _make_claude_md(tmp_path / "a")
        cands = _find_nested_candidates(tmp_path)
        # None = unrecognized key from _read_key; should not crash, just loop.
        result = _interactive_checkbox_picker(
            tmp_path, cands, _read_key_fn=self._keys(None, "ENTER"),
        )
        assert result == [a]

    def test_keyboard_interrupt_returns_empty(self, tmp_path):
        _make_claude_md(tmp_path / "a")
        cands = _find_nested_candidates(tmp_path)

        def boom():
            raise KeyboardInterrupt

        result = _interactive_checkbox_picker(
            tmp_path, cands, _read_key_fn=boom,
        )
        assert result == []

    def test_renders_checkbox_markers_and_cursor(self, tmp_path, capsys):
        _make_claude_md(tmp_path / "with-signal")
        _make_git_repo(tmp_path / "no-signal")
        cands = _find_nested_candidates(tmp_path)
        _interactive_checkbox_picker(
            tmp_path, cands, _read_key_fn=self._keys("ENTER"),
        )
        err = capsys.readouterr().err
        assert "[X]" in err          # the pre-selected default
        assert "[ ]" in err          # the unchecked candidate
        assert ">" in err            # cursor pointer somewhere
        assert "Space toggle" in err # help line


class TestResolveScanTargetsInteractive:
    """Routing: TTY + interactive-capable env → interactive picker fires."""

    @staticmethod
    def _force_interactive(monkeypatch, keys):
        """Pin routing to the interactive picker with a scripted key stream."""
        # stdin.isatty must be True for the TTY branch to fire.
        monkeypatch.setattr("sys.stdin", _fake_tty(""))
        monkeypatch.setattr(
            "agent_radar.scanner._can_use_interactive_picker", lambda: True,
        )
        it = iter(keys)
        monkeypatch.setattr(
            "agent_radar.scanner._read_key", lambda: next(it),
        )

    def test_tty_routes_to_interactive_picker(self, tmp_path, monkeypatch):
        a = _make_claude_md(tmp_path / "active")
        _make_git_repo(tmp_path / "plain")
        self._force_interactive(monkeypatch, ["ENTER"])
        assert _resolve_scan_targets(tmp_path) == [a]

    def test_interactive_path_honors_space_toggle(self, tmp_path, monkeypatch):
        _make_claude_md(tmp_path / "a")  # default-on
        b = _make_claude_md(tmp_path / "b")  # also default-on
        self._force_interactive(monkeypatch, ["SPACE", "ENTER"])
        # SPACE at cursor 0 toggles off "a"; ENTER returns only b.
        assert _resolve_scan_targets(tmp_path) == [b]
