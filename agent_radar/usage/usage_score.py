"""Convert a UsageWindow into per-dimension 0–100 scores.

The dimension keys MUST mirror ``agent_radar.scanner``'s DIMENSIONS exactly so
the merge step can stack config vs usage on the same radar axes.

`iteration` has no usage signal — it is intentionally returned as None, and the
report renders it as N/A with a dashed line.

Findings carry ``label_key`` / ``detail_key`` + ``detail_args`` (i18n-ready);
``agent_radar.report`` resolves them via ``agent_radar.i18n`` per ``--lang``.
"""

from __future__ import annotations


from .collectors.base import UsageWindow


# Keep in sync with scanner.DIMENSION_KEYS — 0.2.0 dropped "iteration" as a
# top-level axis (folded into claude_md as a fact-based sub-signal).
USAGE_DIMENSION_KEYS = [
    "claude_md", "skills", "mcp", "automation", "context_hygiene",
]


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


# ---------------------------------------------------------------------------
# per-dimension scoring
# ---------------------------------------------------------------------------

def _score_skills(w: UsageWindow) -> tuple[float, list[dict]]:
    total = sum(s["total"] for s in w.skills.values())
    proactive = sum(
        s["triggers"].get("claude-proactive", 0) for s in w.skills.values()
    )
    sessions = max(w.session_count, 1)
    distinct = sum(1 for s in w.skills.values() if s["total"] > 0)

    activation_rate = min(total / sessions, 1.0)
    proactive_ratio = _safe_div(proactive, total)
    distinct_bonus = 1.0 if distinct > 0 else 0.0

    score = _clamp(40 * activation_rate + 40 * proactive_ratio + 20 * distinct_bonus)

    findings = [
        {
            "label_key": "usage.skills.trigger_count",
            "weight": 40,
            "score": round(40 * activation_rate, 1),
            "detail_key": "usage.skills.trigger_count.detail",
            "detail_args": {
                "total": total, "sessions": w.session_count, "rate": activation_rate,
            },
        },
        {
            "label_key": "usage.skills.proactive",
            "weight": 40,
            "score": round(40 * proactive_ratio, 1),
            "detail_key": "usage.skills.proactive.detail",
            "detail_args": {"p": proactive, "t": total, "pct": proactive_ratio * 100},
        },
        {
            "label_key": "usage.skills.at_least_one",
            "weight": 20,
            "score": round(20 * distinct_bonus, 1),
            "detail_key": "usage.skills.at_least_one.detail",
            "detail_args": {"n": distinct},
        },
    ]
    return round(score, 1), findings


def _score_mcp(w: UsageWindow, servers_configured: int | None) -> tuple[float, list[dict]]:
    connected = sum(b["connected"] for b in w.mcp.values())
    failed = sum(b["failed"] for b in w.mcp.values())
    health = _safe_div(connected, connected + failed)

    if servers_configured is None or servers_configured <= 0:
        servers_configured = max(len(w.mcp), 1)
    used_ratio = min(_safe_div(len(w.mcp_invoked), servers_configured), 1.0)

    score = _clamp(50 * health + 50 * used_ratio)
    invoked = len(w.mcp_invoked)
    has_scan_suffix = invoked == servers_configured or servers_configured > len(w.mcp)
    suffixes = ([["usage.mcp.used_ratio.suffix_scan", {}]] if has_scan_suffix else [])
    findings = [
        {
            "label_key": "usage.mcp.health",
            "weight": 50,
            "score": round(50 * health, 1),
            "detail_key": "usage.mcp.health.detail",
            "detail_args": {"c": connected, "f": failed, "pct": health * 100},
        },
        {
            "label_key": "usage.mcp.used_ratio",
            "weight": 50,
            "score": round(50 * used_ratio, 1),
            "detail_key": "usage.mcp.used_ratio.detail",
            "detail_args": {
                "invoked": invoked, "configured": servers_configured,
                "_suffixes": suffixes,
            },
        },
    ]
    return round(score, 1), findings


def _score_automation(
    w: UsageWindow,
    hooks_registered_static: int | None,
    plugins_installed: int | None,
) -> tuple[float, list[dict]]:
    hooks_registered = sum(b["registered"] for b in w.hooks.values())
    hooks_executed = sum(b["executed"] for b in w.hooks.values())
    reg_denom = hooks_registered_static or hooks_registered
    hook_ratio = min(_safe_div(hooks_executed, reg_denom), 1.0) if reg_denom else 0.0

    plugins_loaded = len(w.plugins)
    if plugins_installed is None or plugins_installed <= 0:
        plugins_installed = max(plugins_loaded, 1)
    plugin_ratio = min(_safe_div(plugins_loaded, plugins_installed), 1.0)

    subagent_used = 1.0 if w.subagents else 0.0

    score = _clamp(40 * hook_ratio + 35 * plugin_ratio + 25 * subagent_used)
    findings = [
        {
            "label_key": "usage.automation.hook_rate",
            "weight": 40,
            "score": round(40 * hook_ratio, 1),
            "detail_key": ("usage.automation.hook_rate.detail" if reg_denom
                           else "usage.automation.hook_rate.empty"),
            "detail_args": ({"e": hooks_executed, "r": reg_denom,
                             "pct": hook_ratio * 100} if reg_denom else {}),
        },
        {
            "label_key": "usage.automation.plugin_ratio",
            "weight": 35,
            "score": round(35 * plugin_ratio, 1),
            "detail_key": "usage.automation.plugin_ratio.detail",
            "detail_args": {"loaded": plugins_loaded, "installed": plugins_installed,
                            "pct": plugin_ratio * 100},
        },
        {
            "label_key": "usage.automation.subagent",
            "weight": 25,
            "score": round(25 * subagent_used, 1),
            "detail_key": ("usage.automation.subagent.have" if w.subagents
                           else "usage.automation.subagent.none"),
            "detail_args": ({"n": len(w.subagents)} if w.subagents else {}),
        },
    ]
    return round(score, 1), findings


def _score_context_hygiene(w: UsageWindow) -> tuple[float, list[dict]]:
    file_mentions = w.mentions.get("file", {})
    file_count = file_mentions.get("success", 0) + file_mentions.get("fail", 0)
    sessions = max(w.session_count, 1)
    file_mention_rate = min(file_count / sessions, 1.0)

    total_mentions = sum(b["success"] + b["fail"] for b in w.mentions.values())
    total_success = sum(b["success"] for b in w.mentions.values())
    success_rate = _safe_div(total_success, total_mentions)

    score = _clamp(60 * file_mention_rate + 40 * success_rate)
    findings = [
        {
            "label_key": "usage.context.mention_rate",
            "weight": 60,
            "score": round(60 * file_mention_rate, 1),
            "detail_key": "usage.context.mention_rate.detail",
            "detail_args": {"count": file_count, "sessions": w.session_count,
                            "rate": file_mention_rate},
        },
        {
            "label_key": "usage.context.mention_success",
            "weight": 40,
            "score": round(40 * success_rate, 1),
            "detail_key": ("usage.context.mention_success.detail" if total_mentions
                           else "usage.context.mention_success.empty"),
            "detail_args": ({"ok": total_success, "total": total_mentions}
                            if total_mentions else {}),
        },
    ]
    return round(score, 1), findings


def _score_claude_md_effectiveness(w: UsageWindow) -> tuple[float, list[dict]]:
    accepts = w.decisions["accept"]
    rejects = w.decisions["reject"]
    total = accepts + rejects
    reject_ratio = _safe_div(rejects, total)
    score = _clamp(100 * (1 - reject_ratio))
    findings = [
        {
            "label_key": "usage.claude_md.accept_rate",
            "weight": 100,
            "score": round(score, 1),
            "detail_key": ("usage.claude_md.accept_rate.detail" if total
                           else "usage.claude_md.accept_rate.empty"),
            "detail_args": ({"a": accepts, "t": total, "pct": reject_ratio * 100}
                            if total else {}),
        },
    ]
    return round(score, 1), findings


# ---------------------------------------------------------------------------
# top-level API
# ---------------------------------------------------------------------------

def score_window(window: UsageWindow, scan_context: dict | None = None) -> dict:
    """Score a UsageWindow.

    `scan_context` is an optional dict carrying counts from the static scan
    (provides the denominators for usage ratios):
        {"servers_configured": int, "hooks_registered": int, "plugins_installed": int}
    """
    ctx = scan_context or {}
    skills_score, skills_f = _score_skills(window)
    mcp_score, mcp_f = _score_mcp(window, ctx.get("servers_configured"))
    auto_score, auto_f = _score_automation(
        window, ctx.get("hooks_registered"), ctx.get("plugins_installed"))
    ctx_score, ctx_f = _score_context_hygiene(window)
    md_score, md_f = _score_claude_md_effectiveness(window)

    scores = {
        "claude_md": md_score,
        "skills": skills_score,
        "mcp": mcp_score,
        "automation": auto_score,
        "context_hygiene": ctx_score,
    }
    findings_by_dim = {
        "claude_md": md_f,
        "skills": skills_f,
        "mcp": mcp_f,
        "automation": auto_f,
        "context_hygiene": ctx_f,
    }
    totals = {
        "session_count": window.session_count,
        "active_seconds": window.active_seconds,
        "skills_activated_total": sum(s["total"] for s in window.skills.values()),
        "mcp_connected_total": sum(b["connected"] for b in window.mcp.values()),
        "mcp_servers_invoked": len(window.mcp_invoked),
        "hooks_executed_total": sum(b["executed"] for b in window.hooks.values()),
        "subagents_distinct": len(window.subagents),
        "tool_accepts": window.decisions["accept"],
        "tool_rejects": window.decisions["reject"],
    }
    valid = [s for s in scores.values() if s is not None]
    overall = round(sum(valid) / len(valid), 1) if valid else 0.0

    return {
        "scores": scores,
        "overall": overall,
        "findings_by_dim": findings_by_dim,
        "totals": totals,
        "notes": list(window.notes),
        "window": {
            "since": window.since.isoformat(),
            "until": window.until.isoformat(),
        },
    }
