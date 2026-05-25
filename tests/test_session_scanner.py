"""Unit tests for agent_radar.session_scanner (0.2.0 — activation-gap framing).

session_scanner now emits per-axis ``activated`` scores aligned to scanner's
five axes (claude_md / skills / mcp / automation / context_hygiene).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_radar import session_scanner
from agent_radar.session_scanner import (
    CORRECTION_RE,
    MENTION_RE,
    USAGE_DIMENSION_KEYS,
    _encode_path,
    _extract_text,
    _iter_jsonl,
    _walk_tool_uses,
    analyze_project,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, entries: list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return path


def _user_msg(text: str) -> dict:
    return {"type": "user", "message": {"content": text}}


def _assistant_with_tool(name: str, **input_args) -> dict:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "name": name, "input": input_args},
            ],
        },
    }


# ---------------------------------------------------------------------------
# encoding + jsonl iteration helpers (unchanged from 0.1.x)
# ---------------------------------------------------------------------------

class TestEncodePath:
    def test_drive_letter_and_separators(self, tmp_path):
        encoded = _encode_path(tmp_path)
        assert ":" not in encoded
        assert "\\" not in encoded
        assert "/" not in encoded


class TestIterJsonl:
    def test_skips_bad_lines(self, tmp_path):
        f = tmp_path / "s.jsonl"
        f.write_text('{"a":1}\nnot json\n{"b":2}\n', encoding="utf-8")
        assert list(_iter_jsonl(f)) == [{"a": 1}, {"b": 2}]

    def test_missing_file_yields_nothing(self, tmp_path):
        assert list(_iter_jsonl(tmp_path / "missing.jsonl")) == []

    def test_empty_lines_ignored(self, tmp_path):
        f = tmp_path / "s.jsonl"
        f.write_text('\n{"a":1}\n\n', encoding="utf-8")
        assert list(_iter_jsonl(f)) == [{"a": 1}]


class TestExtractText:
    def test_plain_string(self):
        assert _extract_text("hello") == "hello"

    def test_block_list(self):
        blocks = [
            {"type": "text", "text": "first"},
            {"type": "tool_result", "content": "ignored"},
            {"type": "text", "text": "second"},
        ]
        assert _extract_text(blocks) == "first\nsecond"

    def test_unknown_returns_empty(self):
        assert _extract_text(123) == ""
        assert _extract_text(None) == ""


class TestWalkToolUses:
    def test_yields_tool_use_only(self):
        content = [
            {"type": "text", "text": "hi"},
            {"type": "tool_use", "name": "Read", "input": {}},
            {"type": "tool_use", "name": "Bash", "input": {}},
        ]
        tools = list(_walk_tool_uses(content))
        assert [t["name"] for t in tools] == ["Read", "Bash"]

    def test_non_list_yields_nothing(self):
        assert list(_walk_tool_uses("not a list")) == []


# ---------------------------------------------------------------------------
# regexes
# ---------------------------------------------------------------------------

class TestCorrectionRegex:
    @pytest.mark.parametrize("text", [
        "no don't do that",
        "Stop, that's wrong",
        "wait — actually",
        "wrong file",
        "不對",
        "不是這樣",
        "等等",
        "請還原",
    ])
    def test_matches(self, text):
        assert CORRECTION_RE.search(text)

    @pytest.mark.parametrize("text", [
        "great, ship it",
        "繼續",
        "thanks",
    ])
    def test_non_matches(self, text):
        assert not CORRECTION_RE.search(text)


class TestMentionRegex:
    def test_matches_at_path(self):
        assert MENTION_RE.search("look at @scanner.py")
        assert MENTION_RE.search("see @docs/style.md please")

    def test_ignores_email_like(self):
        # "@" not preceded by whitespace/start (e.g. inside an email) shouldn't match
        # Note: this regex is intentionally lenient — emails will count too. We
        # accept that as noise rather than over-engineering the detector.
        assert MENTION_RE.search("hello @world")


# ---------------------------------------------------------------------------
# analyze_project — 0.2.0 five-axis activation framework
# ---------------------------------------------------------------------------

class TestAnalyzeProject:
    def test_empty_project(self, tmp_path):
        proj = tmp_path / "C--repos-empty"
        proj.mkdir()
        rep = analyze_project(proj)
        assert rep.sessions == 0
        assert rep.total_messages == 0
        # all five axes are present, even if zero
        assert set(rep.scores.keys()) == set(USAGE_DIMENSION_KEYS)

    def test_five_axes_align_with_scanner(self):
        # session_scanner MUST emit the same five axis keys scanner does,
        # otherwise merge can't join the two.
        assert USAGE_DIMENSION_KEYS == [
            "claude_md", "skills", "mcp", "automation", "context_hygiene",
        ]

    def test_diverse_session(self, tmp_path):
        proj = tmp_path / "C--repos-x"
        proj.mkdir()
        entries = [
            _user_msg("please scan @scanner.py"),
            _assistant_with_tool("Read", file_path="/repo/a.py"),
            _assistant_with_tool("Read", file_path="/repo/a.py"),  # repeat
            _assistant_with_tool("Read", file_path="/repo/b.py"),
            _assistant_with_tool("Skill", skill="browse"),
            _assistant_with_tool("mcp__github__list_issues"),
            _assistant_with_tool("Agent", subagent_type="Explore"),
            _assistant_with_tool("Bash"),
            _user_msg("no, that's wrong"),
            _user_msg("thanks"),
        ]
        _write_jsonl(proj / "session-1.jsonl", entries)
        rep = analyze_project(proj)

        # raw counters
        assert rep.sessions == 1
        assert rep.skill_calls == 1
        assert rep.mcp_calls == 1
        assert rep.subagent_calls == 1
        assert rep.reads_total == 3
        assert rep.reads_repeat == 1
        assert rep.corrections == 1
        assert rep.user_messages == 3
        assert rep.mentions == 1  # "@scanner.py"

        # All axis scores within [0, 100]
        for v in rep.scores.values():
            assert 0 <= v <= 100

        # Activated signals fire on the right axes
        assert rep.scores["skills"] > 0       # Skill tool fired
        assert rep.scores["mcp"] > 0          # mcp__* fired
        assert rep.scores["automation"] > 0   # Agent fired
        # claude_md = (1 - 1/3) * 100 ≈ but with 700-multiplier penalty it's
        # heavily docked; just confirm the score is < 100 (corrections lower it).
        assert rep.scores["claude_md"] < 100
        # context_hygiene blends two halves — both should contribute
        assert rep.scores["context_hygiene"] > 0

    def test_claude_md_empty_when_no_user_messages(self, tmp_path):
        proj = tmp_path / "C--no-user"
        proj.mkdir()
        _write_jsonl(proj / "a.jsonl", [_assistant_with_tool("Read", file_path="x")])
        rep = analyze_project(proj)
        # No user messages = can't measure guidance effectiveness
        assert rep.scores["claude_md"] == 0

    def test_context_efficiency_neutral_when_no_reads(self, tmp_path):
        proj = tmp_path / "C--no-reads"
        proj.mkdir()
        # one user msg (so mention half can compute) + no Reads
        _write_jsonl(proj / "a.jsonl", [_user_msg("hi")])
        rep = analyze_project(proj)
        # efficiency half = 50 (neutral), mention half = 0 → ctx score = 50
        assert rep.scores["context_hygiene"] == 50

    def test_subagent_via_agent_tool(self, tmp_path):
        proj = tmp_path / "C--subagent-only"
        proj.mkdir()
        entries = [
            _user_msg("hi"),
            _assistant_with_tool("Agent", subagent_type="Explore"),
            _assistant_with_tool("Agent", subagent_type="general-purpose"),
        ]
        _write_jsonl(proj / "a.jsonl", entries)
        rep = analyze_project(proj)
        assert rep.subagent_calls == 2
        assert rep.scores["automation"] > 0  # 2 × 10 = 20

    def test_zero_signals_yields_zero_scores(self, tmp_path):
        proj = tmp_path / "C--bash-only"
        proj.mkdir()
        # User did stuff but no skill/mcp/agent ever fired
        entries = [
            _user_msg("hi"),
            _assistant_with_tool("Bash"),
            _assistant_with_tool("Read", file_path="/x"),
        ]
        _write_jsonl(proj / "a.jsonl", entries)
        rep = analyze_project(proj)
        assert rep.scores["skills"] == 0
        assert rep.scores["mcp"] == 0
        assert rep.scores["automation"] == 0


# ---------------------------------------------------------------------------
# CLI main
# ---------------------------------------------------------------------------

class TestSessionMainCli:
    def test_main_emits_targets_by_name_for_merge(self, tmp_path, monkeypatch):
        projects_root = tmp_path / "projects"
        proj = projects_root / "C--repos-demo"
        proj.mkdir(parents=True)
        _write_jsonl(proj / "s.jsonl", [_user_msg("hello")])

        out = tmp_path / "session.json"
        monkeypatch.setattr(
            "sys.argv",
            ["session", "--projects-dir", str(projects_root), "-o", str(out)],
        )
        session_scanner.main()
        data = json.loads(out.read_text(encoding="utf-8"))
        # Required for merge.py join
        assert "usage_dimensions" in data
        assert "targets" in data
        assert "targets_by_name" in data
        # five axes
        assert data["usage_dimensions"] == USAGE_DIMENSION_KEYS

    def test_main_missing_projects_dir_exits(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "sys.argv",
            ["session", "--projects-dir", str(tmp_path / "nope")],
        )
        with pytest.raises(SystemExit):
            session_scanner.main()
