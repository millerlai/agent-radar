# agent-radar · AI Agent 能力邊界診斷工具

偵測「個人 / 團隊使用 Claude Code 生態的能力邊界」——透過掃描檔案系統指紋,
把一個人對 CLAUDE.md、skills、MCP、hooks、subagents 等的掌握程度量化成
六大維度的成熟度分數,並輸出 HTML 雷達圖報告。

**雙層量測**:

- `agent-radar scan` 量「配置完整度」(靜態指紋,六大配置維度)
- `agent-radar session` 讀本機 `~/.claude/projects/*.jsonl`,量「實際運用度」
  (session 內真正觸發的工具 / Skill / MCP / 使用者糾正率)

兩者落差即是最具體的改善清單。本專案本身也是一個可安裝的 Claude Code skill
(見 `SKILL.md`),可放到 `~/.claude/skills/agent-radar/` 後直接用。

## 核心理念

一個人對 Claude Code 的掌握程度,會直接刻在他的檔案系統與 session 紀錄裡。
本工具讀這些指紋,而不是去監控對話內容。

- **配置完整度** (靜態) 反映你「寫了多少」CLAUDE.md / skills / MCP。
- **實際運用度** (動態) 反映這些設定在 session 中「真的有沒有被觸發」。

很多人寫了完整 CLAUDE.md、裝了 5 個 MCP,但實際 session 中根本沒被用到——
這個落差,本工具會用兩條雷達線疊起來直接視覺化。

## 六大配置維度 (agent-radar scan)

| 維度 | 偵測什麼 |
|---|---|
| CLAUDE.md 成熟度 | 有無、user/project 層級、結構化分區、指令式語氣、精簡度、@import 拆檔、**Lint 大小** |
| Skills 運用 | skills 有無、SKILL.md 的 description 觸發品質、progressive disclosure、**Lint frontmatter & token 衛生** |
| MCP 整合 | MCP server 數量與類型廣度 (data/saas/cloud/search/files) |
| 自動化 | hooks、subagents、自訂 slash commands、plugins |
| 情境衛生 | user/project 設定分工、共享 vs 個人設定區分 (gitignore)、模組化引用 |
| 迭代與維護 | 透過 git history 看設定是否隨踩坑反覆調整 |

**Lint 訊號**借自 [`felixgeelhaar/cclint`](https://github.com/felixgeelhaar/cclint)
與 agentskills.io 的 Skill Linter 規則 (frontmatter 必要欄位、行數上限、
ASCII art / 裝飾性內容偵測、CLAUDE.md 過大警告等),用純 Python 重新實作,
不依賴外部工具。

總分對應 L0(未使用) → L4(精煉) 五個層級。

## 六大運用維度 (agent-radar session)

| 維度 | 量測什麼 |
|---|---|
| tool_diversity | session 內呼叫過幾種不同工具 |
| skill_triggered | `Skill` tool 實際被呼叫次數 (反映 description 觸發力) |
| mcp_triggered | `mcp__*` tool 實際呼叫次數 (反映 MCP 是否真的被用) |
| low_correction | user 訊息中糾正性語句的比例 (反向計分,低=好) |
| context_efficiency | 同一 session 重複讀同檔案的比例 (反向計分) |
| session_volume | session 數量與訊息量 (基準曝光度) |

## 安裝

**前置需求**:Python 3.8+ (僅用標準庫,零外部相依)。

### 方式 A · 從 PyPI 安裝 (推薦)

PyPI 套件名是 **`claude-agent-radar`** (PyPI 拒絕了較短的
`agent-radar`,因為跟一個無關的既有套件名稱衝突)。CLI 指令名與
Python module 名仍為 `agent-radar` 與 `agent_radar`。

底下兩種推薦安裝法會自動把 `agent-radar.exe` 放上 `PATH`——
不需要手動改環境變數。

```bash
# 推薦 · pipx (各 OS 都能用,免設定)
pipx install claude-agent-radar

# 推薦 · uv tool (你已經在用 uv 的話)
uv tool install claude-agent-radar

# 在已啟動的 venv 裡裝
python -m venv .venv
.venv\Scripts\activate           # Windows
source .venv/bin/activate        # macOS / Linux
pip install claude-agent-radar

# 開發用 (editable install)
git clone https://github.com/millerlai/agent-radar
cd agent-radar
pip install -e .
```

裝完後驗證:

```bash
agent-radar --version   # 例如印出 `agent-radar 0.1.3`
agent-radar --help
```

如果 `--version` 比 [PyPI 最新版](https://pypi.org/project/claude-agent-radar/)
舊,跑 `pipx upgrade claude-agent-radar` 或 `uv tool upgrade claude-agent-radar`
升級。

如果 `pipx` / `uv tool install` 成功但 `agent-radar` 還是
`command not found`,代表 shell 還沒讀到 tool-bin 目錄 ——
跑 `pipx ensurepath` 或 `uv tool update-shell`,再重開 shell 即可。

> ⚠️ **Windows 上不要用 `pip install --user claude-agent-radar`。**
> 執行檔會被裝到 `%APPDATA%\Python\Python3XX\Scripts\`,這個目錄
> 預設**不在 PATH 上**,裝完馬上會 `command not found`。請改用
> `pipx`。

如果 CLI 真的因為某些原因不在 PATH 上,`python -m agent_radar` 是
完全等價的替代寫法 (參數一致):

```bash
python -m agent_radar --help
python -m agent_radar scan ...     # 參數跟 `agent-radar scan ...` 一模一樣
```

### 方式 B · 安裝為 Claude Code skill (推薦給日常使用)

整個 repo 本身就是一個 Claude Code skill (根目錄含 `SKILL.md`),
複製到 user-space skills 目錄即可:

```bash
# macOS / Linux / Cygwin
cp -r /path/to/agent-radar ~/.claude/skills/agent-radar

# Windows PowerShell
Copy-Item -Recurse C:\path\to\agent-radar $env:USERPROFILE\.claude\skills\agent-radar
```

之後在任何 Claude Code session 中,只要說以下任一句,Claude 會自動載入此 skill
並引導你跑掃描:

- 「audit my Claude Code maturity」
- 「scan this repo's Claude Code setup」
- 「找出我設定的盲區」
- 「benchmark our team's Claude Code adoption」

skill 會呼叫 `agent-radar` CLI,所以請先把套件裝起來
(`pipx install claude-agent-radar` 最簡便),或在 skill 目錄裡改用
`python -m agent_radar ...`。

## 執行

### 30 秒快速開始

掃當前 repo + 你的 user-space,生成完整含實際運用度的 HTML 報告。
請在「想被掃描的 repo」目錄裡執行:

```bash
agent-radar scan --include-home . -o scan.json
agent-radar session -o session.json
agent-radar report scan.json --session session.json -o report.html

# 開啟報告
open report.html        # macOS
xdg-open report.html    # Linux
start report.html       # Windows (PowerShell / cmd)
```

如果 `agent-radar` 找不到指令,把每一行的 `agent-radar` 換成
`python -m agent_radar` 即可 (參數完全相同)。詳見上方安裝段。

### 子指令一覽

| 子指令 | 用途 |
|---|---|
| `agent-radar scan` | 掃檔案系統指紋 (六大配置維度) |
| `agent-radar session` | 掃本機 `~/.claude/projects/*.jsonl` 量實際運用 |
| `agent-radar report` | 產 HTML 雷達報告 |
| `agent-radar usage` | 把 OTel 事件轉成 `usage.json` |
| `agent-radar merge` | 把 `scan.json` + `usage.json` 合成 `merged.json` |

每個子指令都有自己的 `--help`;另一種等價寫法是 `python -m agent_radar <sub> ...`。

### 三種掃描情境

**情境 1 · 個人單一 repo (最簡)**

```bash
agent-radar scan /path/to/repo -o scan.json
agent-radar report scan.json -o report.html
```

**情境 2 · 個人完整體檢 (含 user-space)**

把 `~/.claude/` 一併納入,看 user-level 與 project-level 設定的分工:

```bash
agent-radar scan --include-home /path/to/repo -o scan.json
agent-radar report scan.json -o report.html
```

**情境 3 · 團隊 benchmark (多 repo)**

掃多個 repo,報告會自動加排行榜:

```bash
agent-radar scan /repos/a /repos/b /repos/c -o scan.json
agent-radar report scan.json -o report.html
```

### 加上實際運用度量測 (完整雙層分析)

`agent-radar session` 讀本機 `~/.claude/projects/*.jsonl`,輸出 session 中
真正觸發的工具 / Skill / MCP / 使用者糾正率。配 `agent-radar report --session`
會在 HTML 多一張運用度雷達:

```bash
# 1. 掃所有 project (預設讀 ~/.claude/projects/)
agent-radar session -o session.json

# 或:只統計某幾個 repo
agent-radar session /path/to/repo -o session.json

# 2. Cygwin / 跨 OS 環境,手動指定 projects 目錄
agent-radar session --projects-dir /c/Users/<you>/.claude/projects -o session.json

# 3. 生成雙層雷達報告
agent-radar report scan.json --session session.json -o report.html
```

### 輸出檔案說明

| 檔案 | 來源 | 內容 |
|---|---|---|
| `scan.json` | `agent-radar scan` | 配置完整度:六大配置維度分數 + 每個訊號的明細 |
| `session.json` | `agent-radar session` | 實際運用度:每個 project 的 tool 呼叫、Skill / MCP 觸發、糾正率 |
| `report.html` | `agent-radar report` | 單檔可離線開啟的 HTML 報告,含雷達圖 + 排行 + 明細手風琴 |

### 完整 CLI 旗標

```bash
agent-radar --help                  # 列出所有子指令 + 版本
agent-radar scan --help             # paths, --include-home, -o
agent-radar session --help          # paths, --projects-dir, -o
agent-radar report --help           # input, --session, --merged, --lang, -o
agent-radar usage --help            # --otel-log, --scan, --target, --account, ...
agent-radar merge --help            # scan.json, usage.json, -o
```

## 限制

- 只對「有檔案系統存取權」的對象有效 (自己 / 團隊 repo)。
- 對只給程式碼或對話的陌生對象,無法可靠偵測,亦涉及監控他人的灰色地帶,不建議。
- session_scanner 只讀本機 JSONL,跨機器需另接 OpenTelemetry。
- 糾正率僅匹配字面 pattern,語意級糾正偵測不到。
- 評分權重是可調的啟發式,建議依團隊實況校準後再做跨人比較。

## 授權

Apache License 2.0 — 詳見 [LICENSE](LICENSE)。

Copyright 2026 Miller Lai。
