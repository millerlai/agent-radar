#!/usr/bin/env python3
"""
agent-radar :: agent_radar.report
=================================
HTML report renderer.

0.2.0 framing: Activation Gap Diagnostic
----------------------------------------
``agent-radar scan`` outputs *configured-side facts* (what you set up).
``agent-radar session`` outputs *activated-side facts* (what actually fires
in JSONL sessions). The gap between the two is the product's main insight.

CLI shapes:
  agent-radar report scan.json -o report.html
    → "Configured Coverage" view (configured side only)
  agent-radar report scan.json --session session.json -o report.html
    → "Activation Gap" view (merged inline)
  agent-radar report --merged merged.json -o report.html
    → "Activation Gap" view (from pre-merged JSON)

Producers emit only language-neutral keys; ``--lang en|zh`` controls text.
The 0.1.x "Maturity Radar" / "Team Benchmark" / L0-L4 level scale are gone:
they framed configured-ness as quality, which the tool cannot actually
measure.
"""

import argparse
import json
import math
import sys
from pathlib import Path

from . import i18n as i18n_mod
from .usage.merge import merge as _inline_merge


# Series colors — kept from 0.1.x for visual continuity.
PALETTE = ["#4ade80", "#38bdf8", "#fbbf24", "#f472b6", "#a78bfa", "#fb923c", "#2dd4bf", "#f87171"]


# ----------------------------------------------------------------------------
# UI chrome strings (finding/dimension/level strings live in i18n.py)
# ----------------------------------------------------------------------------

STRINGS = {
    "en": {
        "html_lang": "en",
        # Scan-only (configured coverage)
        "title_scan": "Configured Coverage · agent-radar",
        "kicker_scan": "agent-radar · configured fingerprint",
        "h1_scan_pre": "Configured ",
        "h1_scan_em": "Coverage",
        "h1_scan_post": " — what you've set up",
        "sub_scan": ("Counts the Claude Code artifacts on disk: CLAUDE.md, "
                     "skills, MCP servers, hooks, subagents, commands, plugins, "
                     "and gitignore hygiene. The score is configured coverage, "
                     "NOT a quality grade — pair with `agent-radar session` to see "
                     "what actually fires inside Claude Code."),
        "h2_configured": "Configured Coverage Radar",
        # Merged (activation gap)
        "title_merged": "Activation Gap · agent-radar",
        "kicker_merged": "agent-radar · configured vs activated",
        "h1_merged_pre": "Activation ",
        "h1_merged_em": "Gap",
        "h1_merged_post": " — what you configured but never used",
        "sub_merged": ("Overlays the configured side (solid lines) with the "
                       "activated side (dashed lines) on the same five axes. "
                       "The area between them is the capability waste zone."),
        "h2_dual": "Activation Gap Radar",
        "h2_top_gaps": "Biggest Gaps",
        "h2_targets": "Per-Target Detail",
        "card_sub_top_gaps": ("Top items by configured vs activated gap. Large gap "
                              "= configured but unused; that's the cheapest "
                              "capability to fix."),
        # Table headers
        "th_target": "Target",
        "th_dim": "Dimension",
        "th_config": "Configured",
        "th_usage": "Activated",
        "th_gap": "Gap",
        # Labels
        "blind_label": "BLIND SPOT",
        "note_label": "NOTE",
        "col_config": "CONFIGURED",
        "col_usage": "ACTIVATED",
        "direction_under": "UNDERUSED",
        "direction_over":  "OVER-ACTIVATED",
        "expand_hint": "Click to expand the underlying configured + activated findings",
        "no_findings": "No findings",
        "no_usage_signals": "No activation signals (no sessions logged?)",
        "no_targets": "No targets scanned.",
        # Footer / legend
        "footer_scan": "agent-radar · configured-side scan · pair with `session` for the activation view",
        "footer_merged": "agent-radar · configured vs activated · gap = improvement headroom",
        "dual_legend_cfg": "Configured (filesystem fingerprint)",
        "dual_legend_use": "Activated (session JSONL)",
        "gap_meta_config": "· configured ",
        "gap_meta_usage": "· activated ",
        "gap_meta_gap": "· gap ",
        "pair_hint": ("Tip: run `agent-radar session -o session.json` and "
                      "re-run report with `--session session.json` to see the "
                      "activation gap."),
    },
    "zh": {
        "html_lang": "zh-Hant",
        "title_scan": "配置覆蓋率 · agent-radar",
        "kicker_scan": "agent-radar · configured fingerprint",
        "h1_scan_pre": "配置",
        "h1_scan_em": "覆蓋率",
        "h1_scan_post": " — 你裝了什麼",
        "sub_scan": ("計數磁碟上的 Claude Code 物件:CLAUDE.md、skills、MCP server、"
                     "hooks、subagents、commands、plugins、gitignore 衛生。"
                     "這是配置覆蓋率,**不是**品質分數—— 搭配 `agent-radar session` "
                     "才看得到實際在 Claude Code 內觸發了什麼。"),
        "h2_configured": "配置覆蓋率雷達",
        "title_merged": "Activation Gap · agent-radar",
        "kicker_merged": "agent-radar · configured vs activated",
        "h1_merged_pre": "Activation ",
        "h1_merged_em": "Gap",
        "h1_merged_post": " — 你配了但沒在用的能力",
        "sub_merged": ("把「配置側」(實線) 與「啟動側」(虛線) 疊在五大軸上。"
                       "兩者之間的面積就是能力浪費區。"),
        "h2_dual": "Activation Gap 雷達",
        "h2_top_gaps": "最大落差",
        "h2_targets": "目標細節",
        "card_sub_top_gaps": ("依配置 vs 啟動落差排序的項目。落差大 = 你配了但沒在用,"
                              "最有機會用最少力氣補上的能力。"),
        "th_target": "目標",
        "th_dim": "維度",
        "th_config": "配置",
        "th_usage": "啟動",
        "th_gap": "落差",
        "blind_label": "盲區",
        "note_label": "NOTE",
        "col_config": "配置 · CONFIGURED",
        "col_usage": "啟動 · ACTIVATED",
        "direction_under": "用不夠 · UNDERUSED",
        "direction_over":  "用得很重 · OVER-ACTIVATED",
        "expand_hint": "點開看背後的 configured + activated 細節",
        "no_findings": "無 findings",
        "no_usage_signals": "無啟動訊號 (還沒有 session 紀錄?)",
        "no_targets": "未掃描任何目標。",
        "footer_scan": "agent-radar · configured-side scan · 配合 `session` 看 activation",
        "footer_merged": "agent-radar · configured vs activated · 落差即為改善空間",
        "dual_legend_cfg": "配置 · CONFIGURED (filesystem fingerprint)",
        "dual_legend_use": "啟動 · ACTIVATED (session JSONL)",
        "gap_meta_config": "· 配置 ",
        "gap_meta_usage": "· 啟動 ",
        "gap_meta_gap": "· 落差 ",
        "pair_hint": ("提示:跑 `agent-radar session -o session.json`, "
                      "再加 `--session session.json` 重跑 report 就能看到 activation gap。"),
    },
}


def _t(lang, key):
    return STRINGS.get(lang, STRINGS["en"]).get(key, STRINGS["en"].get(key, key))


def _looks_like_merged(data: dict) -> bool:
    """True iff ``data`` carries merge.py's score shape (dicts, not numbers).

    The cheapest reliable signal: in scan.json the first target's first
    score value is a number; in merged.json it's a ``{"config","usage","gap"}``
    dict. Empty / malformed inputs return False — let downstream handle them.
    """
    targets = data.get("targets") if isinstance(data, dict) else None
    if not targets:
        return False
    first_scores = (targets[0] or {}).get("scores") or {}
    sample = next(iter(first_scores.values()), None)
    return isinstance(sample, dict)


# ----------------------------------------------------------------------------
# Per-finding render helpers
# ----------------------------------------------------------------------------

def _finding_label(f: dict, lang: str) -> str:
    return i18n_mod.t_label(f.get("label_key", ""), lang)


def _finding_detail(f: dict, lang: str) -> str:
    return i18n_mod.t_detail(f.get("detail_key"), f.get("detail_args"), lang)


def _blind_text(b, lang: str) -> str:
    if isinstance(b, dict):
        return i18n_mod.t_blind(b.get("key", ""), b.get("args"), lang)
    return str(b)


def _hint_text(g: dict, lang: str) -> str:
    return i18n_mod.t_hint(g.get("hint_key", "gap.generic"),
                           g.get("hint_args"), lang)


def _normalise_dimensions(value) -> list:
    if isinstance(value, dict):
        return list(value.keys())
    return list(value or [])


# ----------------------------------------------------------------------------
# SVG helpers
# ----------------------------------------------------------------------------

def _polar_point(cx, cy, radius, value, i, n):
    ang = -math.pi / 2 + (2 * math.pi * i / n)
    r = radius * (value / 100)
    return cx + r * math.cos(ang), cy + r * math.sin(ang)


def radar_svg(targets, dim_keys, dim_labels, size=460, idx_offset=0):
    """Single-track radar (configured-only)."""
    pad = 100
    vb = size + pad * 2
    cx = cy = size / 2 + pad
    radius = size * 0.34
    n = len(dim_keys)
    rings = 4

    parts = [f'<svg viewBox="0 0 {vb} {vb}" xmlns="http://www.w3.org/2000/svg" '
             f'role="img" class="radar">']

    for ring in range(1, rings + 1):
        rr = radius * ring / rings
        pts = []
        for i in range(n):
            ang = -math.pi / 2 + (2 * math.pi * i / n)
            pts.append(f"{cx + rr*math.cos(ang):.1f},{cy + rr*math.sin(ang):.1f}")
        parts.append(f'<polygon points="{" ".join(pts)}" class="grid-ring"/>')

    for i, key in enumerate(dim_keys):
        ang = -math.pi / 2 + (2 * math.pi * i / n)
        ex, ey = cx + radius*math.cos(ang), cy + radius*math.sin(ang)
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" class="axis"/>')
        lx, ly = cx + (radius+30)*math.cos(ang), cy + (radius+30)*math.sin(ang)
        anchor = "middle"
        if math.cos(ang) > 0.3:
            anchor = "start"
        elif math.cos(ang) < -0.3:
            anchor = "end"
        label = dim_labels[key]
        parts.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
            f'class="axis-label" dominant-baseline="middle">{label}</text>')

    for ti, t in enumerate(targets):
        color = PALETTE[(ti + idx_offset) % len(PALETTE)]
        pts = []
        for i, key in enumerate(dim_keys):
            x, y = _polar_point(cx, cy, radius, t["scores"].get(key, 0), i, n)
            pts.append(f"{x:.1f},{y:.1f}")
        parts.append(
            f'<polygon points="{" ".join(pts)}" fill="{color}" '
            f'fill-opacity="0.12" stroke="{color}" stroke-width="2.5" '
            f'class="series" style="--c:{color}"/>')
        for i, key in enumerate(dim_keys):
            x, y = _polar_point(cx, cy, radius, t["scores"].get(key, 0), i, n)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}"/>')

    parts.append('</svg>')
    return "\n".join(parts)


def dual_radar_svg(merged_targets, dim_keys, dim_labels, size=460, idx_offset=0):
    """Dual-track radar: solid (configured) + dashed (activated) per target."""
    pad = 100
    vb = size + pad * 2
    cx = cy = size / 2 + pad
    radius = size * 0.34
    n = len(dim_keys)
    rings = 4

    parts = [f'<svg viewBox="0 0 {vb} {vb}" xmlns="http://www.w3.org/2000/svg" '
             f'role="img" class="radar">']

    for ring in range(1, rings + 1):
        rr = radius * ring / rings
        pts = []
        for i in range(n):
            ang = -math.pi / 2 + (2 * math.pi * i / n)
            pts.append(f"{cx + rr*math.cos(ang):.1f},{cy + rr*math.sin(ang):.1f}")
        parts.append(f'<polygon points="{" ".join(pts)}" class="grid-ring"/>')

    for i, key in enumerate(dim_keys):
        ang = -math.pi / 2 + (2 * math.pi * i / n)
        ex, ey = cx + radius*math.cos(ang), cy + radius*math.sin(ang)
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" class="axis"/>')
        lx, ly = cx + (radius+30)*math.cos(ang), cy + (radius+30)*math.sin(ang)
        anchor = "middle"
        if math.cos(ang) > 0.3:
            anchor = "start"
        elif math.cos(ang) < -0.3:
            anchor = "end"
        label = dim_labels[key]
        parts.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
            f'class="axis-label" dominant-baseline="middle">{label}</text>')

    for ti, t in enumerate(merged_targets):
        color = PALETTE[(ti + idx_offset) % len(PALETTE)]

        cfg_pts = []
        for i, key in enumerate(dim_keys):
            v = t["scores"][key]["config"]
            x, y = _polar_point(cx, cy, radius, v, i, n)
            cfg_pts.append(f"{x:.1f},{y:.1f}")
        parts.append(
            f'<polygon points="{" ".join(cfg_pts)}" fill="{color}" '
            f'fill-opacity="0.12" stroke="{color}" stroke-width="2.5" '
            f'class="series" style="--c:{color}"/>')
        for i, key in enumerate(dim_keys):
            v = t["scores"][key]["config"]
            x, y = _polar_point(cx, cy, radius, v, i, n)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}"/>')

        usage_pts = []
        for i, key in enumerate(dim_keys):
            v = t["scores"][key]["usage"]
            if v is None:
                continue
            x, y = _polar_point(cx, cy, radius, v, i, n)
            usage_pts.append(f"{x:.1f},{y:.1f}")
        if len(usage_pts) >= 2:
            parts.append(
                f'<polygon points="{" ".join(usage_pts)}" fill="none" '
                f'stroke="{color}" stroke-width="2" stroke-dasharray="6 4" '
                f'stroke-opacity="0.95" class="usage-series"/>')
        for i, key in enumerate(dim_keys):
            v = t["scores"][key]["usage"]
            if v is None:
                continue
            x, y = _polar_point(cx, cy, radius, v, i, n)
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="none" '
                f'stroke="{color}" stroke-width="1.6"/>')

    parts.append('</svg>')
    return "\n".join(parts)


# ----------------------------------------------------------------------------
# Findings accordion
# ----------------------------------------------------------------------------

def _finding_row(f: dict, lang: str) -> str:
    weight = f.get("weight") or 0
    score = f.get("score") or 0
    ratio = (score / weight) if weight else 0
    state = "good" if ratio >= 0.66 else ("mid" if ratio >= 0.33 else "low")
    return f"""
      <div class="finding {state}">
        <div class="f-head">
          <span class="f-label">{_finding_label(f, lang)}</span>
          <span class="f-score">{score:.0f}/{weight:.0f}</span>
        </div>
        <div class="f-bar"><i style="width:{ratio*100:.0f}%"></i></div>
        <div class="f-detail">{_finding_detail(f, lang)}</div>
      </div>"""


def findings_html(target, dim_labels, lang):
    """Single-track (scan-only) findings accordion."""
    by_dim = {}
    for f in target["findings"]:
        by_dim.setdefault(f["dimension"], []).append(f)

    blocks = []
    for dim, score in target["scores"].items():
        rows = "".join(_finding_row(f, lang) for f in by_dim.get(dim, []))
        tone = "good" if score >= 60 else ("mid" if score >= 30 else "low")
        blocks.append(f"""
          <details class="dim-block">
            <summary>
              <span class="d-name">{dim_labels[dim]}</span>
              <span class="d-score {tone}">{score:.0f}</span>
            </summary>
            <div class="findings">{rows}</div>
          </details>""")
    return "".join(blocks)


def _gap_pill(gap):
    """Color the gap by direction + magnitude.

    Positive gap = configured exceeds activated = UNDERUSED:
      ≤15  → good (basically aligned), ≤35 → mid (attention), >35 → low (action)
    Negative gap = activated exceeds configured = OVER-ACTIVATED (a win signal):
      always shown as ``good`` regardless of magnitude.
    """
    if gap is None:
        return '<span class="pill mid">—</span>'
    if gap <= 0:
        # over-activated: positive signal, always good-toned
        return f'<span class="pill good">{gap:.0f}</span>'
    cls = "good" if gap <= 15 else ("mid" if gap <= 35 else "low")
    return f'<span class="pill {cls}">+{gap:.0f}</span>'


def _score_pill(value):
    if value is None:
        return '<span class="pill mid">N/A</span>'
    cls = "good" if value >= 60 else ("mid" if value >= 30 else "low")
    return f'<span class="pill {cls}">{value:.0f}</span>'


def gap_table_html(target, dim_labels, lang="en"):
    rows = []
    for dim, scores in target["scores"].items():
        rows.append(f"""
          <tr>
            <td>{dim_labels.get(dim, dim)}</td>
            <td>{_score_pill(scores['config'])}</td>
            <td>{_score_pill(scores['usage'])}</td>
            <td>{_gap_pill(scores['gap'])}</td>
          </tr>""")
    return f"""
      <table class="gap-table">
        <thead><tr><th>{_t(lang,"th_dim")}</th><th>{_t(lang,"th_config")}</th><th>{_t(lang,"th_usage")}</th><th>{_t(lang,"th_gap")}</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>"""


def top_gaps_html(merged_targets, lang="en"):
    """Render top gaps with click-to-expand drill-down of underlying findings."""
    flat = []
    for t in merged_targets:
        for g in t.get("top_gaps", []):
            flat.append({**g, "target": t["name"]})
    # cross-target sort by |gap| (each target's top_gaps is already abs-sorted)
    flat.sort(key=lambda r: r.get("abs_gap", abs(r["gap"])), reverse=True)
    top = flat[:5]
    if not top:
        return ""

    def _one(i: int, g: dict) -> str:
        direction = g.get("direction", "under" if g["gap"] > 0 else "over")
        gap_sign = f"+{g['gap']:.0f}" if g["gap"] > 0 else f"{g['gap']:.0f}"
        usage_str = (f"{g['usage']:.0f}" if g["usage"] is not None else "N/A")
        cfg_rows = "".join(_finding_row(f, lang) for f in g.get("config_findings", []))
        use_rows = "".join(_finding_row(f, lang) for f in g.get("usage_findings", []))
        return f"""
          <details class="gap-item gap-dir-{direction}">
            <summary>
              <div class="gap-rank">{i+1}</div>
              <div class="gap-summary-body">
                <div class="gap-headline">
                  <span class="gap-tag gap-tag-{direction}">{_t(lang, f'direction_{direction}')}</span>
                  <span class="gap-axis-name">{g['dimension']}</span>
                  <span class="gap-target">{g['target']}</span>
                </div>
                <div class="gap-hint">{_hint_text(g, lang)}</div>
                <div class="gap-meta">
                  <span>{_t(lang,"gap_meta_config")}<b>{g['config']:.0f}</b></span>
                  <span>{_t(lang,"gap_meta_usage")}<b>{usage_str}</b></span>
                  <span>{_t(lang,"gap_meta_gap")}<b>{gap_sign}</b></span>
                </div>
              </div>
              <div class="gap-expand-icon" aria-label="{_t(lang,'expand_hint')}">▾</div>
            </summary>
            <div class="dual-findings">
              <div class="col">
                <div class="col-head">{_t(lang,"col_config")}</div>
                {cfg_rows or f'<div class="f-detail">{_t(lang,"no_findings")}</div>'}
              </div>
              <div class="col">
                <div class="col-head">{_t(lang,"col_usage")}</div>
                {use_rows or f'<div class="f-detail">{_t(lang,"no_usage_signals")}</div>'}
              </div>
            </div>
          </details>"""

    rows = "".join(_one(i, g) for i, g in enumerate(top))
    return f"""
      <section class="card">
        <h2>{_t(lang,"h2_top_gaps")}</h2>
        <p class="card-sub">{_t(lang,"card_sub_top_gaps")}</p>
        <div class="gap-list">{rows}</div>
      </section>"""


def merged_findings_html(target, dim_labels, lang="en"):
    cfg_by = target.get("config_findings_by_dim", {})
    use_by = target.get("usage_findings_by_dim", {})
    blocks = []
    for dim, scores in target["scores"].items():
        cfg_rows = "".join(_finding_row(f, lang) for f in cfg_by.get(dim, []))
        use_rows = "".join(_finding_row(f, lang) for f in use_by.get(dim, []))
        tone_cfg = "good" if scores["config"] >= 60 else ("mid" if scores["config"] >= 30 else "low")
        usage_label = (f'{scores["usage"]:.0f}' if scores["usage"] is not None else "N/A")
        tone_use = "good" if (scores["usage"] or 0) >= 60 else ("mid" if (scores["usage"] or 0) >= 30 else "low")
        if scores["usage"] is None:
            tone_use = "mid"
        gap_label = _gap_pill(scores["gap"])
        blocks.append(f"""
          <details class="dim-block">
            <summary>
              <span class="d-name">{dim_labels.get(dim, dim)}</span>
              <span class="d-dual">
                <span class="d-score {tone_cfg}">{scores['config']:.0f}</span>
                <span class="d-sep">/</span>
                <span class="d-score {tone_use}">{usage_label}</span>
                <span class="d-gap">{gap_label}</span>
              </span>
            </summary>
            <div class="dual-findings">
              <div class="col">
                <div class="col-head">{_t(lang,"col_config")}</div>
                {cfg_rows or f'<div class="f-detail">{_t(lang,"no_findings")}</div>'}
              </div>
              <div class="col">
                <div class="col-head">{_t(lang,"col_usage")}</div>
                {use_rows or f'<div class="f-detail">{_t(lang,"no_usage_signals")}</div>'}
              </div>
            </div>
          </details>""")
    return "".join(blocks)


# ----------------------------------------------------------------------------
# Top-level HTML builders
# ----------------------------------------------------------------------------

def build_html(data, lang="en"):
    """Scan-only report — configured coverage (no activation data)."""
    dim_keys = _normalise_dimensions(data["dimensions"])
    dim_labels = i18n_mod.dimensions_for(dim_keys, lang)
    targets = data["targets"]

    if not targets:
        return f"<html><body>{_t(lang,'no_targets')}</body></html>"

    radar = radar_svg(targets, dim_keys, dim_labels)

    legend = "".join(
        f'<span class="leg"><i style="background:{PALETTE[i%len(PALETTE)]}"></i>'
        f'{t["name"]} <b>{t["overall"]:.0f}</b></span>'
        for i, t in enumerate(targets))

    details = "".join(f"""
      <section class="card target">
        <div class="target-head">
          <div>
            <h3>{t['name']}</h3>
            <code class="path">{t['path']}</code>
          </div>
          <div class="big-score {('good' if t['overall']>=60 else 'mid' if t['overall']>=30 else 'low')}">
            <span class="num">{t['overall']:.0f}</span>
          </div>
        </div>
        {findings_html(t, dim_labels, lang)}
        {"".join(f'<p class="blind"><span>{_t(lang,"blind_label")}</span>{_blind_text(b, lang)}</p>' for b in t.get('blind_spots', []))}
      </section>""" for t in targets)

    return _scaffold_html(
        lang=lang,
        title=_t(lang, "title_scan"),
        body=f"""
  <div class="wrap">
    <header class="masthead">
      <div class="kicker">{_t(lang,"kicker_scan")}</div>
      <h1>{_t(lang,"h1_scan_pre")}<span class="em">{_t(lang,"h1_scan_em")}</span>{_t(lang,"h1_scan_post")}</h1>
      <p class="sub">{_t(lang,"sub_scan")}</p>
    </header>

    <section class="card">
      <h2>{_t(lang,"h2_configured")}</h2>
      <div class="radar-wrap">
        {radar}
        <div class="legend">{legend}</div>
      </div>
      <p class="pair-hint">{_t(lang,"pair_hint")}</p>
    </section>

    {details}

    <footer>{_t(lang,"footer_scan")}</footer>
  </div>""",
        extra_css="")


def build_merged_html(merged, lang="en"):
    """Activation Gap view — dual-track radar of configured vs activated."""
    dim_keys = _normalise_dimensions(merged["dimensions"])
    dim_labels = i18n_mod.dimensions_for(dim_keys, lang)
    targets = merged["targets"]

    if not targets:
        return f"<html><body>{_t(lang,'no_targets')}</body></html>"

    radar = dual_radar_svg(targets, dim_keys, dim_labels)

    def _legend_item(i: int, t: dict) -> str:
        usage_overall = t.get("usage_overall")
        usage_str = f"{usage_overall:.0f}" if usage_overall is not None else "N/A"
        return (
            f'<span class="leg"><i style="background:{PALETTE[i%len(PALETTE)]}"></i>'
            f'{t["name"]} '
            f'<b>{(t["config_overall"] or 0):.0f}</b>'
            f'<span class="sub">→ {usage_str}</span>'
            f'</span>'
        )

    legend = "".join(_legend_item(i, t) for i, t in enumerate(targets))

    dual_legend = (
        '<div class="dual-legend">'
        f'<span class="swatch"><span class="sw-line"></span>{_t(lang,"dual_legend_cfg")}</span>'
        f'<span class="swatch"><span class="sw-line dashed"></span>{_t(lang,"dual_legend_use")}</span>'
        '</div>')

    target_sections = "".join(f"""
      <section class="card target">
        <div class="target-head">
          <div>
            <h3>{t['name']}</h3>
            <code class="path">{t['path']}</code>
          </div>
          <div class="big-score {('good' if (t['config_overall'] or 0)>=60 else 'mid' if (t['config_overall'] or 0)>=30 else 'low')}">
            <span class="num">{(t['config_overall'] or 0):.0f}</span>
          </div>
        </div>
        {gap_table_html(t, dim_labels, lang=lang)}
        <div style="margin-top: 18px;">{merged_findings_html(t, dim_labels, lang=lang)}</div>
        {"".join(f'<p class="blind"><span>{_t(lang,"blind_label")}</span>{_blind_text(b, lang)}</p>' for b in t.get('blind_spots', []))}
        {"".join(f'<p class="blind"><span>{_t(lang,"note_label")}</span>{n}</p>' for n in t.get('notes', []))}
      </section>""" for t in targets)

    body = f"""
  <div class="wrap">
    <header class="masthead">
      <div class="kicker">{_t(lang,"kicker_merged")}</div>
      <h1>{_t(lang,"h1_merged_pre")}<span class="em">{_t(lang,"h1_merged_em")}</span>{_t(lang,"h1_merged_post")}</h1>
      <p class="sub">{_t(lang,"sub_merged")}</p>
    </header>

    <section class="card">
      <h2>{_t(lang,"h2_dual")}</h2>
      <div class="radar-wrap">
        {radar}
        <div class="legend">{legend}</div>
      </div>
      {dual_legend}
    </section>

    {top_gaps_html(targets, lang=lang)}

    <h2 style="margin: 32px 0 16px;">{_t(lang,"h2_targets")}</h2>
    {target_sections}

    <footer>{_t(lang,"footer_merged")}</footer>
  </div>"""

    return _scaffold_html(lang=lang, title=_t(lang, "title_merged"),
                          body=body, extra_css=_MERGED_EXTRA_CSS)


# ----------------------------------------------------------------------------
# CSS scaffolding
# ----------------------------------------------------------------------------

_BASE_CSS = """
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&family=Noto+Sans+TC:wght@400;500;700;900&display=swap');
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0b0f14; --panel: #121821; --panel-2: #0f141b; --line: #1f2a37;
    --ink: #e4ecf4; --ink-dim: #8195a9; --good: #4ade80; --mid: #fbbf24;
    --low: #f87171; --accent: #38bdf8;
  }
  body {
    background:
      radial-gradient(900px 600px at 80% -10%, rgba(56,189,248,.08), transparent),
      radial-gradient(700px 500px at 0% 100%, rgba(74,222,128,.06), transparent),
      var(--bg);
    color: var(--ink); font-family: 'Noto Sans TC', system-ui, sans-serif;
    line-height: 1.6; padding: 48px 20px 80px; min-height: 100vh;
  }
  .wrap { max-width: 1080px; margin: 0 auto; }
  .masthead { margin-bottom: 36px; }
  .kicker { font-family: 'JetBrains Mono', monospace; font-size: 12px;
            letter-spacing: .28em; color: var(--accent); text-transform: uppercase;
            margin-bottom: 12px; }
  h1 { font-size: clamp(28px, 5vw, 46px); font-weight: 900; line-height: 1.1; letter-spacing: -.02em; }
  h1 .em { color: var(--accent); }
  .sub { color: var(--ink-dim); margin-top: 14px; max-width: 64ch; font-size: 15px; }
  .card { background: linear-gradient(180deg, var(--panel), var(--panel-2));
          border: 1px solid var(--line); border-radius: 16px; padding: 28px;
          margin-bottom: 22px; }
  h2 { font-size: 18px; margin-bottom: 18px; display: flex; align-items: center; gap: 10px; }
  h2::before { content: ""; width: 4px; height: 18px; background: var(--accent); border-radius: 2px; }
  .card-sub { color: var(--ink-dim); font-size: 13.5px; max-width: 70ch; margin: -8px 0 18px; }
  .pair-hint { color: var(--ink-dim); font-size: 13px; margin-top: 18px;
               padding: 10px 14px; background: rgba(56,189,248,.06);
               border-left: 3px solid var(--accent); border-radius: 0 8px 8px 0; }
  .radar-wrap { display: grid; grid-template-columns: 1.1fr .9fr; gap: 24px; align-items: center; }
  @media (max-width: 760px) { .radar-wrap { grid-template-columns: 1fr; } }
  .radar { width: 100%; height: auto; }
  .grid-ring { fill: none; stroke: var(--line); stroke-width: 1; }
  .axis { stroke: var(--line); stroke-width: 1; }
  .axis-label { fill: var(--ink-dim); font-size: 12.5px; font-family: 'Noto Sans TC'; font-weight: 500; }
  .series { filter: drop-shadow(0 0 8px color-mix(in srgb, var(--c) 40%, transparent)); }
  .legend { display: flex; flex-direction: column; gap: 10px; }
  .leg { display: flex; align-items: center; gap: 10px; font-size: 14px; color: var(--ink-dim); }
  .leg i { width: 14px; height: 14px; border-radius: 4px; display: inline-block; }
  .leg b { margin-left: auto; color: var(--ink); font-family: 'JetBrains Mono'; }
  .pill { font-family: 'JetBrains Mono'; font-weight: 700; padding: 3px 10px; border-radius: 999px; font-size: 13px; }
  .pill.good { background: rgba(74,222,128,.15); color: var(--good); }
  .pill.mid { background: rgba(251,191,36,.15); color: var(--mid); }
  .pill.low { background: rgba(248,113,113,.15); color: var(--low); }
  .target-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
                 margin-bottom: 20px; padding-bottom: 18px; border-bottom: 1px solid var(--line); }
  .target-head h3 { font-size: 20px; }
  .path { font-family: 'JetBrains Mono'; font-size: 11.5px; color: var(--ink-dim); word-break: break-all; }
  .big-score { text-align: right; min-width: 110px; }
  .big-score .num { font-family: 'JetBrains Mono'; font-weight: 800; font-size: 40px; line-height: 1; display: block; }
  .big-score.good .num { color: var(--good); }
  .big-score.mid .num { color: var(--mid); }
  .big-score.low .num { color: var(--low); }
  .dim-block { border: 1px solid var(--line); border-radius: 12px; margin-bottom: 10px; overflow: hidden; }
  .dim-block summary { list-style: none; cursor: pointer; display: flex; justify-content: space-between;
                       align-items: center; padding: 14px 18px; background: var(--panel-2); }
  .dim-block summary::-webkit-details-marker { display: none; }
  .dim-block summary:hover { background: #141b25; }
  .d-name { font-weight: 700; font-size: 15px; }
  .d-score { font-family: 'JetBrains Mono'; font-weight: 800; font-size: 18px; }
  .d-score.good { color: var(--good); } .d-score.mid { color: var(--mid); } .d-score.low { color: var(--low); }
  .findings { padding: 8px 18px 16px; }
  .finding { padding: 12px 0; border-bottom: 1px dashed var(--line); }
  .finding:last-child { border-bottom: none; }
  .f-head { display: flex; justify-content: space-between; font-size: 14px; }
  .f-label { font-weight: 500; }
  .f-score { font-family: 'JetBrains Mono'; color: var(--ink-dim); font-size: 12px; }
  .f-bar { height: 5px; background: var(--line); border-radius: 3px; margin: 7px 0; overflow: hidden; }
  .f-bar i { display: block; height: 100%; border-radius: 3px; }
  .finding.good .f-bar i { background: var(--good); }
  .finding.mid .f-bar i { background: var(--mid); }
  .finding.low .f-bar i { background: var(--low); }
  .f-detail { font-size: 12.5px; color: var(--ink-dim); }
  .blind { margin-top: 16px; font-size: 13px; color: var(--ink-dim); background: rgba(56,189,248,.06);
           border-left: 3px solid var(--accent); padding: 10px 14px; border-radius: 0 8px 8px 0; }
  .blind span { font-family: 'JetBrains Mono'; color: var(--accent); font-weight: 700; margin-right: 8px;
                text-transform: uppercase; font-size: 11px; letter-spacing: .1em; }
  footer { text-align: center; color: var(--ink-dim); font-size: 12px; margin-top: 40px;
           font-family: 'JetBrains Mono'; }
"""


_MERGED_EXTRA_CSS = """
  .usage-series { stroke-linejoin: round; stroke-linecap: round; }
  .legend .leg .sub { font-size: 11px; color: var(--ink-dim); margin-left: 8px; }
  .gap-table { width: 100%; border-collapse: collapse; margin-top: 18px; }
  .gap-table th { text-align: left; font-size: 12px; color: var(--ink-dim);
                  font-weight: 500; padding: 8px 10px;
                  border-bottom: 1px solid var(--line); }
  .gap-table td { padding: 10px; border-bottom: 1px solid var(--line); font-size: 14px; }
  .d-dual { display: inline-flex; align-items: center; gap: 10px; }
  .d-sep  { color: var(--ink-dim); font-family: 'JetBrains Mono'; }
  .d-gap  { margin-left: 6px; }
  .dual-findings { display: grid; grid-template-columns: 1fr 1fr; gap: 18px;
                   padding: 8px 18px 16px; }
  @media (max-width: 760px) { .dual-findings { grid-template-columns: 1fr; } }
  .col-head { font-family: 'JetBrains Mono'; font-size: 11px; color: var(--accent);
              letter-spacing: .15em; text-transform: uppercase; padding: 8px 0;
              border-bottom: 1px solid var(--line); margin-bottom: 6px; }
  .gap-list { padding: 0; margin: 8px 0 0; }
  .gap-item { border: 1px solid var(--line); border-radius: 12px;
              margin-bottom: 10px; overflow: hidden; background: var(--panel-2); }
  .gap-item summary { list-style: none; cursor: pointer; display: flex;
                      gap: 16px; padding: 14px 18px; align-items: flex-start; }
  .gap-item summary::-webkit-details-marker { display: none; }
  .gap-item summary:hover { background: #141b25; }
  .gap-item[open] summary { border-bottom: 1px solid var(--line); }
  .gap-item[open] .gap-expand-icon { transform: rotate(180deg); }
  .gap-rank { font-family: 'JetBrains Mono'; font-weight: 800; font-size: 22px;
              color: var(--accent); min-width: 28px; line-height: 1.4; }
  .gap-summary-body { flex: 1; min-width: 0; }
  .gap-headline { display: flex; gap: 10px; align-items: center; margin-bottom: 4px;
                  flex-wrap: wrap; }
  .gap-tag { font-family: 'JetBrains Mono'; font-size: 10px; font-weight: 700;
             padding: 2px 8px; border-radius: 999px; letter-spacing: .1em; }
  .gap-tag-under { background: rgba(248,113,113,.18); color: var(--low); }
  .gap-tag-over  { background: rgba(74,222,128,.18); color: var(--good); }
  .gap-axis-name { font-family: 'JetBrains Mono'; font-size: 12px;
                   color: var(--ink-dim); }
  .gap-target { color: var(--ink); font-weight: 500; font-size: 13px;
                margin-left: auto; }
  .gap-hint { font-size: 14.5px; line-height: 1.55; }
  .gap-meta { margin-top: 6px; color: var(--ink-dim); font-size: 12px;
              display: flex; gap: 12px; flex-wrap: wrap; }
  .gap-meta b { color: var(--ink); font-family: 'JetBrains Mono'; }
  .gap-expand-icon { color: var(--ink-dim); font-size: 16px; margin-left: 8px;
                     transition: transform .15s ease; line-height: 1.4; }
  .gap-item .dual-findings { padding: 14px 18px 16px; }
  .dual-legend { display: flex; gap: 22px; flex-wrap: wrap; align-items: center;
                 padding: 12px 14px; background: var(--panel-2);
                 border: 1px solid var(--line); border-radius: 10px;
                 margin-top: 14px; font-size: 13px; color: var(--ink-dim); }
  .dual-legend .swatch { display: inline-flex; align-items: center; gap: 8px; }
  .dual-legend .sw-line { display: inline-block; width: 26px; height: 0;
                          border-top: 2.5px solid var(--ink); }
  .dual-legend .sw-line.dashed { border-top-style: dashed; border-top-width: 2px; }
"""


def _scaffold_html(lang: str, title: str, body: str, extra_css: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="{_t(lang,"html_lang")}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_BASE_CSS}{extra_css}</style>
</head>
<body>{body}
</body>
</html>"""


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def _prompt_lang():
    import sys
    if not sys.stdin.isatty():
        return "en"
    print("Choose report language / 請選擇報告語言:")
    print("  [1] English (default)")
    print("  [2] 繁體中文")
    try:
        choice = input("Select (1/2): ").strip()
    except EOFError:
        return "en"
    return "zh" if choice == "2" else "en"


def main():
    ap = argparse.ArgumentParser(
        description="agent-radar HTML report renderer (0.2.0)")
    ap.add_argument("input", nargs="?", default=None,
                    help="scan.json from `agent-radar scan` (configured-coverage mode)")
    ap.add_argument("--session", default=None,
                    help="session.json from `agent-radar session` "
                         "— merges inline with scan to produce the activation-gap view")
    ap.add_argument("--merged", default=None,
                    help="merged.json from `agent-radar merge` "
                         "— activation-gap view direct")
    ap.add_argument("--lang", choices=["en", "zh"], default=None,
                    help="Report language (en|zh). Prompts at TTY if omitted; en otherwise.")
    ap.add_argument("-o", "--output", default="report.html")
    args = ap.parse_args()

    lang = args.lang if args.lang else _prompt_lang()

    if args.merged:
        merged = json.loads(Path(args.merged).read_text(encoding="utf-8"))
        html = build_merged_html(merged, lang=lang)
    else:
        if not args.input:
            ap.error("input scan.json is required (or use --merged)")
        scan_data = json.loads(Path(args.input).read_text(encoding="utf-8"))
        # File names don't disambiguate scan.json vs merged.json, but the
        # shapes do: scan.json has flat numeric scores, merged.json has
        # {"config","usage","gap"} dicts. Catch the mismatch up front so
        # users get an actionable message instead of a TypeError from
        # deep inside radar_svg.
        if _looks_like_merged(scan_data):
            sys.stderr.write(
                f"error: {args.input} looks like a merged.json (each axis "
                "score is a dict, not a number). Pass it via --merged:\n"
                f"  agent-radar report --merged {args.input} "
                f"-o {args.output}\n"
            )
            return 2
        if args.session:
            session_data = json.loads(Path(args.session).read_text(encoding="utf-8"))
            merged = _inline_merge(scan_data, session_data)
            html = build_merged_html(merged, lang=lang)
        else:
            html = build_html(scan_data, lang=lang)

    Path(args.output).write_text(html, encoding="utf-8")
    print(f"[ok] report generated ({lang}): {args.output}")


if __name__ == "__main__":
    main()
