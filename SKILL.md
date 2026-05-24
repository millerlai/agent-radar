---
name: agent-radar
description: Diagnose AI Agent capability boundaries by scanning Claude Code filesystem fingerprints. Use when the user asks to "audit my Claude Code usage / maturity", "benchmark our team's Claude Code adoption", "scan this repo's CLAUDE.md / skills / MCP setup", "diagnose Claude Code blind spots", or "find what's missing in my agent config". Quantifies six dimensions (CLAUDE.md, Skills, MCP, Automation, Context hygiene, Iteration) into 0–100 maturity scores, plus an optional usage layer that reads ~/.claude/projects/*.jsonl to measure what actually fires inside sessions.
---

# agent-radar

掃描 Claude Code 生態的檔案系統指紋,把使用者 / 團隊對 CLAUDE.md、skills、MCP、
hooks、subagents 等的掌握度量化成六大維度的成熟度分數 (0–100),並輸出 HTML 雷達圖。

## 何時觸發

當使用者要求下列任一事項:
- 評估自己或團隊使用 Claude Code 的成熟度
- 找出 CLAUDE.md / skills / MCP / hooks 設定的盲區
- 比較多個 repo 的 Claude Code 採用程度 (團隊 benchmark)
- 量測「實際運用度」(Claude Code 設定是否真的有在 session 中觸發)
- 借助 lint 規則檢查 SKILL.md / CLAUDE.md 是否合規

## 用法

安裝後 (`pipx install claude-agent-radar`、`uv tool install claude-agent-radar` 或 `pip install claude-agent-radar`)
即可使用 `agent-radar` CLI;不安裝套件時亦可從 repo 根目錄改用 `python -m agent_radar ...`。

```bash
# 1. 掃單一 repo
agent-radar scan /path/to/repo -o scan.json

# 個人 + 納入 user-space
agent-radar scan --include-home /path/to/repo -o scan.json

# 團隊 benchmark (多 repo)
agent-radar scan /repos/a /repos/b /repos/c -o scan.json

# 2. (可選) 加掃實際運用度 (讀本機 session JSONL)
agent-radar session -o session.json

# Cygwin / 跨 OS:手動指定 projects 目錄
agent-radar session --projects-dir /c/Users/<you>/.claude/projects -o session.json

# 3. 生成 HTML 報告 (含配置 + 運用雙雷達)
agent-radar report scan.json --session session.json -o report.html
```

僅需 Python 3 標準庫,零外部相依 (`pip install` 不會拉任何依賴)。

## 六大配置維度 (agent-radar scan)

| 維度 | 內容 |
|---|---|
| CLAUDE.md 成熟度 | 存在性、結構化、指令式語氣、精簡度、@import、**Lint 大小** |
| Skills 運用 | 存在性、description 觸發品質、progressive disclosure、**Lint frontmatter + token 衛生** |
| MCP 整合 | server 數量、類型廣度 |
| 自動化 | hooks、subagents、自訂 commands、plugins |
| 情境衛生 | user/project 分工、settings.local gitignore、模組化引用 |
| 迭代與維護 | git history 中設定檔被修改次數與多樣性 |

Lint 訊號借自 [felixgeelhaar/cclint] 與 [agentskills.io Skill Linter] 的規則,
純 Python 重新實作 (frontmatter 必要欄位、行數上限、ASCII art / 裝飾性內容偵測等),
不依賴外部工具。

## 六大運用維度 (agent-radar session)

| 維度 | 量測什麼 |
|---|---|
| tool_diversity | session 內呼叫過幾種不同工具 |
| skill_triggered | `Skill` tool 實際被呼叫的次數 (反映 description 觸發力) |
| mcp_triggered | `mcp__*` tool 實際呼叫次數 (反映 MCP 是否真的被用) |
| low_correction | user 訊息中糾正性語句的比例 (反向計分,低=好) |
| context_efficiency | 同一 session 重複讀同檔案的比例 (反向計分) |
| session_volume | session 數量與訊息量 (基準曝光度) |

**「配置完整度」與「實際運用度」的落差就是最具體的改善清單**。例如:
你寫了 CLAUDE.md 但糾正率仍高 → CLAUDE.md 沒有真的指導 Claude;
裝了 5 個 MCP server 但 `mcp_triggered=0` → MCP 從未被觸發,可能 description 不夠。

## 限制

- 只對「有檔案系統存取權」的對象有效。
- session_scanner 只看本機 JSONL,跨機器需另接 OpenTelemetry。
- 糾正率僅匹配字面 pattern (no/don't/不對/還原 等),語意級糾正偵測不到。
- 評分權重是啟發式,建議依團隊實況校準後再做跨人比較。

## 安裝

```bash
# 1. 一般 Python 套件方式 (推薦):pipx 或 uv tool 會自動處理 PATH
pipx install claude-agent-radar
# 或
uv tool install claude-agent-radar
# 或在 venv 裡
pip install claude-agent-radar

# 2. 同時 (或單獨) 安裝為 user-space skill — 整個 repo 目錄就是 skill
cp -r /path/to/agent-radar ~/.claude/skills/agent-radar
```

之後在任何 Claude Code session 中,只要說「audit my Claude Code maturity」之類的話,
Claude 就會載入這個 skill 並引導你跑掃描。skill 內已將命令改為 `agent-radar ...`,
請先確認套件已安裝過 (PyPI 套件名 `claude-agent-radar`,CLI 指令名 `agent-radar`)。
