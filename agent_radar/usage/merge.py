"""Align scan.json (config) with usage.json (usage) → merged.json.

The merged structure powers the dual-track radar + gap table + improvement
list in agent_radar.report.

Output shape (all text rendered at report time via agent_radar.i18n):
{
  "dimensions":         [dim_key, ...],            # from scanner
  "usage_dimensions":   [dim_key, ...],
  "level_thresholds":   [0, 20, 40, 60, 80],
  "targets": [
    {
      "name": "...",
      "path": "...",
      "level_threshold": int,                       # config-side
      "config_overall": float,
      "usage_overall":  float | None,
      "scores": {dim: {"config": float,
                       "usage":  float | None,
                       "gap":    float | None}},
      "config_findings_by_dim": {dim: [...]},       # raw structured findings
      "usage_findings_by_dim":  {dim: [...]},
      "top_gaps": [{"dimension": ..., "gap": ...,
                    "config": ..., "usage": ...,
                    "hint_key": "...", "hint_args": {...}}],
      "totals":      {...},
      "blind_spots": [{"key": ..., "args": ...}],
      "notes":       [str, ...],                    # free-form (collector-supplied)
    }
  ]
}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


# ---------------------------------------------------------------------------
# scan.json introspection — pull denominators usage scoring needs
# ---------------------------------------------------------------------------

def scan_context_for(scan_target: dict) -> dict:
    """Extract counts usage_score needs as denominators.

    Reads structured ``detail_args`` directly — no string parsing.
    """
    ctx: dict = {}
    for f in scan_target.get("findings", []):
        dim = f.get("dimension")
        label_key = f.get("label_key", "")
        args = f.get("detail_args") or {}
        score = f.get("score", 0)

        if dim == "mcp" and label_key == "scan.mcp.server_count":
            if "n" in args:
                ctx["servers_configured"] = int(args["n"])
        elif dim == "automation":
            if label_key == "scan.automation.hooks" and score > 0:
                # scanner only signals presence; treat as ≥1 registered to keep
                # the usage ratio definable.
                ctx.setdefault("hooks_registered", 1)
            elif label_key == "scan.automation.plugins" and score > 0:
                ctx.setdefault("plugins_installed", 1)
            elif label_key == "scan.automation.subagents" and "n" in args:
                ctx["subagents_defined"] = int(args["n"])
    return ctx


# ---------------------------------------------------------------------------
# improvement-hint generator
# ---------------------------------------------------------------------------

def _gap_hint(dim: str, target_name: str,
              usage_target: dict | None) -> tuple[str, dict]:
    """Return (hint_key, hint_args). Rendered to text by agent_radar.i18n."""
    usage_findings = (usage_target or {}).get("findings_by_dim", {}).get(dim, [])

    if dim == "skills":
        proactive = next(
            (x for x in usage_findings if x.get("label_key") == "usage.skills.proactive"),
            None,
        )
        if proactive and proactive.get("weight"):
            pct = int(proactive["score"] / proactive["weight"] * 100)
            return "gap.skills.proactive_low", {"target": target_name, "pct": pct}
        return "gap.skills.generic", {"target": target_name}
    if dim == "mcp":
        return "gap.mcp", {"target": target_name}
    if dim == "automation":
        return "gap.automation", {"target": target_name}
    if dim == "context_hygiene":
        return "gap.context_hygiene", {"target": target_name}
    if dim == "claude_md":
        return "gap.claude_md", {"target": target_name}
    return "gap.generic", {"target": target_name, "dim": dim}


def _rank_gaps(target_name: str, usage_target: dict | None,
               merged_scores: dict, top_n: int = 3) -> list[dict]:
    rows = []
    for dim, scores in merged_scores.items():
        gap = scores["gap"]
        if gap is None or gap <= 10:  # noise floor — ignore tiny gaps
            continue
        hint_key, hint_args = _gap_hint(dim, target_name, usage_target)
        rows.append({
            "dimension": dim,
            "gap": gap,
            "config": scores["config"],
            "usage": scores["usage"],
            "hint_key": hint_key,
            "hint_args": hint_args,
        })
    rows.sort(key=lambda r: r["gap"], reverse=True)
    return rows[:top_n]


# ---------------------------------------------------------------------------
# main merge
# ---------------------------------------------------------------------------

def merge(scan_json: dict, usage_json: dict) -> dict:
    dims = scan_json["dimensions"]
    if isinstance(dims, dict):  # legacy shape: dict of {key: label}
        dim_keys = list(dims.keys())
    else:
        dim_keys = list(dims)

    usage_dims = usage_json.get("usage_dimensions", dim_keys)
    if isinstance(usage_dims, dict):
        usage_dim_keys = list(usage_dims.keys())
    else:
        usage_dim_keys = list(usage_dims)

    usage_by_name: dict = usage_json.get("targets_by_name", {})

    merged_targets = []
    for target in scan_json["targets"]:
        name = target["name"]
        utgt = usage_by_name.get(name)
        usage_scores = (utgt or {}).get("scores", {})

        merged_scores: dict = {}
        for dim in dim_keys:
            cfg = target["scores"].get(dim, 0.0)
            use = usage_scores.get(dim)
            gap = (round(cfg - use, 1) if isinstance(use, (int, float)) else None)
            merged_scores[dim] = {"config": cfg, "usage": use, "gap": gap}

        top_gaps = _rank_gaps(name, utgt, merged_scores)

        merged_targets.append({
            "name": name,
            "path": target.get("path"),
            "level_threshold": target.get("level_threshold", 0),
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
        "dimensions": dim_keys,
        "usage_dimensions": usage_dim_keys,
        "level_thresholds": scan_json.get("level_thresholds", [0, 20, 40, 60, 80]),
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
    ap.add_argument("scan", help="agent-radar scan 產出的 JSON")
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
