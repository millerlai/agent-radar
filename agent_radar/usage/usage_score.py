"""Convert a UsageWindow into per-dimension 0–100 scores.

The dimension keys MUST mirror ``agent_radar.scanner``'s DIMENSIONS exactly so
the merge step can stack config vs usage on the same radar axes.

`iteration` has no usage signal — it is intentionally returned as None, and the
report renders it as N/A with a dashed line.
"""

from __future__ import annotations


from .collectors.base import UsageWindow


# Keep in sync with scanner.DIMENSIONS keys.
USAGE_DIMENSIONS = {
    "claude_md": "CLAUDE.md 生效度 (間接)",
    "skills": "Skills 運用",
    "mcp": "MCP 運用",
    "automation": "自動化運用",
    "context_hygiene": "情境引用",
    "iteration": "迭代與維護",
}


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
            "label": "Skill 觸發次數",
            "weight": 40,
            "score": round(40 * activation_rate, 1),
            "detail": f"{total} 次觸發 / {w.session_count} session "
                      f"(activation_rate={activation_rate:.2f})",
        },
        {
            "label": "proactive 觸發比例",
            "weight": 40,
            "score": round(40 * proactive_ratio, 1),
            "detail": f"{proactive}/{total} 為模型主動觸發 "
                      f"({proactive_ratio*100:.0f}%) — 反映 description 觸發力",
        },
        {
            "label": "至少用過 1 個 skill",
            "weight": 20,
            "score": round(20 * distinct_bonus, 1),
            "detail": f"{distinct} 個 skill 被觸發過",
        },
    ]
    return round(score, 1), findings


def _score_mcp(w: UsageWindow, servers_configured: int | None) -> tuple[float, list[dict]]:
    connected = sum(b["connected"] for b in w.mcp.values())
    failed = sum(b["failed"] for b in w.mcp.values())
    health = _safe_div(connected, connected + failed)

    # If scan didn't tell us how many were configured, fall back to the count
    # of server_names we ever saw a connection event for. That biases toward
    # 100% when everything connected, which is fine — there's nothing else.
    if servers_configured is None or servers_configured <= 0:
        servers_configured = max(len(w.mcp), 1)
    used_ratio = min(_safe_div(len(w.mcp_invoked), servers_configured), 1.0)

    score = _clamp(50 * health + 50 * used_ratio)
    findings = [
        {
            "label": "連線健康度",
            "weight": 50,
            "score": round(50 * health, 1),
            "detail": f"connected={connected}, failed={failed} "
                      f"(health={health*100:.0f}%)",
        },
        {
            "label": "被工具呼叫的 server 比例",
            "weight": 50,
            "score": round(50 * used_ratio, 1),
            "detail": f"{len(w.mcp_invoked)}/{servers_configured} server 曾被呼叫"
                      + (" (configured 由 scan.json 提供)"
                         if servers_configured == len(w.mcp_invoked) or
                         servers_configured > len(w.mcp) else ""),
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
    # prefer the static count when present, since some hooks may register
    # without ever firing during the observation window.
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
            "label": "Hook 觸發率",
            "weight": 40,
            "score": round(40 * hook_ratio, 1),
            "detail": f"{hooks_executed}/{reg_denom} 已執行的 hook "
                      f"({hook_ratio*100:.0f}%)" if reg_denom
                      else "尚無 hook 註冊紀錄",
        },
        {
            "label": "Plugin 載入比例",
            "weight": 35,
            "score": round(35 * plugin_ratio, 1),
            "detail": f"{plugins_loaded}/{plugins_installed} plugin 載入"
                      f" ({plugin_ratio*100:.0f}%)",
        },
        {
            "label": "Subagent 使用",
            "weight": 25,
            "score": round(25 * subagent_used, 1),
            "detail": f"{len(w.subagents)} 種 subagent 被派遣" if w.subagents
                      else "未使用任何 subagent",
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
            "label": "@ 引用頻率 (per session)",
            "weight": 60,
            "score": round(60 * file_mention_rate, 1),
            "detail": f"{file_count} 次 @file 引用 / {w.session_count} session "
                      f"(rate={file_mention_rate:.2f})",
        },
        {
            "label": "@ 解析成功率",
            "weight": 40,
            "score": round(40 * success_rate, 1),
            "detail": f"{total_success}/{total_mentions} 解析成功"
                      if total_mentions else "尚無 @ 引用紀錄",
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
            "label": "tool_decision 接受率 (間接)",
            "weight": 100,
            "score": round(score, 1),
            "detail": f"{accepts}/{total} 工具提議被接受 "
                      f"(reject_ratio={reject_ratio*100:.1f}%)"
                      if total else "尚無 tool_decision 事件",
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

    Returns:
        {
          "scores": {dim: float|None, ...},   # iteration is None
          "findings_by_dim": {dim: [{label, weight, score, detail}, ...]},
          "totals": {...},                    # diagnostic counts
          "notes": [...],
        }
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
        "iteration": None,  # N/A — no usage-side signal for iteration
    }
    findings_by_dim = {
        "claude_md": md_f,
        "skills": skills_f,
        "mcp": mcp_f,
        "automation": auto_f,
        "context_hygiene": ctx_f,
        "iteration": [],
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
    # overall ignores None (iteration)
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
