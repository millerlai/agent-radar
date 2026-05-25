"""Unit tests for agent_radar.session_scanner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_radar import session_scanner
from agent_radar.session_scanner import (
    CORRECTION_RE,
    _encode_path,
    _extract_text,
    _iter_jsonl,
    _walk_tool_uses,
    analyze_project,
)


# ---------------------------------------------------------------------------
# small helpers
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
# encoding helper
# ---------------------------------------------------------------------------

class TestEncodePath:
    def test_drive_letter_and_separators(self, tmp_path):
        # On any OS, separators in resolved string are mapped to "-"
        encoded = _encode_path(tmp_path)
        assert ":" not in encoded
        assert "\\" not in encoded
        assert "/" not in encoded


# ---------------------------------------------------------------------------
# JSONL iteration tolerance
# ---------------------------------------------------------------------------

class TestIterJsonl:
    def test_skips_bad_lines(self, tmp_path):
        f = tmp_path / "s.jsonl"
        f.write_text('{"a":1}\nnot json\n{"b":2}\n', encoding="utf-8")
        result = list(_iter_jsonl(f))
        assert result == [{"a": 1}, {"b": 2}]

    def test_missing_file_yields_nothing(self, tmp_path):
        assert list(_iter_jsonl(tmp_path / "missing.jsonl")) == []

    def test_empty_lines_ignored(self, tmp_path):
        f = tmp_path / "s.jsonl"
        f.write_text('\n{"a":1}\n\n', encoding="utf-8")
        assert list(_iter_jsonl(f)) == [{"a": 1}]


# ---------------------------------------------------------------------------
# text + tool_use extraction
# ---------------------------------------------------------------------------

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
# correction regex
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


# ---------------------------------------------------------------------------
# analyze_project end-to-end
# ---------------------------------------------------------------------------

class TestAnalyzeProject:
    def test_empty_project(self, tmp_path):
        proj = tmp_path / "C--repos-empty"
        proj.mkdir()
        rep = analyze_project(proj)
        assert rep.sessions == 0
        assert rep.total_messages == 0
        assert rep.overall >= 0

    def test_diverse_session(self, tmp_path):
        proj = tmp_path / "C--repos-x"
        proj.mkdir()
        entries = [
            _user_msg("please scan"),
            _assistant_with_tool("Read", file_path="/repo/a.py"),
            _assistant_with_tool("Read", file_path="/repo/a.py"),  # repeat
            _assistant_with_tool("Read", file_path="/repo/b.py"),
            _assistant_with_tool("Skill", skill="browse"),
            _assistant_with_tool("mcp__github__list_issues"),
            _assistant_with_tool("Agent", subagent_type="Explore",
                                 description="find usages"),
            _assistant_with_tool("Bash"),
            _user_msg("no, that's wrong"),
            _user_msg("thanks"),
        ]
        _write_jsonl(proj / "session-1.jsonl", entries)
        rep = analyze_project(proj)

        assert rep.sessions == 1
        assert rep.skill_calls == 1
        assert rep.mcp_calls == 1
        assert rep.subagent_calls == 1
        # a.py read twice → 1 repeat
        assert rep.reads_total == 3
        assert rep.reads_repeat == 1
        # corrections: 1 of 3 user messages → low_correction score < 100
        assert rep.corrections == 1
        assert rep.user_messages == 3

        # scoring keys present and within [0, 100]
        for v in rep.scores.values():
            assert 0 <= v <= 100

        # tool_diversity > 0 since multiple distinct tools used
        assert rep.scores["tool_diversity"] > 0
        # skill_triggered > 0
        assert rep.scores["skill_triggered"] > 0
        # mcp_triggered > 0
        assert rep.scores["mcp_triggered"] > 0
        # subagent_triggered > 0 because Agent tool fired
        assert rep.scores["subagent_triggered"] > 0

    def test_session_volume_buckets(self, tmp_path):
        """Cover the 3 bucket boundaries used by session_volume scoring."""
        # one session → 30
        proj = tmp_path / "C--repos-small"
        proj.mkdir()
        _write_jsonl(proj / "a.jsonl", [_user_msg("hi")])
        rep = analyze_project(proj)
        assert rep.scores["session_volume"] == 30

        # 5 sessions → 60
        proj2 = tmp_path / "C--repos-med"
        proj2.mkdir()
        for i in range(5):
            _write_jsonl(proj2 / f"s{i}.jsonl", [_user_msg("hi")])
        rep2 = analyze_project(proj2)
        assert rep2.scores["session_volume"] == 60

        # 12 sessions → 100
        proj3 = tmp_path / "C--repos-big"
        proj3.mkdir()
        for i in range(12):
            _write_jsonl(proj3 / f"s{i}.jsonl", [_user_msg("hi")])
        rep3 = analyze_project(proj3)
        assert rep3.scores["session_volume"] == 100

    def test_low_correction_zero_when_no_user_messages(self, tmp_path):
        proj = tmp_path / "C--no-user"
        proj.mkdir()
        # only assistant messages → low_correction detail says no user messages
        _write_jsonl(proj / "a.jsonl", [_assistant_with_tool("Read", file_path="x")])
        rep = analyze_project(proj)
        assert rep.scores["low_correction"] == 0

    def test_context_efficiency_no_reads_neutral(self, tmp_path):
        proj = tmp_path / "C--no-reads"
        proj.mkdir()
        _write_jsonl(proj / "a.jsonl", [_user_msg("hi")])
        rep = analyze_project(proj)
        # no Read calls → neutral 50
        assert rep.scores["context_efficiency"] == 50

    def test_subagent_triggered_zero_without_agent_tool(self, tmp_path):
        proj = tmp_path / "C--no-subagent"
        proj.mkdir()
        # Bash + Read but no Agent → subagent_calls 0, score 0, .none detail
        entries = [
            _user_msg("just bash"),
            _assistant_with_tool("Bash"),
            _assistant_with_tool("Read", file_path="/x.py"),
        ]
        _write_jsonl(proj / "a.jsonl", entries)
        rep = analyze_project(proj)
        assert rep.subagent_calls == 0
        assert rep.scores["subagent_triggered"] == 0
        sub_finding = next(f for f in rep.findings
                           if f["dimension"] == "subagent_triggered")
        assert sub_finding["detail_key"].endswith(".none")

    def test_usage_dimension_keys_contain_subagent(self):
        assert "subagent_triggered" in session_scanner.USAGE_DIMENSION_KEYS


# ---------------------------------------------------------------------------
# CLI main
# ---------------------------------------------------------------------------

class TestSessionMainCli:
    def test_main_with_projects_dir(self, tmp_path, monkeypatch):
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
        assert "usage_dimensions" in data
        assert "targets" in data
        assert len(data["targets"]) == 1

    def test_main_missing_projects_dir_exits(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "sys.argv",
            ["session", "--projects-dir", str(tmp_path / "nope")],
        )
        with pytest.raises(SystemExit):
            session_scanner.main()
