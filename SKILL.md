---
name: agent-radar
description: Diagnose the Activation Gap in a Claude Code setup — what's configured on disk vs what actually fires inside sessions. Use when the user asks to "audit my Claude Code setup", "scan this repo's CLAUDE.md / skills / MCP / hooks", "find what's configured but unused", "measure my Claude Code activation rate", or "benchmark our team's Claude Code adoption". Produces five-axis (CLAUDE.md, Skills, MCP, Automation, Context hygiene) Configured + Activated scores plus an HTML dual-radar report.
---

# agent-radar

掃描 Claude Code 生態的檔案系統指紋 (CLAUDE.md、skills、MCP、hooks、subagents 等),
同時讀本機 session JSONL,把「**Configured (有設定)**」與「**Activated (真的有跑)**」
分別量化成五大軸的 0–100 分,兩者的落差就是 Activation Gap — 改善空間最具體的地方。

agent-radar **不**判斷 CLAUDE.md / SKILL.md 的「品質」(那種啟發式評分只是假裝在量品質);
詮釋性的品質判斷留給配套的 `/agent-radar-coach` skill。

## 何時觸發

當使用者要求下列任一事項:
- 盤點自己或團隊 Claude Code 設定的活用度 (Activation Gap)
- 找出 CLAUDE.md / skills / MCP / hooks 設定的盲區
- 比較多個 repo 的 Claude Code 採用程度 (團隊 benchmark)
- 量測「實際運用度」(設定是否真的有在 session 中觸發)
- 借助 lint 規則檢查 SKILL.md / CLAUDE.md frontmatter 是否合規

## 用法

安裝後 (`pipx install claude-agent-radar`、`uv tool install claude-agent-radar` 或 `pip install claude-agent-radar`)
即可使用 `agent-radar` CLI;不安裝套件時亦可從 repo 根目錄改用 `python -m agent_radar ...`。

```bash
# 1. 掃單一 repo (Configured 側)
agent-radar scan /path/to/repo -o scan.json

# 個人 + 納入 user-space
agent-radar scan --include-home /path/to/repo -o scan.json

# 團隊 benchmark (多 repo)
agent-radar scan /repos/a /repos/b /repos/c -o scan.json

# 2. 掃本機 session JSONL (Activated 側)
agent-radar session -o session.json

# Cygwin / 跨 OS:手動指定 projects 目錄
agent-radar session --projects-dir /c/Users/<you>/.claude/projects -o session.json

# 3. 生成 HTML 報告 (含 Configured + Activated 雙雷達 + Top Gaps)
agent-radar report scan.json --session session.json -o report.html
```

僅需 Python 3 標準庫,零外部相依 (`pip install` 不會拉任何依賴)。

## 五大軸

每一軸都同時產出 **Configured (`scan`)** 與 **Activated (`session`)** 兩個 0–100 分。

| 軸 | Configured 量什麼 | Activated 量什麼 |
|---|---|---|
| `claude_md` | 存在性、大小、`@import` 引用、迭代證據 (git 修改次數 + 內文有沒有「lessons learned / 不要再犯 / 帶日期的規則」等型樣) | `(1 − correction_rate) × 100` — 糾正率低 = CLAUDE.md 真的有在指導 |
| `skills` | SKILL.md 數量 + lint 衛生 (frontmatter 必要欄位、行數上限、ASCII art / 裝飾性內容偵測) | `Skill` tool 實際被呼叫次數 × 10 |
| `mcp` | 已設定的 server 數量 + 類型廣度 (data / saas / cloud / search / files) | `mcp__*` tool 實際呼叫次數 × 8 |
| `automation` | hooks、subagents、custom commands、plugins (事實計數) | `Agent` tool 派發次數 × 10 (hooks/commands 在 JSONL 看不到) |
| `context_hygiene` | user/project 分工、`settings.local.json` 是否 gitignore、`@import` 模組化 | `(1 − 重讀同檔比例) × 50` + `@-mention 比例 × 50` 的混合 |

Lint 訊號借自 [felixgeelhaar/cclint] 與 agentskills.io Skill Linter 的規則,
純 Python 重新實作,不依賴外部工具。

## 限制

- 只對「有檔案系統存取權」的對象有效。
- session_scanner 只看本機 JSONL,跨機器需另接 OpenTelemetry。
- 糾正率僅匹配字面 pattern (no/don't/不對/還原 等),語意級糾正偵測不到。
- Configured / Activated 兩側「單位不同」(完整度 vs 觸發頻率),Gap 在「Configured > Activated」方向最具語意,反向 (Activated > Configured) 也會雙向標示,但意義不同 — 報告會分開呈現。

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

之後在任何 Claude Code session 中,只要說「audit my Claude Code activation gap」之類的話,
Claude 就會載入這個 skill 並引導你跑掃描。skill 內已將命令改為 `agent-radar ...`,
請先確認套件已安裝過 (PyPI 套件名 `claude-agent-radar`,CLI 指令名 `agent-radar`)。
