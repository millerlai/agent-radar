"""Collector interface — every backend normalises into UsageWindow.

UsageWindow is the single contract between collectors and the scoring engine
(usage_score). Adding a new backend only requires implementing UsageCollector.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class UsageWindow:
    """Aggregated usage signals for a single attribution scope (user or team)
    within a time window. Field shapes follow SPEC §5."""

    since: datetime
    until: datetime
    session_count: int = 0
    active_seconds: float = 0.0

    # skill_activated: skill_name -> {
    #   "total": int,
    #   "triggers": {"user-slash"|"claude-proactive"|"nested-skill": int},
    #   "sources":  {"bundled"|"userSettings"|"projectSettings"|"plugin": int},
    # }
    skills: dict = field(default_factory=dict)

    # mcp_server_connection: server_name -> {
    #   "connected": int, "failed": int, "disconnected": int,
    #   "transports": {transport_type: int},
    # }
    mcp: dict = field(default_factory=dict)

    # Servers that were actually invoked by a tool (from tool_result attrs).
    mcp_invoked: set = field(default_factory=set)

    # plugin_loaded: plugin_name -> load_count
    plugins: dict = field(default_factory=dict)

    # hook_event ("PreToolUse" etc.) -> {
    #   "registered": int, "executed": int,
    #   "blocking": int, "errors": int, "duration_ms": int
    # }
    hooks: dict = field(default_factory=dict)

    # at_mention: mention_type -> {"success": int, "fail": int}
    mentions: dict = field(default_factory=dict)

    # tool_decision aggregate
    decisions: dict = field(default_factory=lambda: {
        "accept": 0,
        "reject": 0,
        "by_source": {},
    })

    # Distinct subagent types observed (via tool_parameters.subagent_type or
    # token/cost metric agent.name).
    subagents: set = field(default_factory=set)

    # token / cost attribution
    token_by_skill: dict = field(default_factory=dict)
    cost_by_skill: dict = field(default_factory=dict)
    token_by_plugin: dict = field(default_factory=dict)
    cost_by_plugin: dict = field(default_factory=dict)
    token_by_agent: dict = field(default_factory=dict)
    cost_by_agent: dict = field(default_factory=dict)

    # Free-form diagnostic notes the collector wants to surface (e.g. "no
    # OTEL_LOG_TOOL_DETAILS detected — skill/MCP names will be redacted").
    notes: list = field(default_factory=list)

    def to_jsonable(self) -> dict:
        """Convert sets → sorted lists so json.dumps works."""
        d = {
            "since": self.since.isoformat(),
            "until": self.until.isoformat(),
            "session_count": self.session_count,
            "active_seconds": self.active_seconds,
            "skills": self.skills,
            "mcp": self.mcp,
            "mcp_invoked": sorted(self.mcp_invoked),
            "plugins": self.plugins,
            "hooks": self.hooks,
            "mentions": self.mentions,
            "decisions": self.decisions,
            "subagents": sorted(self.subagents),
            "token_by_skill": self.token_by_skill,
            "cost_by_skill": self.cost_by_skill,
            "token_by_plugin": self.token_by_plugin,
            "cost_by_plugin": self.cost_by_plugin,
            "token_by_agent": self.token_by_agent,
            "cost_by_agent": self.cost_by_agent,
            "notes": self.notes,
        }
        return d


class UsageCollector(Protocol):
    def fetch(
        self,
        since: datetime,
        until: datetime,
        account_filter: str | None = None,
    ) -> UsageWindow:
        """Query the backend and return an aggregated UsageWindow.

        account_filter narrows results to a single principal (matched against
        user.account_uuid or user.email). None = all observed accounts.
        """
        ...


# ----- helpers shared by collectors ---------------------------------------

def ensure_skill(window: UsageWindow, name: str) -> dict:
    return window.skills.setdefault(name, {
        "total": 0,
        "triggers": {},
        "sources": {},
    })


def ensure_mcp(window: UsageWindow, name: str) -> dict:
    return window.mcp.setdefault(name, {
        "connected": 0,
        "failed": 0,
        "disconnected": 0,
        "transports": {},
    })


def ensure_hook(window: UsageWindow, event: str) -> dict:
    return window.hooks.setdefault(event, {
        "registered": 0,
        "executed": 0,
        "blocking": 0,
        "errors": 0,
        "duration_ms": 0,
    })


def ensure_mention(window: UsageWindow, mtype: str) -> dict:
    return window.mentions.setdefault(mtype, {"success": 0, "fail": 0})


def bump(d: dict, key: str, n: int = 1) -> None:
    d[key] = d.get(key, 0) + n
