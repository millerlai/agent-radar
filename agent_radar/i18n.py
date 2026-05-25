"""agent-radar :: agent_radar.i18n
================================
Localizable strings for findings, blind spots, gap hints, dimensions and levels.

Producers (``scanner``, ``session_scanner``, ``usage_score``, ``merge``) emit
language-neutral keys + arg dicts into JSON. The HTML renderer in
``report.py`` looks the strings up here at render time, driven by ``--lang``.

Adding a new finding:
  1. Add a key + en/zh template to ``FINDING_LABELS`` / ``FINDING_DETAILS``.
  2. Emit ``{"label_key": key, "detail_key": key, "detail_args": {...}}``
     from the producer.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Finding labels — short titles shown in the report's accordion summaries.
# Keyed by stable identifier; values are {lang: text}.
# ---------------------------------------------------------------------------

FINDING_LABELS: dict[str, dict[str, str]] = {
    # scanner.py
    "scan.claude_md.exists":       {"en": "CLAUDE.md exists",                "zh": "CLAUDE.md 存在"},
    "scan.claude_md.structure":    {"en": "Structured sections",             "zh": "結構化分區"},
    "scan.claude_md.imperative":   {"en": "Imperative tone",                 "zh": "指令式語氣"},
    "scan.claude_md.concise":      {"en": "Conciseness (not a prose dump)",  "zh": "精簡度 (非散文堆疊)"},
    "scan.claude_md.import":       {"en": "@import references",              "zh": "@import 引用"},
    "scan.claude_md.lint_size":    {"en": "Lint: reasonable size",           "zh": "Lint: 大小合理"},
    "scan.skills.exists":          {"en": "Skills present",                  "zh": "Skills 存在"},
    "scan.skills.description":     {"en": "Description quality",             "zh": "description 品質"},
    "scan.skills.progressive":     {"en": "Progressive disclosure",          "zh": "Progressive disclosure"},
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
    "scan.iteration.git":          {"en": "Config git iteration",            "zh": "設定檔 git 迭代"},
    "scan.iteration.diversity":    {"en": "Config diversity",                "zh": "設定檔多樣性"},

    # session_scanner.py
    "session.tool_diversity":      {"en": "Tool diversity",                  "zh": "Tool 多樣性"},
    "session.skill_calls":         {"en": "Skill tool invocations",          "zh": "Skill tool 呼叫"},
    "session.mcp_calls":           {"en": "MCP tool invocations",            "zh": "MCP tool 呼叫"},
    "session.subagent_calls":      {"en": "Subagent dispatches",             "zh": "Subagent 派遣"},
    "session.low_correction":      {"en": "Low correction rate",             "zh": "低糾正率"},
    "session.read_repeat":         {"en": "Read repetition rate (inverse)",  "zh": "Read 重複率 (反向)"},
    "session.session_volume":      {"en": "Session volume",                  "zh": "Session 量"},

    # usage_score.py
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
# Finding details — sentence-level templates with placeholders.
#
# Keys are usually <label_key>.<variant>, e.g. ``scan.automation.commands.have``
# and ``scan.automation.commands.none`` for the two branches.
# ---------------------------------------------------------------------------

FINDING_DETAILS: dict[str, dict[str, str]] = {
    # scan.claude_md
    "scan.claude_md.exists.found":     {"en": "Found {paths}",                              "zh": "找到 {paths}"},
    "scan.claude_md.exists.none":      {"en": "No CLAUDE.md found",                         "zh": "未發現 CLAUDE.md"},
    "scan.claude_md.placeholder":      {"en": "No CLAUDE.md to evaluate",                   "zh": "無 CLAUDE.md 可評估"},
    "scan.claude_md.structure.detail": {"en": "{headers} header(s), {hints} section hint(s) matched",
                                        "zh": "{headers} 個標題, 命中 {hints} 個分區關鍵字"},
    "scan.claude_md.imperative.detail":{"en": "~{hits} imperative / rule statements detected",
                                        "zh": "偵測到約 {hits} 處祈使/規範語句"},
    "scan.claude_md.concise.detail":   {"en": "~{words} words",                             "zh": "約 {words} 字"},
    "scan.claude_md.import.have":      {"en": "{n} @ reference(s)",                         "zh": "{n} 處 @ 引用"},
    "scan.claude_md.import.none":      {"en": "@import not used to split files",            "zh": "未使用 @import 拆檔"},
    "scan.claude_md.lint_size.ok":     {"en": "{chars} chars (within limit)",               "zh": "{chars} chars (合規)"},
    "scan.claude_md.lint_size.soft":   {"en": "{chars} chars (large — consider splitting or trimming)",
                                        "zh": "{chars} chars (偏大,建議拆檔或精簡)"},
    "scan.claude_md.lint_size.hard":   {"en": "{chars} chars (oversize — violates cclint guidance, wastes context)",
                                        "zh": "{chars} chars (過大,違反 cclint 建議,context 浪費)"},

    # scan.skills
    "scan.skills.exists.have":         {"en": "Found {n} SKILL.md file(s)",                 "zh": "找到 {n} 個 SKILL.md"},
    "scan.skills.exists.none":         {"en": "Skills not in use",                          "zh": "未使用 skills"},
    "scan.skills.placeholder":         {"en": "No skills to evaluate",                      "zh": "無 skills 可評估"},
    "scan.skills.description.detail":  {"en": "Average description quality (incl. trigger description)",
                                        "zh": "description 平均品質 (含觸發描述)"},
    "scan.skills.progressive.detail":  {"en": "Main file conciseness + sibling-file split",
                                        "zh": "主檔精簡 + 附屬檔拆分情況"},
    "scan.skills.lint.detail":         {"en": "frontmatter compliant {fm}/{n}",
                                        "zh": "frontmatter 合規 {fm}/{n}"},
    "scan.skills.lint.decor_suffix":   {"en": ", {n} ASCII-art / decorative banner violation(s)",
                                        "zh": ", {n} 處 ASCII art/裝飾性內容"},
    "scan.skills.lint.oversize_suffix":{"en": ", {n} oversize file(s)",                    "zh": ", 行數超標 {n}"},

    # scan.mcp
    "scan.mcp.server_count.have":      {"en": "{n} MCP server(s)",                          "zh": "{n} 個 MCP server"},
    "scan.mcp.server_count.none":      {"en": "No MCP server configured",                   "zh": "未設定任何 MCP server"},
    "scan.mcp.category_breadth.have":  {"en": "Categories covered: {cats}",                 "zh": "涵蓋類別: {cats}"},
    "scan.mcp.category_breadth.none":  {"en": "Could not classify categories",              "zh": "無法辨識類別"},

    # scan.automation
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

    # scan.context
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

    # scan.iteration
    "scan.iteration.non_git":          {"en": "Not a git repo — cannot evaluate iteration", "zh": "非 git repo，無法評估迭代"},
    "scan.iteration.non_git.short":    {"en": "Not a git repo",                             "zh": "非 git repo"},
    "scan.iteration.git.detail":       {"en": "Config-related commit counts: {parts}",     "zh": "設定相關 commit 次數: {parts}"},
    "scan.iteration.diversity.detail": {"en": "Iterated on {n} kind(s) of config file",    "zh": "曾迭代 {n} 類設定檔"},

    # ---- session_scanner.py
    "session.tool_diversity.detail":   {"en": "{n} distinct tool(s); top 5: {top}",        "zh": "{n} 種工具,前 5: {top}"},
    "session.skill_calls.have":        {"en": "{n} Skill invocation(s)",                   "zh": "{n} 次 Skill 觸發"},
    "session.skill_calls.none":        {"en": "Skill never triggered (description may be weak, or no skills installed)",
                                        "zh": "Skill 從未觸發 (description 可能寫不夠好,或無安裝 skills)"},
    "session.mcp_calls.have":          {"en": "{n} MCP server invocation(s)",              "zh": "{n} 次 MCP server 呼叫"},
    "session.mcp_calls.none":          {"en": "MCP server never invoked",                  "zh": "MCP server 從未被呼叫"},
    "session.subagent_calls.have":     {"en": "{n} subagent dispatch(es) via Agent tool",  "zh": "{n} 次 subagent 派遣 (Agent tool)"},
    "session.subagent_calls.none":     {"en": "Subagent never dispatched (Agent tool unused)",
                                        "zh": "從未派遣 subagent (Agent tool 未使用)"},
    "session.low_correction.detail":   {"en": "{c}/{m} user messages contain corrections ({pct:.1f}%)",
                                        "zh": "{c}/{m} user 訊息含糾正 ({pct:.1f}%)"},
    "session.low_correction.empty":    {"en": "No user messages to evaluate",              "zh": "無 user 訊息可評估"},
    "session.read_repeat.detail":      {"en": "{r}/{t} reads were repeats ({pct:.1f}%)",   "zh": "{r}/{t} 為重複讀檔 ({pct:.1f}%)"},
    "session.read_repeat.empty":       {"en": "No Read activity",                          "zh": "無 Read 行為"},
    "session.session_volume.detail":   {"en": "{s} session(s), {m} message(s)",            "zh": "{s} 個 session, {m} 則訊息"},

    # ---- usage_score.py
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
        "en": "This tool only measures configuration completeness; it cannot tell "
              "whether these settings are actually exercised in real sessions. "
              "Wire up OpenTelemetry to measure actual usage — the gap is your "
              "improvement headroom.",
        "zh": "本工具只偵測『配置完整度』，無法得知這些設定在實際 session 中"
              "是否真的被觸發。建議接 OpenTelemetry 量測『實際運用度』，"
              "兩者落差即為改善空間。",
    },
    "scan.blind.non_git": {
        "en": "This target is not a git repo, so the iteration dimension cannot "
              "be evaluated; a low score is expected.",
        "zh": "此目標非 git repo，迭代維度無法評估，分數偏低屬正常。",
    },
    "session.blind.local_only": {
        "en": "This tool reads local JSONL only; sessions on the cloud or other "
              "machines are invisible. For cross-machine teams, pair with a "
              "centralized OpenTelemetry collector.",
        "zh": "本工具讀取本機 JSONL,無法觀測雲端 / 其他機器的 session;"
              "若團隊跨機器使用,建議搭配 OpenTelemetry 中央化收集。",
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
        "en": "`{target}`: CLAUDE.md is thorough, but tool_decision shows proposals "
              "are often rejected. Review which suggestions get rejected and "
              "codify the rules in CLAUDE.md.",
        "zh": "`{target}`：CLAUDE.md 寫得齊全，但 tool_decision 顯示提議常被拒。"
              "回頭看哪些建議被拒，把規則明文寫進 CLAUDE.md。",
    },
    "gap.generic": {
        "en": "`{target}` has a large config-vs-usage gap on `{dim}`. Investigate further.",
        "zh": "`{target}` 在 {dim} 維度配置 vs 運用落差大，請進一步審視。",
    },
}


# ---------------------------------------------------------------------------
# Dimension labels (scan + usage). Producers carry only keys; report renders
# via this table.
# ---------------------------------------------------------------------------

DIMENSIONS: dict[str, dict[str, str]] = {
    "claude_md":       {"en": "CLAUDE.md Maturity",       "zh": "CLAUDE.md 成熟度"},
    "skills":          {"en": "Skills Usage",             "zh": "Skills 運用"},
    "mcp":             {"en": "MCP Integration",          "zh": "MCP 整合"},
    "automation":      {"en": "Automation",               "zh": "自動化"},
    "context_hygiene": {"en": "Context Hygiene",          "zh": "情境衛生"},
    "iteration":       {"en": "Iteration & Maintenance",  "zh": "迭代與維護"},
}


USAGE_DIMENSIONS: dict[str, dict[str, str]] = {
    # session_scanner.py axes
    "tool_diversity":     {"en": "Tool diversity",          "zh": "工具多樣性"},
    "skill_triggered":    {"en": "Skill triggers (actual)", "zh": "Skills 實際觸發"},
    "mcp_triggered":      {"en": "MCP calls (actual)",      "zh": "MCP 實際呼叫"},
    "subagent_triggered": {"en": "Subagent dispatches (actual)", "zh": "Subagent 實際派遣"},
    "low_correction":     {"en": "Low correction rate",     "zh": "低糾正率"},
    "context_efficiency": {"en": "Context efficiency",      "zh": "Context 效率"},
    "session_volume":     {"en": "Session volume",          "zh": "Session 量"},
    # usage_score.py axes — mirror DIMENSIONS keys
    # (resolved via DIMENSIONS first; here we only add usage-specific overrides)
    "claude_md.usage":       {"en": "CLAUDE.md effectiveness (indirect)", "zh": "CLAUDE.md 生效度 (間接)"},
    "skills.usage":          {"en": "Skills usage",                       "zh": "Skills 運用"},
    "mcp.usage":             {"en": "MCP usage",                          "zh": "MCP 運用"},
    "automation.usage":      {"en": "Automation usage",                   "zh": "自動化運用"},
    "context_hygiene.usage": {"en": "Context references (actual)",        "zh": "情境引用"},
}


# ---------------------------------------------------------------------------
# Maturity levels — labels carry both an L# prefix and a one-word descriptor.
# The report parses on the "·" separator.
# ---------------------------------------------------------------------------

LEVELS: list[tuple[int, dict[str, str]]] = [
    (0,  {"en": "L0 · Unaware",    "zh": "L0 · 未使用 (Unaware)"}),
    (20, {"en": "L1 · Reactive",   "zh": "L1 · 萌芽 (Reactive)"}),
    (40, {"en": "L2 · Structured", "zh": "L2 · 結構化 (Structured)"}),
    (60, {"en": "L3 · Advanced",   "zh": "L3 · 進階 (Advanced)"}),
    (80, {"en": "L4 · Mastery",    "zh": "L4 · 精煉 (Mastery)"}),
]


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

    Falls back to a best-effort rendering if the key is unknown so partial
    rollouts don't produce blank rows.
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


def levels_for(lang: str) -> list[tuple[int, str]]:
    return [(th, entry.get(lang, entry["en"])) for th, entry in LEVELS]


def dimensions_for(keys: list[str], lang: str) -> dict[str, str]:
    """Return {key: localized_label} for a sequence of dimension keys."""
    return {k: t_dimension(k, lang) for k in keys}
