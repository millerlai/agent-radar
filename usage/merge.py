"""Align scan.json (config) with usage.json (usage) → merged.json.

The merged structure powers the dual-track radar + gap table + improvement
list in report.py. SPEC §7.

Output shape:
{
  "dimensions":         {dim: label, ...},         # same keys as scanner
  "usage_dimensions":   {dim: label, ...},
  "levels":             [[threshold, label], ...], # carried over from scan
  "targets": [
    {
      "name": "...",
      "path": "...",
      "level": "...",                              # config-side level (scan)
      "config_overall": float,
      "usage_overall":  float | None,
      "scores": {dim: {"config": float,
                       "usage":  float | None,
                       "gap":    float | None}},
      "config_findings_by_dim": {dim: [...]},      # from scan
      "usage_findings_by_dim":  {dim: [...]},      # from usage
      "top_gaps": [{"dimension": ..., "gap": ...,
                    "hint": "..."}],
      "totals":      {...},                         # diagnostic counts
      "blind_spots": [...],
      "notes":       [...],
    }
  ]
}
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# scan.json introspection — pull denominators usage scoring needs
# ---------------------------------------------------------------------------

_MCP_COUNT_RE = re.compile(r"(\d+)\s*個\s*MCP\s*server", re.IGNORECASE)
_SUBAGENT_COUNT_RE = re.compile(r"(\d+)\s*個\s*subagent", re.IGNORECASE)
_CMD_COUNT_RE = re.compile(r"(\d+)\s*個自訂命令", re.IGNORECASE)


def scan_context_for(scan_target: dict) -> dict:
    """Extract counts usage_score needs as denominators.

    Best-effort: scan.py embeds counts in `detail` strings; we regex them out.
    Falls back to None (let usage_score derive from events) when uncertain.
    """
    ctx: dict = {}
    for f in scan_target.get("findings", []):
        dim = f.get("dimension")
        detail = f.get("detail") or ""
        label = f.get("label") or ""
        if dim == "mcp" and "數量" in label:
            m = _MCP_COUNT_RE.search(detail)
            if m:
                ctx["servers_configured"] = int(m.group(1))
        elif dim == "automation":
            if "Hooks" in label and f.get("score", 0) > 0:
                # scanner only signals presence; treat as ≥1 registered to keep
                # ratio definable. Real count would need scanner extension.
                ctx.setdefault("hooks_registered", 1)
            if "Plugins" in label and f.get("score", 0) > 0:
                ctx.setdefault("plugins_installed", 1)
            if "Subagents" in label:
                m = _SUBAGENT_COUNT_RE.search(detail)
                if m:
                    ctx["subagents_defined"] = int(m.group(1))
    return ctx


# ---------------------------------------------------------------------------
# improvement-hint generator
# ---------------------------------------------------------------------------

def _gap_hint(dim: str, target_name: str, scan_target: dict,
              usage_target: dict | None) -> str:
    """One-line, actionable suggestion based on the dimension and any context."""
    config_findings = {f["dimension"]: f for f in scan_target.get("findings", [])}
    usage_findings = (usage_target or {}).get("findings_by_dim", {}).get(dim, [])

    if dim == "skills":
        proactive = next((x for x in usage_findings if "proactive" in x["label"]), None)
        return (
            f"`{target_name}`：Skills 配置完整但實際觸發少。"
            + (f"proactive 比例僅 {int(proactive['score']/proactive['weight']*100)}%，"
               "重寫 description 讓模型能命中觸發條件。"
               if proactive and proactive["weight"] else
               "考慮重寫 SKILL.md 的 description，加入明確觸發場景。")
        )
    if dim == "mcp":
        return (f"`{target_name}`：你設定了 MCP server，但實際被呼叫的比例偏低。"
                "檢查哪些 server 從未被使用，刪除或重新評估。")
    if dim == "automation":
        return (f"`{target_name}`：自動化 (hooks/plugins/subagents) 配置存在但運用不足。"
                "確認 hooks 是否真的觸發、subagents 是否被派遣。")
    if dim == "context_hygiene":
        return (f"`{target_name}`：CLAUDE.md / settings 結構良好，但 session 中"
                "幾乎不用 @ 引用。在常用檔上養成 `@path` 習慣以聚焦 context。")
    if dim == "claude_md":
        return (f"`{target_name}`：CLAUDE.md 寫得齊全，但 tool_decision 顯示提議常被拒。"
                "回頭看哪些建議被拒，把規則明文寫進 CLAUDE.md。")
    return f"`{target_name}` 在 {dim} 維度配置 vs 運用落差大，請進一步審視。"


def _rank_gaps(target_name: str, scan_target: dict, usage_target: dict | None,
               merged_scores: dict, top_n: int = 3) -> list[dict]:
    rows = []
    for dim, scores in merged_scores.items():
        gap = scores["gap"]
        if gap is None or gap <= 10:  # noise floor — ignore tiny gaps
            continue
        rows.append({
            "dimension": dim,
            "gap": gap,
            "config": scores["config"],
            "usage": scores["usage"],
            "hint": _gap_hint(dim, target_name, scan_target, usage_target),
        })
    rows.sort(key=lambda r: r["gap"], reverse=True)
    return rows[:top_n]


# ---------------------------------------------------------------------------
# main merge
# ---------------------------------------------------------------------------

def merge(scan_json: dict, usage_json: dict) -> dict:
    dims: dict = scan_json["dimensions"]
    usage_dims: dict = usage_json.get("usage_dimensions", dims)
    usage_by_name: dict = usage_json.get("targets_by_name", {})

    merged_targets = []
    for target in scan_json["targets"]:
        name = target["name"]
        utgt = usage_by_name.get(name)
        usage_scores = (utgt or {}).get("scores", {})

        # build per-dim {config, usage, gap}
        merged_scores: dict = {}
        for dim in dims:
            cfg = target["scores"].get(dim, 0.0)
            use = usage_scores.get(dim)  # None for iteration
            gap = (round(cfg - use, 1) if isinstance(use, (int, float)) else None)
            merged_scores[dim] = {"config": cfg, "usage": use, "gap": gap}

        top_gaps = _rank_gaps(name, target, utgt, merged_scores)

        merged_targets.append({
            "name": name,
            "path": target.get("path"),
            "level": target.get("level"),
            "config_overall": target.get("overall"),
            "usage_overall": (utgt or {}).get("overall"),
            "scores": merged_scores,
            "config_findings_by_dim": _group_findings(target.get("findings", [])),
            "usage_findings_by_dim": (utgt or {}).get("findings_by_dim", {}),
            "top_gaps": top_gaps,
            "totals": (utgt or {}).get("totals", {}),
            "blind_spots": target.get("blind_spots", []),
            "notes": (utgt or {}).get("notes", []),
        })

    return {
        "dimensions": dims,
        "usage_dimensions": usage_dims,
        "levels": scan_json.get("levels", []),
        "targets": merged_targets,
    }


def _group_findings(findings: list) -> dict:
    out: dict = {}
    for f in findings:
        out.setdefault(f["dimension"], []).append(f)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Merge scan.json + usage.json into merged.json")
    ap.add_argument("scan", help="scanner.py 產出的 JSON")
    ap.add_argument("usage", help="usage 模組產出的 JSON")
    ap.add_argument("-o", "--output", default="merged.json")
    args = ap.parse_args()

    scan = json.loads(Path(args.scan).read_text(encoding="utf-8"))
    usage = json.loads(Path(args.usage).read_text(encoding="utf-8"))
    merged = merge(scan, usage)
    Path(args.output).write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] 已寫入 {args.output}")


if __name__ == "__main__":
    main()
