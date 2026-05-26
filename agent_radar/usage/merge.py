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
              usage_target: dict | None,
              direction: str = "under") -> tuple[str, dict]:
    """Return (hint_key, hint_args). Rendered to text by agent_radar.i18n.

    ``direction``: ``"under"`` (configured > activated — typical underused case)
    or ``"over"`` (activated > configured — heavy use relative to config; a
    win signal, not a problem). Different hint keys per direction.
    """
    usage_findings = (usage_target or {}).get("findings_by_dim", {}).get(dim, [])

    if direction == "over":
        # Configured side under-represents what's actually happening — this is
        # almost always a positive signal (the user is doing more with less
        # config than the score implies). Hint per axis where it's interesting.
        if dim == "automation":
            return "gap.over.automation", {"target": target_name}
        if dim == "claude_md":
            return "gap.over.claude_md", {"target": target_name}
        return "gap.over.generic", {"target": target_name, "dim": dim}

    # Default: "under" direction (the actionable case)
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


# Noise-floor heuristics. Both have to be exceeded for a gap to surface.
# - GAP_ABS_FLOOR: small absolute gaps (≤10 points) are noise either way.
# - GAP_RATIO_FLOOR: a 16-point gap means very different things at
#   config=30/usage=14 (ratio 0.53 — real headroom) vs config=90/usage=74
#   (ratio 0.18 — basically aligned). Threshold is heuristic; calibrate
#   after dogfood data is in.
GAP_ABS_FLOOR = 10
GAP_RATIO_FLOOR = 0.3


def _rank_gaps(target_name: str, usage_target: dict | None,
               merged_scores: dict, top_n: int = 5,
               config_findings_by_dim: dict | None = None,
               usage_findings_by_dim: dict | None = None) -> list[dict]:
    """Rank axes by |gap|, attach findings for drill-down, label direction.

    Both directions are reported:
      - ``"under"``: configured > activated (the canonical "you configured
        but never used it" case — actionable)
      - ``"over"``: activated > configured (heavy use relative to config —
        a win signal, often points to a quality concern in config docs)

    Noise floor: ``|gap| > GAP_ABS_FLOOR`` *and*
    ``gap_ratio > GAP_RATIO_FLOOR``, where
    ``gap_ratio = |gap| / max(config, usage, 1)``.

    Using the larger side as denominator keeps the ratio symmetric across
    directions — a gap of 16 is "missing 1/2 of the bigger side" regardless
    of which side is bigger. A single-side denominator (e.g. always
    ``config``) leaks when ``over`` direction lands on a tiny configured
    score. See ``feedback_commensurable_kpi_units`` in user memory for why.
    """
    cfg_by = config_findings_by_dim or {}
    use_by = usage_findings_by_dim or {}
    rows = []
    for dim, scores in merged_scores.items():
        gap = scores["gap"]
        if gap is None:
            continue
        # gap is non-None ⇒ both config and usage are numeric (merge.py:212).
        denom = max(scores["config"], scores["usage"], 1)
        gap_ratio = abs(gap) / denom
        if abs(gap) <= GAP_ABS_FLOOR or gap_ratio < GAP_RATIO_FLOOR:
            continue
        direction = "under" if gap > 0 else "over"
        hint_key, hint_args = _gap_hint(dim, target_name, usage_target, direction)
        rows.append({
            "dimension": dim,
            "gap": gap,                       # signed; negative = over-activated
            "abs_gap": abs(gap),              # for ranking
            "gap_ratio": round(gap_ratio, 3), # 0..1, direction-agnostic
            "direction": direction,
            "config": scores["config"],
            "usage": scores["usage"],
            "hint_key": hint_key,
            "hint_args": hint_args,
            # Findings for click-to-drill-down in the report
            "config_findings": cfg_by.get(dim, []),
            "usage_findings": use_by.get(dim, []),
        })
    rows.sort(key=lambda r: r["abs_gap"], reverse=True)
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
    # session_scanner emits both ``targets`` (list) and ``targets_by_name``
    # (dict). If only the list shape is present (e.g. user wrote their own
    # adapter), fall back to building the by-name map here.
    if not usage_by_name:
        usage_by_name = {t.get("name"): t
                         for t in usage_json.get("targets", []) if t.get("name")}

    # Cross-side join also needs a path-based fallback: session_scanner
    # derives display names from a lossy encoding (e.g.
    # ``D--project-tradestation-monarch`` → ``monarch``), which never matches
    # the scan target's pretty name (``tradestation-monarch``). The
    # ``project_dir`` field is the encoded path itself — a stable join key
    # we can reproduce on the scan side.
    def _encode_path_for_join(path_str: str) -> str:
        return path_str.replace(":", "-").replace("\\", "-").replace("/", "-")

    usage_by_project_dir: dict = {}
    for t in usage_json.get("targets", []):
        pd = t.get("project_dir")
        if pd:
            usage_by_project_dir[pd] = t

    merged_targets = []
    for target in scan_json["targets"]:
        name = target["name"]
        utgt = usage_by_name.get(name)
        # Fall back to path-encoded match if the lossy session-side name
        # didn't line up with scan's pretty basename.
        if utgt is None and target.get("path"):
            utgt = usage_by_project_dir.get(_encode_path_for_join(target["path"]))
        usage_scores = (utgt or {}).get("scores", {})

        merged_scores: dict = {}
        for dim in dim_keys:
            cfg = target["scores"].get(dim, 0.0)
            use = usage_scores.get(dim)
            gap = (round(cfg - use, 1) if isinstance(use, (int, float)) else None)
            merged_scores[dim] = {"config": cfg, "usage": use, "gap": gap}

        # 0.2.0 session_scanner emits a raw ``findings`` list; legacy
        # usage_score OTel emits ``findings_by_dim`` pre-grouped. Support
        # both by grouping on the fly when raw findings are present.
        utgt_findings_by_dim = (utgt or {}).get("findings_by_dim") or \
            _group_findings((utgt or {}).get("findings", []))
        cfg_findings_by_dim = _group_findings(target.get("findings", []))

        # Recompute top_gaps with findings attached for drill-down render.
        top_gaps = _rank_gaps(
            name, utgt, merged_scores,
            config_findings_by_dim=cfg_findings_by_dim,
            usage_findings_by_dim=utgt_findings_by_dim,
        )

        merged_targets.append({
            "name": name,
            "path": target.get("path"),
            "config_overall": target.get("overall"),
            "usage_overall": (utgt or {}).get("overall"),
            "scores": merged_scores,
            "config_findings_by_dim": cfg_findings_by_dim,
            "usage_findings_by_dim": utgt_findings_by_dim,
            "top_gaps": top_gaps,
            "totals": (utgt or {}).get("totals", {}),
            "blind_spots": (target.get("blind_spots", []) +
                            (utgt or {}).get("blind_spots", [])),
            "notes": (utgt or {}).get("notes", []),
        })

    return {
        "dimensions": dim_keys,
        "usage_dimensions": usage_dim_keys,
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
