"""agent-radar :: agent_radar.i18n
================================
Localizable strings for findings, blind spots, gap hints, and dimensions.

0.2.0 reset: only keys currently emitted by ``scanner`` / ``session_scanner``
remain. Heuristic-quality keys from 0.1.x (structure/imperative/concise grades,
skills description-quality grades) were removed along with their producers.

Producers (``scanner``, ``session_scanner``, ``usage_score``, ``merge``) emit
language-neutral keys + arg dicts into JSON. ``report`` resolves text per
``--lang`` at render time.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Finding labels — short titles shown in the report's accordion summaries.
# ---------------------------------------------------------------------------

FINDING_LABELS: dict[str, dict[str, str]] = {
    # ----- scanner.py (configured-side facts) -----
    "scan.claude_md.exists":       {"en": "CLAUDE.md exists",                "zh": "CLAUDE.md 存在"},
    "scan.claude_md.import":       {"en": "@import references",              "zh": "@import 引用"},
    "scan.claude_md.lint_size":    {"en": "Lint: file size",                 "zh": "Lint: 檔案大小"},
    "scan.claude_md.iteration":    {"en": "Iteration evidence",              "zh": "迭代證據"},
    "scan.skills.exists":          {"en": "Skills present",                  "zh": "Skills 存在"},
    "scan.skills.lint_hygiene":    {"en": "Lint: frontmatter & token hygiene", "zh": "Lint: frontmatter & token 衛生"},
    "scan.mcp.server_count":       {"en": "MCP server count",                "zh": "MCP server 數量"},
    "scan.mcp.category_breadth":   {"en": "MCP category breadth",            "zh": "MCP 類型廣度"},
    "scan.automation.hooks":       {"en": "Hooks",                           "zh": "Hooks"},
    "scan.automation.subagents":   {"en": "Subagents",                       "zh": "Subagents"},
    "scan.automation.commands":    {"en": "Custom slash commands",           "zh": "自訂 slash commands"},
    "scan.automation.plugins":     {"en": "Plugins",                         "zh": "Plugins"},
    "scan.context.split":          {"en": "User/Project split",              "zh": "User/Project 分工"},
    "scan.context.shared_personal":{"en": "Shared vs personal config",       "zh": "共享/個人設定區分"},
    "scan.context.modular":        {"en": "Modular references",              "zh": "模組化引用"},

    # ----- session_scanner.py (activated-side facts) -----
    "session.claude_md.guidance":      {"en": "Guidance effectiveness (low correction rate)",
                                        "zh": "指導生效度 (低糾正率)"},
    "session.skills.calls":            {"en": "Skill tool invocations",      "zh": "Skill tool 呼叫"},
    "session.mcp.calls":               {"en": "MCP tool invocations",        "zh": "MCP tool 呼叫"},
    "session.automation.subagent_calls":{"en": "Subagent dispatches",        "zh": "Subagent 派遣"},
    "session.context.efficiency":      {"en": "Read efficiency (low repetition)",
                                        "zh": "Read 效率 (低重複)"},
    "session.context.mention":         {"en": "@ reference rate",            "zh": "@ 引用頻率"},

    # ----- usage_score.py (OTel, optional advanced path — kept for future use) -----
    "usage.skills.trigger_count":  {"en": "Skill trigger count",             "zh": "Skill 觸發次數"},
    "usage.skills.proactive":      {"en": "Proactive trigger ratio",         "zh": "proactive 觸發比例"},
    "usage.skills.at_least_one":   {"en": "At least one skill used",         "zh": "至少用過 1 個 skill"},
    "usage.mcp.health":            {"en": "Connection health",               "zh": "連線健康度"},
    "usage.mcp.used_ratio":        {"en": "Ratio of servers invoked",        "zh": "被工具呼叫的 server 比例"},
    "usage.automation.hook_rate":  {"en": "Hook trigger rate",               "zh": "Hook 觸發率"},
    "usage.automation.plugin_ratio":{"en": "Plugin load ratio",              "zh": "Plugin 載入比例"},
    "usage.automation.subagent":   {"en": "Subagent usage",                  "zh": "Subagent 使用"},
    "usage.context.mention_rate":  {"en": "@ reference rate (per session)",  "zh": "@ 引用頻率 (per session)"},
    "usage.context.mention_success":{"en": "@ resolution success rate",      "zh": "@ 解析成功率"},
    "usage.claude_md.accept_rate": {"en": "tool_decision accept rate (indirect)", "zh": "tool_decision 接受率 (間接)"},
}


# ---------------------------------------------------------------------------
# Finding details — sentence templates with placeholders.
# ---------------------------------------------------------------------------

FINDING_DETAILS: dict[str, dict[str, str]] = {
    # ----- scan.claude_md -----
    "scan.claude_md.exists.found":     {"en": "Found {paths}",                              "zh": "找到 {paths}"},
    "scan.claude_md.exists.none":      {"en": "No CLAUDE.md found",                         "zh": "未發現 CLAUDE.md"},
    "scan.claude_md.import.have":      {"en": "{n} @ reference(s)",                         "zh": "{n} 處 @ 引用"},
    "scan.claude_md.import.none":      {"en": "@import not used to split files",            "zh": "未使用 @import 拆檔"},
    "scan.claude_md.lint_size.ok":     {"en": "{chars} chars (within limit)",               "zh": "{chars} chars (合規)"},
    "scan.claude_md.lint_size.soft":   {"en": "{chars} chars (large — consider splitting or trimming)",
                                        "zh": "{chars} chars (偏大,建議拆檔或精簡)"},
    "scan.claude_md.lint_size.hard":   {"en": "{chars} chars (oversize — violates cclint guidance, wastes context)",
                                        "zh": "{chars} chars (過大,違反 cclint 建議,context 浪費)"},
    "scan.claude_md.iteration.detail": {"en": "{commits} git commit(s) on CLAUDE.md; {hits} iteration-loop content signal(s) (lessons-learned / do-not-repeat / dated rules)",
                                        "zh": "{commits} 次 git 修改 CLAUDE.md;{hits} 處內容迭代訊號 (教訓 / 不要再 / 日期戳記)"},

    # ----- scan.skills -----
    "scan.skills.exists.have":         {"en": "Found {n} SKILL.md file(s)",                 "zh": "找到 {n} 個 SKILL.md"},
    "scan.skills.exists.none":         {"en": "Skills not in use",                          "zh": "未使用 skills"},
    "scan.skills.lint.detail":         {"en": "frontmatter compliant {fm}/{n}",
                                        "zh": "frontmatter 合規 {fm}/{n}"},
    "scan.skills.lint.decor_suffix":   {"en": ", {n} ASCII-art / decorative banner violation(s)",
                                        "zh": ", {n} 處 ASCII art/裝飾性內容"},
    "scan.skills.lint.oversize_suffix":{"en": ", {n} oversize file(s)",                    "zh": ", 行數超標 {n}"},

    # ----- scan.mcp -----
    "scan.mcp.server_count.have":      {"en": "{n} MCP server(s)",                          "zh": "{n} 個 MCP server"},
    "scan.mcp.server_count.none":      {"en": "No MCP server configured",                   "zh": "未設定任何 MCP server"},
    "scan.mcp.category_breadth.have":  {"en": "Categories covered: {cats}",                 "zh": "涵蓋類別: {cats}"},
    "scan.mcp.category_breadth.none":  {"en": "Could not classify categories",              "zh": "無法辨識類別"},

    # ----- scan.automation -----
    "scan.automation.hooks.have":      {"en": "Hooks configured",                           "zh": "偵測到 hooks 設定"},
    "scan.automation.hooks.none":      {"en": "Hooks not in use",                           "zh": "未使用 hooks"},
    "scan.automation.hooks.invalid":   {"en": "Lint: .claude/settings.json failed to parse (invalid JSON)",
                                        "zh": "Lint: .claude/settings.json 解析失敗 (JSON 格式錯誤)"},
    "scan.automation.subagents.have":  {"en": "{n} subagent(s)",                            "zh": "{n} 個 subagent"},
    "scan.automation.subagents.none":  {"en": "No subagents defined",                       "zh": "未定義 subagents"},
    "scan.automation.commands.have":   {"en": "{n} custom command(s)",                      "zh": "{n} 個自訂命令"},
    "scan.automation.commands.none":   {"en": "No custom commands",                         "zh": "未建立自訂命令"},
    "scan.automation.plugins.have":    {"en": "Plugins detected",                           "zh": "偵測到 plugin 使用"},
    "scan.automation.plugins.none":    {"en": "Plugins not in use",                         "zh": "未使用 plugins"},

    # ----- scan.context -----
    "scan.context.split.full":         {"en": "Both project- and user-space config present (good split)",
                                        "zh": "同時具備 project 與 user-space 設定 (分工良好)"},
    "scan.context.split.project_only": {"en": "Project-space only (consider adding ~/.claude for personal preferences)",
                                        "zh": "僅 project-space 設定 (建議補 ~/.claude 放個人通用偏好)"},
    "scan.context.split.user_only":    {"en": "User-space only",                            "zh": "僅 user-space 設定"},
    "scan.context.split.none":         {"en": "No split",                                   "zh": "無分工"},
    "scan.context.shared_personal.ok": {"en": "settings.local.json is gitignored",          "zh": "settings.local.json 已 gitignore"},
    "scan.context.shared_personal.no": {"en": "Shared vs personal config not separated",    "zh": "未區分共享與個人設定"},
    "scan.context.modular.have":       {"en": "{n} modular reference(s)",                   "zh": "{n} 處模組化引用"},
    "scan.context.modular.none":       {"en": "Not split into modules",                     "zh": "未模組化拆檔"},

    # ----- session_scanner activated-side details -----
    "session.claude_md.detail":        {"en": "{c}/{m} user messages contain corrections ({pct:.1f}%) — high rate ⇒ CLAUDE.md not guiding",
                                        "zh": "{c}/{m} user 訊息含糾正 ({pct:.1f}%) — 比例高 = CLAUDE.md 沒指導到"},
    "session.claude_md.empty":         {"en": "No user messages to evaluate",               "zh": "無 user 訊息可評估"},
    "session.skills.calls.have":       {"en": "{n} Skill invocation(s)",                    "zh": "{n} 次 Skill 觸發"},
    "session.skills.calls.none":       {"en": "Skill never triggered (description may be weak, or no skills installed)",
                                        "zh": "Skill 從未觸發 (description 可能寫不夠好,或無安裝 skills)"},
    "session.mcp.calls.have":          {"en": "{n} MCP server invocation(s)",               "zh": "{n} 次 MCP server 呼叫"},
    "session.mcp.calls.none":          {"en": "MCP server never invoked",                   "zh": "MCP server 從未被呼叫"},
    "session.automation.subagent_calls.have": {"en": "{n} subagent dispatch(es) via Agent tool",
                                                "zh": "{n} 次 subagent 派遣 (Agent tool)"},
    "session.automation.subagent_calls.none": {"en": "Subagent never dispatched (Agent tool unused)",
                                                "zh": "從未派遣 subagent (Agent tool 未使用)"},
    "session.context.efficiency.detail":{"en": "{r}/{t} reads were repeats ({pct:.1f}%)",   "zh": "{r}/{t} 為重複讀檔 ({pct:.1f}%)"},
    "session.context.efficiency.empty":{"en": "No Read activity",                           "zh": "無 Read 行為"},
    "session.context.mention.detail":  {"en": "{n} @-mention(s) in {m} user message(s) (rate={rate:.2f}/msg)",
                                        "zh": "{n} 處 @ 引用 / {m} user 訊息 (rate={rate:.2f}/msg)"},
    "session.context.mention.empty":   {"en": "No user messages to evaluate",               "zh": "無 user 訊息可評估"},

    # ----- usage_score.py (OTel optional path) -----
    "usage.skills.trigger_count.detail":{"en": "{total} trigger(s) / {sessions} session(s) (activation_rate={rate:.2f})",
                                         "zh": "{total} 次觸發 / {sessions} session (activation_rate={rate:.2f})"},
    "usage.skills.proactive.detail":    {"en": "{p}/{t} were model-initiated ({pct:.0f}%) — reflects description triggerability",
                                         "zh": "{p}/{t} 為模型主動觸發 ({pct:.0f}%) — 反映 description 觸發力"},
    "usage.skills.at_least_one.detail": {"en": "{n} skill(s) triggered",                   "zh": "{n} 個 skill 被觸發過"},
    "usage.mcp.health.detail":          {"en": "connected={c}, failed={f} (health={pct:.0f}%)",
                                         "zh": "connected={c}, failed={f} (health={pct:.0f}%)"},
    "usage.mcp.used_ratio.detail":      {"en": "{invoked}/{configured} server(s) invoked",
                                         "zh": "{invoked}/{configured} server 曾被呼叫"},
    "usage.mcp.used_ratio.suffix_scan": {"en": " (configured count from scan.json)",       "zh": " (configured 由 scan.json 提供)"},
    "usage.automation.hook_rate.detail":{"en": "{e}/{r} hooks executed ({pct:.0f}%)",      "zh": "{e}/{r} 已執行的 hook ({pct:.0f}%)"},
    "usage.automation.hook_rate.empty": {"en": "No hook registration recorded",            "zh": "尚無 hook 註冊紀錄"},
    "usage.automation.plugin_ratio.detail":{"en": "{loaded}/{installed} plugin(s) loaded ({pct:.0f}%)",
                                            "zh": "{loaded}/{installed} plugin 載入 ({pct:.0f}%)"},
    "usage.automation.subagent.have":   {"en": "{n} distinct subagent(s) dispatched",      "zh": "{n} 種 subagent 被派遣"},
    "usage.automation.subagent.none":   {"en": "No subagent used",                         "zh": "未使用任何 subagent"},
    "usage.context.mention_rate.detail":{"en": "{count} @file mention(s) / {sessions} session(s) (rate={rate:.2f})",
                                         "zh": "{count} 次 @file 引用 / {sessions} session (rate={rate:.2f})"},
    "usage.context.mention_success.detail":{"en": "{ok}/{total} resolved successfully",   "zh": "{ok}/{total} 解析成功"},
    "usage.context.mention_success.empty":{"en": "No @ references recorded",              "zh": "尚無 @ 引用紀錄"},
    "usage.claude_md.accept_rate.detail":{"en": "{a}/{t} tool proposals accepted (reject_ratio={pct:.1f}%)",
                                          "zh": "{a}/{t} 工具提議被接受 (reject_ratio={pct:.1f}%)"},
    "usage.claude_md.accept_rate.empty":{"en": "No tool_decision events",                 "zh": "尚無 tool_decision 事件"},
}


# ---------------------------------------------------------------------------
# Blind spots — explanatory caveats appended to a target.
# ---------------------------------------------------------------------------

BLIND_SPOTS: dict[str, dict[str, str]] = {
    "scan.blind.config_only": {
        "en": "scan only measures what's configured on disk. Pair with "
              "`agent-radar session` to see what actually fires inside "
              "Claude Code — the gap is your improvement headroom.",
        "zh": "scan 只看磁碟上的配置。搭配 `agent-radar session` 量「實際運用」, "
              "兩者落差就是改善空間。",
    },
    "session.blind.local_only": {
        "en": "session reads local JSONL only; sessions on the cloud or "
              "other machines are invisible. For cross-machine teams, pair "
              "with a centralized OpenTelemetry collector.",
        "zh": "session 只讀本機 JSONL,雲端 / 其他機器的 session 看不到。"
              "團隊跨機器使用建議搭配 OpenTelemetry 中央化收集。",
    },
    "session.blind.pattern_only": {
        "en": "Correction rate matches literal patterns only; semantic-level "
              "corrections (e.g. lengthy explanations of why something is wrong) "
              "are not detected.",
        "zh": "糾正率僅匹配字面 pattern,語意級糾正 (例如冗長解釋為什麼錯) 偵測不到。",
    },
}


# ---------------------------------------------------------------------------
# Gap hints — actionable one-liners for the merged Top Gaps section.
# ---------------------------------------------------------------------------

GAP_HINTS: dict[str, dict[str, str]] = {
    "gap.skills.proactive_low": {
        "en": "`{target}`: Skills configured but rarely triggered. proactive ratio "
              "only {pct}% — rewrite SKILL.md descriptions so the model can match "
              "trigger conditions.",
        "zh": "`{target}`：Skills 配置完整但實際觸發少。proactive 比例僅 {pct}%，"
              "重寫 description 讓模型能命中觸發條件。",
    },
    "gap.skills.generic": {
        "en": "`{target}`: Skills configured but rarely triggered. Consider "
              "rewriting SKILL.md descriptions with explicit trigger scenarios.",
        "zh": "`{target}`：Skills 配置完整但實際觸發少。"
              "考慮重寫 SKILL.md 的 description，加入明確觸發場景。",
    },
    "gap.mcp": {
        "en": "`{target}`: You configured MCP servers but the invocation ratio is "
              "low. Audit which servers are never used and prune or reconsider.",
        "zh": "`{target}`：你設定了 MCP server，但實際被呼叫的比例偏低。"
              "檢查哪些 server 從未被使用，刪除或重新評估。",
    },
    "gap.automation": {
        "en": "`{target}`: Automation (hooks / plugins / subagents) is configured "
              "but under-used. Verify hooks actually fire and subagents are dispatched.",
        "zh": "`{target}`：自動化 (hooks/plugins/subagents) 配置存在但運用不足。"
              "確認 hooks 是否真的觸發、subagents 是否被派遣。",
    },
    "gap.context_hygiene": {
        "en": "`{target}`: CLAUDE.md / settings are well-structured, but sessions "
              "rarely use @ references. Build a `@path` habit on hot files to keep "
              "context focused.",
        "zh": "`{target}`：CLAUDE.md / settings 結構良好，但 session 中"
              "幾乎不用 @ 引用。在常用檔上養成 `@path` 習慣以聚焦 context。",
    },
    "gap.claude_md": {
        "en": "`{target}`: CLAUDE.md exists but the session correction rate is high "
              "— users keep correcting Claude on things CLAUDE.md should already "
              "cover. Pick the top 3 correction patterns and codify them.",
        "zh": "`{target}`：CLAUDE.md 寫了，但 session 糾正率高 — 使用者一直在糾正"
              "本來該由 CLAUDE.md 處理的事。挑出前 3 個常糾正情境寫成規則。",
    },
    "gap.generic": {
        "en": "`{target}` has a large config-vs-usage gap on `{dim}`. Investigate further.",
        "zh": "`{target}` 在 {dim} 維度配置 vs 運用落差大，請進一步審視。",
    },
    # --- Over-activated direction (activated > configured): wins / under-documented strengths ---
    "gap.over.automation": {
        "en": "`{target}`: subagent dispatches outpace the configured automation surface. "
              "You're using subagents heavily — consider documenting *why* they get "
              "dispatched (in CLAUDE.md or subagent descriptions) so the pattern survives "
              "future config edits.",
        "zh": "`{target}`：subagent 派遣次數超過配置面所反映的程度。"
              "你用 subagent 用得很重 — 建議把「為什麼會派遣」寫進 CLAUDE.md 或 "
              "subagent description,讓這個 workflow 不會在未來改設定時意外丟失。",
    },
    "gap.over.claude_md": {
        "en": "`{target}`: correction rate is very low even though CLAUDE.md isn't "
              "maximally configured. Claude is being guided well by something — either "
              "your prompts are unusually clear, or CLAUDE.md is more effective than its "
              "configured-coverage score suggests. No action needed.",
        "zh": "`{target}`：CLAUDE.md 配置不算滿分,但 user 糾正率極低。"
              "Claude 在實際使用中被指導得很好 — 你 prompt 寫得好,或 CLAUDE.md 比"
              "「配置覆蓋率」這個分數所反映的還有效。沒有需要立即動作的事。",
    },
    "gap.over.generic": {
        "en": "`{target}`: `{dim}` is activated more than its configured surface suggests "
              "— a positive signal. Document what's working so the pattern is preserved.",
        "zh": "`{target}`：`{dim}` 的實際運用超過配置面所反映的程度,正向訊號。"
              "建議把運作良好的東西寫下來,避免未來重構時遺失。",
    },
}


# ---------------------------------------------------------------------------
# Dimension labels (five axes, used by both scanner and session_scanner).
# ---------------------------------------------------------------------------

DIMENSIONS: dict[str, dict[str, str]] = {
    "claude_md":       {"en": "CLAUDE.md",            "zh": "CLAUDE.md"},
    "skills":          {"en": "Skills",               "zh": "Skills"},
    "mcp":             {"en": "MCP",                  "zh": "MCP"},
    "automation":      {"en": "Automation",           "zh": "自動化"},
    "context_hygiene": {"en": "Context Hygiene",      "zh": "上下文管理"},
}

# Kept for backwards-compat with usage_score.py (OTel path); it overlays the
# same five axes but with ``.usage`` suffix in some emit paths.
USAGE_DIMENSIONS: dict[str, dict[str, str]] = {
    "claude_md":       {"en": "CLAUDE.md",            "zh": "CLAUDE.md"},
    "skills":          {"en": "Skills",               "zh": "Skills"},
    "mcp":             {"en": "MCP",                  "zh": "MCP"},
    "automation":      {"en": "Automation",           "zh": "自動化"},
    "context_hygiene": {"en": "Context Hygiene",      "zh": "上下文管理"},
    # OTel-specific overrides (legacy)
    "claude_md.usage":       {"en": "CLAUDE.md effectiveness (indirect)", "zh": "CLAUDE.md 生效度 (間接)"},
    "skills.usage":          {"en": "Skills usage",                       "zh": "Skills 運用"},
    "mcp.usage":             {"en": "MCP usage",                          "zh": "MCP 運用"},
    "automation.usage":      {"en": "Automation usage",                   "zh": "自動化運用"},
    "context_hygiene.usage": {"en": "Context references (actual)",        "zh": "上下文引用"},
}


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def _pick(table: dict, key: str, lang: str) -> str | None:
    entry = table.get(key)
    if not entry:
        return None
    return entry.get(lang) or entry.get("en")


def t_label(key: str, lang: str) -> str:
    """Translate a finding label key. Falls back to the key itself."""
    return _pick(FINDING_LABELS, key, lang) or key


def t_detail(key: str | None, args: dict | None, lang: str) -> str:
    """Translate a finding detail key + args. Empty key → ''.

    Special arg: ``_suffixes`` (list of ``[suffix_key, suffix_args]``) is
    rendered and appended after the base template. Used when a finding wants
    to optionally extend its detail (e.g. lint violations) without baking the
    conditionality into the template language.
    """
    if not key:
        return ""
    template = _pick(FINDING_DETAILS, key, lang)
    if template is None:
        return f"[{key}] {args or ''}"
    args = dict(args or {})
    suffixes = args.pop("_suffixes", []) or []
    try:
        base = template.format(**args)
    except (KeyError, IndexError) as exc:
        return f"[{key}] missing arg {exc}"
    for sk, sa in suffixes:
        base += t_detail(sk, sa, lang)
    return base


def t_blind(key: str, args: dict | None, lang: str) -> str:
    template = _pick(BLIND_SPOTS, key, lang) or f"[{key}]"
    try:
        return template.format(**(args or {})) if args else template
    except (KeyError, IndexError):
        return template


def t_hint(key: str, args: dict | None, lang: str) -> str:
    template = _pick(GAP_HINTS, key, lang)
    if template is None:
        return f"[{key}]"
    try:
        return template.format(**(args or {}))
    except (KeyError, IndexError) as exc:
        return f"[{key}] missing arg {exc}"


def t_dimension(dim_key: str, lang: str) -> str:
    """Translate a dimension key. Tries DIMENSIONS first, then USAGE_DIMENSIONS."""
    return (_pick(DIMENSIONS, dim_key, lang)
            or _pick(USAGE_DIMENSIONS, dim_key, lang)
            or dim_key)


def dimensions_for(keys: list[str], lang: str) -> dict[str, str]:
    """Return {key: localized_label} for a sequence of dimension keys."""
    return {k: t_dimension(k, lang) for k in keys}
