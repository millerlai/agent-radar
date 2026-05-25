# agent-radar · Claude Code Activation Gap 診斷工具

**這個工具獨家做到的一件事**:它同時看得到你**配置了什麼**(磁碟上的指紋)
和**實際在 session 裡發生了什麼**(JSONL 紀錄)—— 兩者落差就是改善空間。

- `agent-radar scan` 讀檔案系統指紋 → **配置側**(五大軸)
- `agent-radar session` 讀本機 `~/.claude/projects/*.jsonl` → **啟動側**(同五軸)
- `agent-radar merge` + `agent-radar report` → HTML 視覺化 activation gap

附帶的 `/agent-radar-coach` skill(用 `agent-radar install-skill` 安裝)會
拿著這個落差,一次處理一個 gap,**用實際數據當證據、改之前先問你**。

## 範例報告

repo 內已附上一份對真實 repo 跑出來的範例報告 ——
GitHub 不會直接渲染 HTML,透過 CDN 預覽:

- 🇹🇼 **繁體中文** · [report.zh.html](https://raw.githack.com/millerlai/agent-radar/main/report.zh.html)
- 🇬🇧 **English** · [report.en.html](https://raw.githack.com/millerlai/agent-radar/main/report.en.html)

裡面包含雙軌雷達、雙向 Top Gaps(每一條都可以點開看背後的 configured +
activated findings)、以及 per-target 細節。

## 核心理念

絕大多數「Claude Code 健檢」工具止步於「你寫了 CLAUDE.md 嗎?」這只是指紋偵測—
必要但不有趣。**真正有趣的是:很多人寫了完整 CLAUDE.md、裝了 5 個 MCP,
但實際 session 中根本沒被用到。**這個落差,本工具會用兩條雷達線疊起來直接視覺化。

agent-radar **不會**去評你 CLAUDE.md 的「品質」——「imperative 詞出現幾次」
這類 heuristic 根本量不到品質,只是假裝在量。品質判斷是解釋層的事,
交給 coach skill,讓 Claude 真的讀內容做語意級判斷。

## 五大軸

每個軸都產出兩個 0-100 分數:**Configured**(配置側,scan)與
**Activated**(啟動側,session)。落差就是改善空間。

| 軸 | Configured (`scan`) | Activated (`session`) |
|---|---|---|
| `claude_md` | 存在、size、`@import` 引用、**迭代證據**(git commit 次數 + 內容中的「lessons learned / 不要再 / 日期戳記」等迭代訊號) | `(1 - 糾正率) × 100` —— 糾正率低 = CLAUDE.md 真的在指導 |
| `skills` | SKILL.md 數量 + lint 衛生(frontmatter 合規、無 ASCII-art 裝飾、行數合規) | `Skill` tool 觸發次數 × 10 |
| `mcp` | 配置的 server 數量 + 類別廣度(data / saas / cloud / search / files) | `mcp__*` tool 呼叫次數 × 8 |
| `automation` | Hooks、subagents、自訂 commands、plugins(事實計數) | `Agent` tool 派遣次數 × 10(hooks/commands 在 JSONL 看不到) |
| `context_hygiene` | User/project 分工 + `settings.local.json` gitignore + `@import` 模組化 | 混合: `(1 - 重複讀率) × 50` + `@ 引用率 × 50` |

**Lint 訊號**借自 [`felixgeelhaar/cclint`](https://github.com/felixgeelhaar/cclint)
與 agentskills.io 的 Skill Linter 規則(frontmatter 必要欄位、行數上限、
ASCII art 偵測、CLAUDE.md 過大警告等),用純 Python 重新實作,
不依賴外部工具。

> **從 0.1.x 升級?** `iteration` 維度沒了 —— 折進 `claude_md` 變成 fact-based
> 子訊號(git commit 次數 + 內容 regex)。「成熟度總分」也沒了;同一個 0-100
> 數字還在,但語意改為「Configured Coverage」不是「Maturity」。
> Heuristic 子檢查(imperative 詞統計、headers-graded、word-count concise bucket、
> skills description 品質分)都拿掉 —— 這些是假裝在量品質,CLI 本來就量不到。

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

### 安裝 coach skill (選用,但建議裝)

```bash
agent-radar install-skill
```

把內建的 Claude Code skill 複製到 `~/.claude/skills/agent-radar-coach/`。
在任何 Claude Code session 內叫 `/agent-radar-coach`,
它會根據你的 scan / session 結果,一次處理一個 gap
(用實際數據當證據、改之前先問你)。覆蓋舊版加 `--force`,
裝到別處用 `--dest <dir>`。

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

### 進階 · OpenTelemetry 路徑 (跨機器、hooks / plugins)

`agent-radar usage` 是 **OpenTelemetry 版**的 activation 量測,跟
`agent-radar session` 互為替代。它讀 Claude Code 透過 OTel 吐出的事件
串流,產出跟 `merge` 預期格式相同的 `usage.json`。

**大部分使用者不需要**走這條 —— `agent-radar session` 已經涵蓋從 JSONL
能拿到的 ~90% 有用訊號,且不需任何前置設定。會想用 OTel 路徑只有以下情況:

- 想看 **hook 觸發遙測**(JSONL 看不到 hook 是否真的觸發)
- 想看 **plugin 載入事件**
- 想看 **MCP 連線健康度**(connected / failed)
- 想做**跨機器聚合**(透過中央 OTel collector)
- 共用機器需要**按帳號過濾**事件

| | `agent-radar session` | `agent-radar usage` |
|---|---|---|
| 前置設定 | 不用,裝完即跑 | 要先啟用 Claude Code telemetry |
| 資料來源 | `~/.claude/projects/*.jsonl` | OTel events log (console exporter) |
| hook / plugin 訊號 | ✗ | ✓ |
| 跨機器 | 僅本機 | 是(透過中央 collector) |

#### Step 1 · 開啟 Claude Code OTel 遙測

啟動 `claude` **之前**設好以下環境變數。最簡單的設定是用 **console
exporter** —— Claude Code 會把 JSON 事件串流寫到 `stderr`,你接到檔案
即可。

**macOS / Linux (bash / zsh):**

```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_LOGS_EXPORTER=console
export OTEL_METRICS_EXPORTER=console
export OTEL_LOG_TOOL_DETAILS=1
```

**Windows PowerShell:**

```powershell
$env:CLAUDE_CODE_ENABLE_TELEMETRY = "1"
$env:OTEL_LOGS_EXPORTER          = "console"
$env:OTEL_METRICS_EXPORTER       = "console"
$env:OTEL_LOG_TOOL_DETAILS       = "1"
```

要永久生效就寫進 shell rc 檔(`.bashrc`、`.zshrc`、PowerShell `$PROFILE`)。

#### Step 2 · 把事件累積到 log 檔

遙測只在 `claude` 跑著的時候會吐。要累積到值得分析的量,把 `stderr`
導去一個 append-only 的 log:

```bash
mkdir -p ~/.agent-radar

# macOS / Linux — 每次 Claude Code session 都附加到同一個 log
claude 2>> ~/.agent-radar/otel-events.log
```

```powershell
# Windows PowerShell — 一樣的概念
New-Item -ItemType Directory -Force "$env:USERPROFILE\.agent-radar" | Out-Null
claude 2>> "$env:USERPROFILE\.agent-radar\otel-events.log"
```

一次短對話大約累積幾 KB;**通常需要 1-2 週的正常使用**才有足夠訊號做
有意義的彙整。如果只關心最近一段時間,用後面 Step 3 的 `--since` /
`--until` 切時間窗即可,不必輪替 log。

**Log 維護**:這個檔是 append-only,Claude Code 不會自己縮小。建議
週期性輪替,例如每週做:

```bash
mv otel-events.log otel-events.$(date +%Y%m%d).log
: > otel-events.log
```

然後把輪替出來的那份餵給一次新的 `agent-radar usage` 跑。

**Production-grade 替代方案**:把 `OTEL_*_EXPORTER` 指到真的 OTel
collector(Jaeger / Honeycomb / Grafana Tempo …),而不是 console。
團隊聚合的話,那個 collector 就是 agent-radar 讀取的單一來源。
這裡示範的 console-to-file 是入門最低門檻。

#### Step 3 · 把 log 計分成 usage.json

Log 累積夠之後:

```bash
# 推薦:配 scan.json,讓比例有合理分母
# (例如「設了 5 個 MCP,實際呼叫 2 個」而不是只看「2 次呼叫」)
agent-radar usage \
    --otel-log ~/.agent-radar/otel-events.log \
    --scan scan.json \
    --target my-repo \
    -o usage.json

# 最簡:不給 scan,比例會 fallback 成純事件計數
agent-radar usage --otel-log ~/.agent-radar/otel-events.log -o usage.json
```

可選的旗標:

| 旗標 | 作用 |
|---|---|
| `--scan scan.json` | 提供配置側分母,讓 usage 比例有意義 |
| `--target <name>` | 從 `scan.json` 挑要對齊的 target(scan 有 >1 個 target 時必填) |
| `--account <email-or-uuid>` | 只統計符合 `user.email` / `user.account_uuid` 的事件;共用機器時很有用 |
| `--since 2026-05-01T00:00:00Z` | ISO 時間下界(含) |
| `--until 2026-05-25T23:59:59Z` | ISO 時間上界(含) |

#### Step 4 · Merge + 出報告

OTel 路徑跑完之後接回標準 pipeline,`merge` 跟 `report` 用法完全一樣:

```bash
agent-radar merge scan.json usage.json -o merged.json
agent-radar report --merged merged.json -o report.html
```

差別在於 HTML 雷達的 activation 側現在是從 OTel 量出來的,所以
`automation` 軸會看到真正的 hook 觸發次數(`session` 那條看不到)。

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
