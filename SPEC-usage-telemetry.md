# agent-radar · 運用度模組實作規格 (Usage Telemetry Module)

> **狀態**：Draft v1
> **目標讀者**：實作此模組的工程師 (或 Claude Code 自身)
> **前置依賴**：已完成的靜態掃描模組 (`scanner.py` / `report.py`)
> **核心命題**：靜態掃描量測「配置完整度」；本模組量測「實際運用度」。兩者並列，落差即為改善清單。

---

## 1. 為什麼需要這個模組

靜態掃描看得到「使用者寫了一個 skill、裝了 4 個 MCP server、定義了 2 個 hook」，
但看不到這些東西**在實際 session 中有沒有被用到**。這是檔案系統指紋的根本盲區。

Claude Code 內建 OpenTelemetry (OTel) 匯出，會在每次 session 吐出 metrics 與
events。其中數個事件，恰好能一對一補上靜態維度的運用面：

| 靜態維度 (配置) | 對應的 OTel 訊號 (運用) | 落差的意義 |
|---|---|---|
| Skills 運用 | `skill_activated` 事件 | 寫了 skill 但從未觸發 = 死 skill |
| MCP 整合 | `mcp_server_connection` 事件 | 設定了 server 但 `status=failed`/從未 connected = 死配置 |
| 自動化 (hooks) | `hook_registered` + `hook_execution_complete` | 註冊了 hook 但從未執行 = 裝飾性配置 |
| 自動化 (plugins) | `plugin_loaded` 事件 | 裝了 plugin 但未載入 |
| 情境衛生 (@import) | `at_mention` 事件 (`mention_type=file`) | 拆了檔但 session 從不 `@` 引用 |
| CLAUDE.md 成熟度 | `tool_decision` 的 reject 率 (間接) | 規則沒生效，使用者反覆手動否決 |

**設計原則**：本模組「只讀」既有的 OTel 輸出，不修改 Claude Code，也不要求使用者
跑側車 (sidecar)。我們假設使用者已依官方文件開啟遙測，並把 events 落到一個
可查詢的後端 (見 §3)。

---

## 2. 資料來源：Claude Code OTel 規格摘要

以下為實作時會用到的確切字段，摘自官方 monitoring 文件。**字段名稱以此為準。**

### 2.1 啟用方式 (使用者端，文件交代即可，非本模組職責)

```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_LOGS_EXPORTER=otlp           # events 走 logs 協定
export OTEL_METRICS_EXPORTER=otlp        # metrics 走 metrics 協定
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
# 關鍵：要拿到 skill / MCP / hook 的細節名稱，必須開啟：
export OTEL_LOG_TOOL_DETAILS=1
```

> **重要**：`OTEL_LOG_TOOL_DETAILS=1` 是本模組能否拿到「具名」資料的關鍵開關。
> 不開啟時，使用者自訂 / 第三方 skill 名稱會被遮成 `custom_skill` / `third-party`，
> MCP 的 `mcp_server_name` 也不會出現。規格的精準歸因高度依賴此旗標。

### 2.2 標準屬性 (所有 metrics 與 events 共有)

實作歸因 / 分組時會用到：

- `session.id`：session 唯一識別
- `user.account_uuid` / `user.account_id` / `user.email`：使用者身份 (OAuth 登入時)
- `organization.id`：組織 UUID
- `service.name` = `claude-code`、`service.version`：版本
- `os.type`、`host.arch`：環境

事件額外帶 `prompt.id` (串起單一 prompt 觸發的所有後續事件)，但**不可**用於 metrics 分組
(基數爆炸)。

### 2.3 本模組消費的核心事件 (event name → 關鍵字段)

#### `claude_code.skill_activated` — Skills 運用度的主訊號
- `skill.name`：skill 名稱 (自訂 / 第三方在未開 `OTEL_LOG_TOOL_DETAILS` 時為 `custom_skill`)
- `invocation_trigger`：`user-slash` / `claude-proactive` / `nested-skill`
- `skill.source`：`bundled` / `userSettings` / `projectSettings` / `plugin`
- `plugin.name`、`marketplace.name`：當 skill 來自 plugin

> **判讀**：`claude-proactive` 觸發比例高，代表 skill 的 description 寫得好 (能被模型自動命中)；
> 全靠 `user-slash` 手動觸發，代表 description 觸發力弱 —— 這直接呼應靜態維度裡的
> 「description 品質」評分。

#### `claude_code.mcp_server_connection` — MCP 運用度
- `status`：`connected` / `failed` / `disconnected`
- `transport_type`：`stdio` / `sse` / `http`
- `server_scope`：`user` / `project` / `local`
- `server_name` (需 `OTEL_LOG_TOOL_DETAILS=1`)
- `error_code`、`error`：連線失敗時

#### `claude_code.plugin_loaded` — Plugin 運用度
- 每個啟用的 plugin 在 session 開始時記一次 (適合做 fleet inventory)
- `plugin.name`、`plugin.scope` (`official`/`org`/`user-local`/`default-bundle`)
- `has_hooks`、`has_mcp`、`skill_path_count`、`command_path_count`、`agent_path_count`
- `plugin_id_hash`：去識別化計數用

#### `claude_code.hook_registered` + `hook_execution_complete` — Hook 運用度
- registered：`hook_event` (如 `PreToolUse`)、`hook_type`、`hook_source`
- execution_complete：`num_hooks`、`num_success`、`num_blocking`、`num_non_blocking_error`、`total_duration_ms`

> **判讀**：`hook_registered` 有、但對應的 `hook_execution_complete` 從未出現 = 註冊了卻沒觸發過。

#### `claude_code.at_mention` — 情境引用運用度
- `mention_type`：`file` / `directory` / `agent` / `mcp_resource`
- `success`：是否解析成功

#### `claude_code.tool_decision` — CLAUDE.md 生效度 (間接)
- `decision`：`accept` / `reject`
- `source`：`config` / `hook` / `user_permanent` / `user_temporary` / `user_abort` / `user_reject`
- `tool_name`

> **判讀**：高 `reject` 比例 (尤其 `user_reject`) 代表 Claude 反覆提議使用者不要的操作，
> 間接反映 CLAUDE.md 的規則沒寫好或沒生效。

#### 輔助：`tool_result` — 工具使用全貌
- `tool_name`、`success`、`duration_ms`、`error_type`
- `mcp_server_scope` (MCP 工具)
- 開 `OTEL_LOG_TOOL_DETAILS` 後有 `tool_parameters` (含 `skill_name`、`mcp_server_name`、`mcp_tool_name`、`subagent_type`)

### 2.4 本模組消費的核心 metrics

| Metric | 用途 |
|---|---|
| `claude_code.session.count` | session 量 (運用度的分母；多數比率要除以它) |
| `claude_code.active_time.total` | 實際活躍秒數，排除 idle |
| `claude_code.token.usage` | 可按 `skill.name` / `plugin.name` / `agent.name` 拆解 token 歸因 |
| `claude_code.cost.usage` | 同上，成本歸因到 skill/plugin/subagent |
| `claude_code.code_edit_tool.decision` | accept/reject 比，含 `language` |

> token / cost metric 的 `skill.name`、`plugin.name`、`agent.name` 屬性是隱藏寶藏：
> 可算出「某個 skill 實際消耗多少 token / 成本」，把運用度從「有沒有用」升級到「用得划不划算」。

---

## 3. 系統架構

```
                ┌─────────────────────────────────────────┐
                │  使用者的 Claude Code (已開 OTel)         │
                │  CLAUDE_CODE_ENABLE_TELEMETRY=1          │
                │  OTEL_LOG_TOOL_DETAILS=1                 │
                └───────────────┬─────────────────────────┘
                                │ OTLP (events + metrics)
                                ▼
                ┌─────────────────────────────────────────┐
                │  OTel 後端 (擇一)：                       │
                │  ClickHouse / Loki+Prometheus /          │
                │  自託管 Langfuse / Honeycomb 等          │
                └───────────────┬─────────────────────────┘
                                │ query API
                                ▼
        ┌───────────────────────────────────────────────────┐
        │  agent-radar usage 模組 (本規格)                    │
        │  ┌──────────────┐   ┌──────────────┐               │
        │  │ collectors/  │──▶│  usage_score │               │
        │  │ (後端 adapter)│   │  (評分引擎)   │               │
        │  └──────────────┘   └──────┬───────┘               │
        │                            │ usage.json            │
        │  ┌─────────────────────────▼───────────────────┐  │
        │  │  merge.py：對齊 scan.json + usage.json        │  │
        │  │  → 產生 config-vs-usage 雙軌資料              │  │
        │  └─────────────────────────┬───────────────────┘  │
        └────────────────────────────┼──────────────────────┘
                                     │
                                     ▼
                          report.py (擴充：雙軌雷達 + 落差表)
```

**後端選擇建議**：延續既有結論 (LangSmith vs Langfuse 比較)，本模組首選
**自託管 Langfuse + OpenTelemetry**，理由是 events 可走 OTLP 進 Langfuse，
且自託管利於敏感資料控管。次選 ClickHouse (結構化 event 查詢效率高)。
collector 層用 adapter pattern，後端可替換。

---

## 4. 模組檔案結構

```
agent-radar/
├── scanner.py              # 既有：靜態掃描
├── report.py               # 既有 → 擴充支援雙軌
├── usage/
│   ├── __init__.py
│   ├── collectors/
│   │   ├── base.py         # UsageCollector 抽象介面
│   │   ├── clickhouse.py   # ClickHouse adapter
│   │   ├── langfuse.py     # Langfuse adapter
│   │   └── otlp_file.py    # 離線：直接讀 console exporter 落地的 JSON
│   ├── usage_score.py      # 評分引擎 (本規格 §6)
│   └── merge.py            # 對齊靜態 + 運用 (本規格 §7)
└── SPEC-usage-telemetry.md # 本檔
```

---

## 5. Collector 介面

所有後端 adapter 實作同一介面，回傳「正規化事件聚合」，與後端無關。

```python
# usage/collectors/base.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

@dataclass
class UsageWindow:
    """一段時間內、某個歸因對象 (個人或團隊) 的聚合運用資料。"""
    since: datetime
    until: datetime
    session_count: int = 0
    active_seconds: float = 0.0

    # skill_activated 聚合：skill_name -> {triggers:{trigger:count}, sources:{...}, total:int}
    skills: dict = field(default_factory=dict)
    # mcp_server_connection 聚合：server_name -> {connected:int, failed:int, disconnected:int}
    mcp: dict = field(default_factory=dict)
    # plugin_loaded：plugin_name -> load_count
    plugins: dict = field(default_factory=dict)
    # hook：hook_event -> {registered:int, executed:int, blocking:int, errors:int}
    hooks: dict = field(default_factory=dict)
    # at_mention：mention_type -> {success:int, fail:int}
    mentions: dict = field(default_factory=dict)
    # tool_decision：{accept:int, reject:int, by_source:{source:count}}
    decisions: dict = field(default_factory=dict)
    # token/cost 歸因：skill_name -> tokens / usd
    token_by_skill: dict = field(default_factory=dict)
    cost_by_skill: dict = field(default_factory=dict)


class UsageCollector(Protocol):
    def fetch(self, since: datetime, until: datetime,
              account_filter: str | None = None) -> UsageWindow:
        """查詢後端，回傳聚合。account_filter 用於團隊中鎖定單一使用者
        (對應 user.account_uuid / user.email)。"""
        ...
```

### 5.1 離線 adapter (最低門檻，建議先做這個)

`otlp_file.py` 讓使用者用 console exporter 把事件落到檔案，模組直接讀，
**零後端依賴**，適合個人快速試用：

```bash
# 使用者端
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_LOGS_EXPORTER=console
export OTEL_LOG_TOOL_DETAILS=1
claude 2>> ~/.agent-radar/otel-events.log
```

adapter 逐行解析 console exporter 的輸出，抽出 `event.name` 與屬性後聚合成 `UsageWindow`。
這是 MVP 的最快路徑，不需要架 ClickHouse / Langfuse。

---

## 6. 評分引擎 (usage_score.py)

把 `UsageWindow` 換算成「運用度分數」，維度與靜態掃描**完全對齊**，
這樣兩張雷達才能疊在同一組軸上。

每個維度輸出 0~100。下列公式為啟發式，係數應依團隊實況校準。

### 6.1 Skills 運用度

```
proactive_ratio = proactive_activations / max(total_activations, 1)
activation_rate = total_activations / max(session_count, 1)

skills_usage = clamp(
    40 * min(activation_rate, 1.0)        # 每個 session 平均至少觸發 1 次給滿
  + 40 * proactive_ratio                  # 自動觸發比例 (反映 description 品質)
  + 20 * (distinct_skills_used > 0)       # 是否真用到 ≥1 個 skill
, 0, 100)
```

### 6.2 MCP 運用度

```
# 連線健康度：connected 佔總連線嘗試比例
mcp_health = connected / max(connected + failed, 1)
# 實際被工具呼叫過的 server 比例 (從 tool_result 的 mcp_server_scope 推)
mcp_used_ratio = servers_invoked / max(servers_configured, 1)

mcp_usage = clamp(50 * mcp_health + 50 * mcp_used_ratio, 0, 100)
```

> **跨模組校驗**：`servers_configured` 取自靜態掃描 (scan.json 的 MCP server 數)，
> `servers_invoked` 取自運用資料。這是「配置 vs 運用」落差最直接的數字。

### 6.3 自動化運用度 (hooks + plugins + commands + subagents)

```
hook_exec_ratio    = hooks_executed / max(hooks_registered, 1)
plugin_load_ratio  = plugins_loaded / max(plugins_installed, 1)   # installed 取自靜態掃描
# subagent 透過 token/cost metric 的 agent.name 屬性，或 tool_result 的 subagent_type 判定
subagent_used      = (distinct_subagents_invoked > 0)

automation_usage = clamp(
    40 * hook_exec_ratio
  + 35 * plugin_load_ratio
  + 25 * subagent_used
, 0, 100)
```

### 6.4 情境衛生運用度

```
file_mention_rate = file_mentions / max(session_count, 1)
mention_success   = mention_success / max(mention_total, 1)

context_usage = clamp(
    60 * min(file_mention_rate, 1.0)   # 平均每 session 至少 @ 引用 1 次給滿
  + 40 * mention_success
, 0, 100)
```

### 6.5 CLAUDE.md 生效度 (反向指標)

```
reject_ratio = rejects / max(accepts + rejects, 1)
# reject 越低代表 Claude 的提議越貼合使用者意圖 → 規則越生效
claude_md_effectiveness = clamp(100 * (1 - reject_ratio), 0, 100)
```

> 注意：reject 高不必然是 CLAUDE.md 的錯 (也可能是任務探索性高)。此維度標為「間接訊號」，
> 在報告中以較低權重呈現，並附判讀提醒。

### 6.6 迭代維度

迭代是「歷史行為」，靜態掃描已用 git history 量測，運用資料無對應訊號。
本維度在運用雷達上**留空 (N/A)**，報告中以虛線標示，避免誤導。

---

## 7. 對齊與合併 (merge.py)

```python
def merge(scan_json: dict, usage_json: dict) -> dict:
    """
    產出雙軌結構，供 report.py 同軸疊圖。
    對齊規則：
      - 維度 key 與靜態掃描完全相同 (claude_md / skills / mcp /
        automation / context_hygiene / iteration)
      - 每個維度同時帶 config_score 與 usage_score
      - gap = config_score - usage_score
      - iteration 的 usage_score = None (N/A)
    """
    dims = scan_json["dimensions"]
    out = {"dimensions": dims, "targets": []}
    for target in scan_json["targets"]:
        u = usage_json["targets_by_name"].get(target["name"], {})
        merged_scores = {}
        for d in dims:
            cfg = target["scores"][d]
            use = u.get("scores", {}).get(d)   # 可能為 None
            merged_scores[d] = {
                "config": cfg,
                "usage": use,
                "gap": (round(cfg - use, 1) if use is not None else None),
            }
        out["targets"].append({
            "name": target["name"],
            "scores": merged_scores,
            # 落差最大的維度 = 最該優先處理的「死配置」
            "top_gaps": _rank_gaps(merged_scores),
        })
    return out
```

`top_gaps` 是整份報告**最有行動力的輸出**：它直接列出「你配置了但根本沒在用」的項目，
依落差大小排序，等於一份自動生成的改善清單。

---

## 8. 報告擴充 (report.py)

在既有 HTML 報告上增加：

1. **雙軌雷達**：同一組軸上疊兩條多邊形——實線 = 配置分數，虛線 = 運用分數。
   兩線之間的面積差，視覺上就是「能力浪費區」。
2. **落差表 (Gap Table)**：每個維度一列，三欄 `配置 / 運用 / 落差`，
   落差用紅→綠色階。`iteration` 列的運用欄顯示 `N/A`。
3. **改善清單卡片**：把所有 target 的 `top_gaps` 攤平，挑落差最大的前 5 項，
   每項一句話可執行建議。例如：
   - 「你設定了 4 個 MCP server，但只有 2 個曾被呼叫。檢查 `sentry`、`playwright` 是否真的需要。」
   - 「`data-pipeline` skill 從未被 proactive 觸發，全靠手動 `/`。考慮改寫它的 description。」
4. **token/cost 歸因小圖** (選配)：哪個 skill / plugin 最燒 token，對應 ROI 視角。

---

## 9. 隱私與資安注意事項

實作與文件**必須**明確提醒使用者：

- `OTEL_LOG_TOOL_DETAILS=1` 會讓 Bash 指令、檔案路徑、MCP 參數進入事件流，
  屬敏感資料。團隊部署前應確認後端的存取控制與保留政策。
- 不要開 `OTEL_LOG_USER_PROMPTS` / `OTEL_LOG_RAW_API_BODIES`，本模組評分**不需要**
  prompt 內容或 API body；開了只會擴大資料外洩面。
- 團隊歸因依賴 `user.email` / `user.account_uuid`。跨人比較前應取得成員同意，
  並把本工具定位為「自我改善」而非「績效監控」——後者會破壞信任且訊雜比低。
- 本模組只讀資料、只做聚合，不回寫任何 Claude Code 設定。

---

## 10. 實作里程碑 (建議順序)

1. **M1 — 離線 MVP**：`otlp_file.py` + `usage_score.py`，個人用 console exporter
   落檔，先跑通 Skills 與 MCP 兩個維度的運用分數。
2. **M2 — 合併與雙軌報告**：`merge.py` + `report.py` 雙軌雷達 + 落差表。
   此時「配置 vs 運用」的核心價值就完整了。
3. **M3 — 後端 adapter**：補 `clickhouse.py` 或 `langfuse.py`，支援團隊規模查詢。
4. **M4 — 成本歸因**：接 token/cost metric 的 skill/plugin 屬性，加 ROI 小圖。
5. **M5 — Traces (beta，選配)**：若需要 prompt → tool 的完整因果鏈，
   開 `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` 接 span，做更細的 skill 觸發路徑分析。

---

## 附錄 A — 事件 / 維度 速查表

| OTel 事件 | 餵給哪個運用維度 | 關鍵字段 |
|---|---|---|
| `skill_activated` | Skills | `skill.name`, `invocation_trigger`, `skill.source` |
| `mcp_server_connection` | MCP | `status`, `server_name`, `transport_type` |
| `plugin_loaded` | 自動化 | `plugin.name`, `has_hooks`, `has_mcp` |
| `hook_registered` | 自動化 | `hook_event`, `hook_source` |
| `hook_execution_complete` | 自動化 | `num_success`, `num_blocking` |
| `at_mention` | 情境衛生 | `mention_type`, `success` |
| `tool_decision` | CLAUDE.md 生效度 | `decision`, `source` |
| `tool_result` | (輔助多維) | `tool_name`, `mcp_server_scope`, `tool_parameters` |
| metric `token.usage` | 成本歸因 | attr `skill.name`/`plugin.name`/`agent.name` |
| metric `session.count` | (比率分母) | `start_type` |
| metric `active_time.total` | (參與度) | `type` (`user`/`cli`) |
