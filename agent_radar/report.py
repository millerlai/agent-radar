#!/usr/bin/env python3
"""
agent-radar :: agent_radar.report
=================================
讀取 ``agent-radar scan`` 產出的 JSON，生成單檔 HTML 雷達圖診斷報告。

JSON 採 i18n key 形式 (label_key / detail_key / detail_args / blind_spot key …);
本檔透過 ``agent_radar.i18n`` 依 ``--lang`` 把它們渲染成顯示文字。

用法:
  agent-radar scan <paths...> -o scan.json
  agent-radar report scan.json -o report.html
"""

import argparse
import json
import math
from pathlib import Path

from . import i18n as i18n_mod


# 色票：暗色「診斷儀表板」風
PALETTE = ["#4ade80", "#38bdf8", "#fbbf24", "#f472b6", "#a78bfa", "#fb923c", "#2dd4bf", "#f87171"]


# ----------------------------------------------------------------------------
# i18n: UI chrome strings only (finding/dimension/level strings live in i18n.py)
# ----------------------------------------------------------------------------

STRINGS = {
    "en": {
        "html_lang": "en",
        "title_scan": "AI Agent Capability Boundary Diagnostic",
        "title_merged": "AI Agent Capability Boundary · Config vs Usage",
        "kicker_scan": "agent-radar · capability boundary scan",
        "kicker_merged": "agent-radar · config vs usage",
        "h1_scan_pre": "AI Agent ",
        "h1_scan_em": "Capability Boundary",
        "h1_scan_post": " Diagnostic Report",
        "h1_merged_pre": "Capability ",
        "h1_merged_em": "Config vs Usage",
        "h1_merged_post": " Gap Diagnostic",
        "sub_scan": ("Quantifies the Claude Code ecosystem's \"configuration maturity\" by "
                     "scanning filesystem fingerprints (CLAUDE.md, skills, MCP, hooks, "
                     "subagents, git history). Scores reflect setup completeness, not actual usage."),
        "sub_merged": ("Overlays scanner's \"static configuration\" with OTel events' \"actual "
                       "usage\" on the same axes. The area between solid and dashed lines is "
                       "the capability-waste zone — what you configured but never used."),
        "h2_maturity": "Maturity Radar",
        "h2_team": "Team Benchmark",
        "h2_usage": "Actual Usage Radar",
        "h2_dual": "Dual-Track Radar · Config × Usage",
        "h2_top_gaps": "Top Gaps",
        "card_sub_usage": ("Reads local ~/.claude/projects/ JSONL logs and quantifies tool "
                          "calls, Skill triggers, MCP calls, and user-correction rate within "
                          "sessions. The gap from the configuration radar above is your "
                          "improvement headroom."),
        "card_sub_top_gaps": ("Top 5 items sorted by config vs usage gap. Large gap = configured "
                              "but unused — the cheapest capability wins."),
        "th_num": "#",
        "th_target": "Target",
        "th_overall": "Overall",
        "th_level": "Level",
        "th_dim": "Dimension",
        "th_config": "Config",
        "th_usage": "Usage",
        "th_gap": "Gap",
        "team_avg_pre": "Team average maturity ",
        "team_avg_post": " / 100",
        "blind_label": "BLIND SPOT",
        "note_label": "NOTE",
        "col_config": "CONFIG",
        "col_usage": "USAGE",
        "no_findings": "No findings",
        "no_usage_signals": "No usage signals",
        "footer_scan": "agent-radar · static fingerprint scan · configuration completeness ≠ actual usage",
        "footer_merged": "agent-radar · static fingerprint + OTel telemetry · config ≠ usage",
        "dual_legend_cfg": "Config (static fingerprint)",
        "dual_legend_use": "Usage (OTel events)",
        "dual_legend_na": "iteration dim · USAGE = N/A (no corresponding signal)",
        "gap_meta_config": "· config ",
        "gap_meta_usage": "· usage ",
        "gap_meta_gap": "· gap ",
        "no_targets": "No targets scanned.",
    },
    "zh": {
        "html_lang": "zh-Hant",
        "title_scan": "AI Agent 能力邊界診斷",
        "title_merged": "AI Agent 能力邊界診斷 · 配置 vs 運用",
        "kicker_scan": "agent-radar · capability boundary scan",
        "kicker_merged": "agent-radar · config vs usage",
        "h1_scan_pre": "AI Agent ",
        "h1_scan_em": "能力邊界",
        "h1_scan_post": "診斷報告",
        "h1_merged_pre": "能力",
        "h1_merged_em": "配置 vs 運用",
        "h1_merged_post": "落差診斷",
        "sub_scan": ("透過掃描檔案系統指紋 (CLAUDE.md · skills · MCP · hooks · subagents · "
                     "git history),量化 Claude Code 生態的「配置成熟度」。分數反映設定完整度,"
                     "非實際運用度。"),
        "sub_merged": ("把 scanner 的「靜態配置」與 OTel events 的「實際運用」疊在同一組軸上。"
                       "實線與虛線之間的面積就是能力浪費區 — 你配了但沒在用的部分。"),
        "h2_maturity": "成熟度雷達 · Maturity Radar",
        "h2_team": "團隊排行 · Team Benchmark",
        "h2_usage": "運用度雷達 · Actual Usage",
        "h2_dual": "雙軌雷達 · Config × Usage",
        "h2_top_gaps": "改善清單 · Top Gaps",
        "card_sub_usage": ("讀取本機 ~/.claude/projects/ JSONL,量化 session 內真正發生的工具呼叫、"
                          "Skill 觸發、MCP 呼叫、使用者糾正率。與上方配置雷達的「落差」即為改善空間。"),
        "card_sub_top_gaps": ("依「配置 vs 運用」落差排序的前 5 項。落差大 = 你配了但沒在用,"
                              "最有機會用最少力氣補上的能力。"),
        "th_num": "#",
        "th_target": "目標",
        "th_overall": "總分",
        "th_level": "層級",
        "th_dim": "維度",
        "th_config": "配置",
        "th_usage": "運用",
        "th_gap": "落差",
        "team_avg_pre": "團隊平均成熟度 ",
        "team_avg_post": " / 100",
        "blind_label": "盲區",
        "note_label": "NOTE",
        "col_config": "配置 · CONFIG",
        "col_usage": "運用 · USAGE",
        "no_findings": "無 findings",
        "no_usage_signals": "無 usage 訊號",
        "footer_scan": "agent-radar · static fingerprint scan · 配置完整度 ≠ 實際運用度",
        "footer_merged": "agent-radar · static fingerprint + OTel telemetry · 配置 ≠ 運用",
        "dual_legend_cfg": "配置 · CONFIG (static fingerprint)",
        "dual_legend_use": "運用 · USAGE (OTel events)",
        "dual_legend_na": "iteration 維度 · USAGE = N/A (無對應訊號)",
        "gap_meta_config": "· 配置 ",
        "gap_meta_usage": "· 運用 ",
        "gap_meta_gap": "· 落差 ",
        "no_targets": "未掃描任何目標。",
    },
}


def _t(lang, key):
    """查表;查不到就 fallback 到 en。"""
    return STRINGS.get(lang, STRINGS["en"]).get(key, STRINGS["en"].get(key, key))


# ----------------------------------------------------------------------------
# Per-finding render helpers (drive everything through agent_radar.i18n).
# ----------------------------------------------------------------------------

def _finding_label(f: dict, lang: str) -> str:
    return i18n_mod.t_label(f.get("label_key", ""), lang)


def _finding_detail(f: dict, lang: str) -> str:
    return i18n_mod.t_detail(f.get("detail_key"), f.get("detail_args"), lang)


def _blind_text(b, lang: str) -> str:
    """blind_spots may be {"key", "args"} dicts (i18n keys) or legacy strings."""
    if isinstance(b, dict):
        return i18n_mod.t_blind(b.get("key", ""), b.get("args"), lang)
    return str(b)


def _hint_text(g: dict, lang: str) -> str:
    return i18n_mod.t_hint(g.get("hint_key", "gap.generic"),
                           g.get("hint_args"), lang)


def _level_label(threshold: int, lang: str) -> str:
    for th, entry in i18n_mod.LEVELS:
        if th == threshold:
            return entry.get(lang, entry["en"])
    return ""


def _normalise_dimensions(value) -> list[str]:
    """Accepts either the new list-of-keys or the legacy {key: label} dict."""
    if isinstance(value, dict):
        return list(value.keys())
    return list(value or [])


# ----------------------------------------------------------------------------
# SVG / table helpers
# ----------------------------------------------------------------------------

def _polar_point(cx, cy, radius, value, i, n):
    ang = -math.pi / 2 + (2 * math.pi * i / n)
    r = radius * (value / 100)
    return cx + r * math.cos(ang), cy + r * math.sin(ang)


def radar_svg(targets, dim_keys, dim_labels, size=460, idx_offset=0):
    """產生多目標疊圖的雷達圖 SVG。

    viewBox 在 size 之外左右各加 pad 像素,給軸標籤水平延伸空間,
    避免中文標籤被截掉。雷達主體位置由 cx/cy 平移補償。
    """
    # 100 才容得下 "Iteration & Maintenance" / "Skill triggers (actual)" 這類 ~23 字標籤
    pad = 100
    vb = size + pad * 2
    cx = cy = size / 2 + pad
    radius = size * 0.34
    n = len(dim_keys)
    rings = 4

    def point(value, i):
        ang = -math.pi / 2 + (2 * math.pi * i / n)
        r = radius * (value / 100)
        return cx + r * math.cos(ang), cy + r * math.sin(ang)

    parts = [f'<svg viewBox="0 0 {vb} {vb}" xmlns="http://www.w3.org/2000/svg" '
             f'role="img" class="radar">']

    # 同心格線
    for ring in range(1, rings + 1):
        rr = radius * ring / rings
        pts = []
        for i in range(n):
            ang = -math.pi / 2 + (2 * math.pi * i / n)
            pts.append(f"{cx + rr*math.cos(ang):.1f},{cy + rr*math.sin(ang):.1f}")
        parts.append(f'<polygon points="{" ".join(pts)}" class="grid-ring"/>')

    # 軸線 + 標籤
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

    # 每個目標一層多邊形
    for ti, t in enumerate(targets):
        color = PALETTE[(ti + idx_offset) % len(PALETTE)]
        pts = []
        for i, key in enumerate(dim_keys):
            x, y = point(t["scores"].get(key, 0), i)
            pts.append(f"{x:.1f},{y:.1f}")
        parts.append(
            f'<polygon points="{" ".join(pts)}" fill="{color}" '
            f'fill-opacity="0.12" stroke="{color}" stroke-width="2.5" '
            f'class="series" style="--c:{color}"/>')
        for i, key in enumerate(dim_keys):
            x, y = point(t["scores"].get(key, 0), i)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}"/>')

    parts.append('</svg>')
    return "\n".join(parts)


def findings_html(target, dim_labels, lang):
    """單一目標的維度明細手風琴。"""
    by_dim = {}
    for f in target["findings"]:
        by_dim.setdefault(f["dimension"], []).append(f)

    blocks = []
    for dim, score in target["scores"].items():
        rows = []
        for f in by_dim.get(dim, []):
            ratio = (f["score"] / f["weight"]) if f["weight"] else 0
            state = "good" if ratio >= 0.66 else ("mid" if ratio >= 0.33 else "low")
            rows.append(f"""
              <div class="finding {state}">
                <div class="f-head">
                  <span class="f-label">{_finding_label(f, lang)}</span>
                  <span class="f-score">{f['score']:.0f}/{f['weight']:.0f}</span>
                </div>
                <div class="f-bar"><i style="width:{ratio*100:.0f}%"></i></div>
                <div class="f-detail">{_finding_detail(f, lang)}</div>
              </div>""")
        tone = "good" if score >= 60 else ("mid" if score >= 30 else "low")
        blocks.append(f"""
          <details class="dim-block">
            <summary>
              <span class="d-name">{dim_labels[dim]}</span>
              <span class="d-score {tone}">{score:.0f}</span>
            </summary>
            <div class="findings">{''.join(rows)}</div>
          </details>""")
    return "".join(blocks)


def build_usage_section(session_data, lang="en"):
    """生成「實際運用度」雷達卡 (來自 agent-radar session 輸出)。"""
    if not session_data:
        return ""
    dim_keys = _normalise_dimensions(session_data.get("usage_dimensions", {}))
    targets = session_data.get("targets", [])
    if not targets or not dim_keys:
        return ""

    dim_labels = i18n_mod.dimensions_for(dim_keys, lang)
    radar = radar_svg(targets, dim_keys, dim_labels, idx_offset=3)

    legend = "".join(
        f'<span class="leg"><i style="background:{PALETTE[(i+3)%len(PALETTE)]}"></i>'
        f'{t["name"]} <b>{t["overall"]:.0f}</b></span>'
        for i, t in enumerate(targets))

    blind = "".join(
        f'<p class="blind"><span>{_t(lang,"blind_label")}</span>{_blind_text(b, lang)}</p>'
        for b in session_data.get("blind_spots", []))

    # 個別 target 的明細
    rows = []
    for t in targets:
        finding_rows = []
        for f in t["findings"]:
            ratio = (f["score"] / f["weight"]) if f["weight"] else 0
            state = "good" if ratio >= 0.66 else ("mid" if ratio >= 0.33 else "low")
            finding_rows.append(f"""
              <div class="finding {state}">
                <div class="f-head">
                  <span class="f-label">{_finding_label(f, lang)}</span>
                  <span class="f-score">{f['score']:.0f}/{f['weight']:.0f}</span>
                </div>
                <div class="f-bar"><i style="width:{ratio*100:.0f}%"></i></div>
                <div class="f-detail">{_finding_detail(f, lang)}</div>
              </div>""")
        rows.append(f"""
          <details class="dim-block">
            <summary>
              <span class="d-name">{t['name']}</span>
              <span class="d-score {('good' if t['overall']>=60 else 'mid' if t['overall']>=30 else 'low')}">{t['overall']:.0f}</span>
            </summary>
            <div class="findings">{''.join(finding_rows)}</div>
          </details>""")

    return f"""
    <section class="card">
      <h2>{_t(lang,"h2_usage")}</h2>
      <p class="card-sub">{_t(lang,"card_sub_usage")}</p>
      <div class="radar-wrap">
        {radar}
        <div class="legend">{legend}</div>
      </div>
      <div style="margin-top: 22px;">{''.join(rows)}</div>
      {blind}
    </section>"""


def build_html(data, session_data=None, lang="en"):
    dim_keys = _normalise_dimensions(data["dimensions"])
    dim_labels = i18n_mod.dimensions_for(dim_keys, lang)
    targets = data["targets"]

    if not targets:
        return f"<html><body>{_t(lang,'no_targets')}</body></html>"

    is_team = len(targets) > 1
    team_avg = {}
    for k in dim_keys:
        vals = [t["scores"].get(k, 0) for t in targets]
        team_avg[k] = round(sum(vals) / len(vals), 1)
    team_overall = round(sum(team_avg.values()) / len(team_avg), 1)

    radar = radar_svg(targets, dim_keys, dim_labels)

    legend = "".join(
        f'<span class="leg"><i style="background:{PALETTE[i%len(PALETTE)]}"></i>'
        f'{t["name"]} <b>{t["overall"]:.0f}</b></span>'
        for i, t in enumerate(targets))

    # --- 排行 (團隊) ---
    ranking = ""
    if is_team:
        ranked = sorted(targets, key=lambda x: x["overall"], reverse=True)
        rows = "".join(
            f"""<tr>
                  <td class="rank">{i+1}</td>
                  <td>{t['name']}</td>
                  <td><span class="pill {('good' if t['overall']>=60 else 'mid' if t['overall']>=30 else 'low')}">{t['overall']:.0f}</span></td>
                  <td class="lvl">{_level_label(t.get('level_threshold', 0), lang)}</td>
                </tr>""" for i, t in enumerate(ranked))
        ranking = f"""
        <section class="card">
          <h2>{_t(lang,"h2_team")}</h2>
          <table class="rank-table">
            <thead><tr><th>{_t(lang,"th_num")}</th><th>{_t(lang,"th_target")}</th><th>{_t(lang,"th_overall")}</th><th>{_t(lang,"th_level")}</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
          <p class="team-avg">{_t(lang,"team_avg_pre")}<b>{team_overall:.0f}</b>{_t(lang,"team_avg_post")}</p>
        </section>"""

    # --- 個別目標明細 ---
    details = "".join(f"""
      <section class="card target">
        <div class="target-head">
          <div>
            <h3>{t['name']}</h3>
            <code class="path">{t['path']}</code>
          </div>
          <div class="big-score {('good' if t['overall']>=60 else 'mid' if t['overall']>=30 else 'low')}">
            <span class="num">{t['overall']:.0f}</span>
            <span class="lvl-tag">{_level_label(t.get('level_threshold', 0), lang)}</span>
          </div>
        </div>
        {findings_html(t, dim_labels, lang)}
        {"".join(f'<p class="blind"><span>{_t(lang,"blind_label")}</span>{_blind_text(b, lang)}</p>' for b in t.get('blind_spots', []))}
      </section>""" for t in targets)

    # --- 層級量尺 ---
    level_thresholds = data.get("level_thresholds")
    if level_thresholds is None:
        level_thresholds = [th for th, _ in i18n_mod.LEVELS]
    level_scale = "".join(
        _level_scale_item(th, lang) for th in level_thresholds)

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
      <h2>{_t(lang,"h2_maturity")}</h2>
      <div class="radar-wrap">
        {radar}
        <div class="legend">{legend}</div>
      </div>
      <div class="scale">{level_scale}</div>
    </section>

    {ranking}

    {build_usage_section(session_data, lang=lang)}

    {details}

    <footer>{_t(lang,"footer_scan")}</footer>
  </div>""",
        extra_css="")


def _level_scale_item(threshold: int, lang: str) -> str:
    """Render one level chip in the maturity scale strip."""
    label = _level_label(threshold, lang)
    head = label.split("·")[0].strip() if "·" in label else label
    tail = label.split("·")[1].strip() if "·" in label else ""
    return (f'<div class="lv"><b>{head}</b><span>{tail}</span>'
            f'<i>{threshold}+</i></div>')


def dual_radar_svg(merged_targets, dim_keys, dim_labels, size=460, idx_offset=0):
    """雙軌雷達:每個 target 同時畫實線 (config) + 虛線 (usage)。

    iteration 維度的 usage 為 None,usage polygon 以開口形式繞過 iteration
    軸,避免假裝 0 分。
    """
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

    iteration_idx = None
    for i, key in enumerate(dim_keys):
        if key == "iteration":
            iteration_idx = i
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
            shape_tag = "polygon" if iteration_idx is None else "polyline"
            parts.append(
                f'<{shape_tag} points="{" ".join(usage_pts)}" fill="none" '
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

    if iteration_idx is not None:
        ang = -math.pi / 2 + (2 * math.pi * iteration_idx / n)
        nx = cx + (radius * 0.5) * math.cos(ang)
        ny = cy + (radius * 0.5) * math.sin(ang)
        parts.append(
            f'<text x="{nx:.1f}" y="{ny:.1f}" text-anchor="middle" '
            f'dominant-baseline="middle" class="na-tag">N/A</text>')

    parts.append('</svg>')
    return "\n".join(parts)


def _gap_pill(gap):
    if gap is None:
        return '<span class="pill mid">—</span>'
    cls = "good" if gap <= 15 else ("mid" if gap <= 35 else "low")
    sign = "+" if gap > 0 else ""
    return f'<span class="pill {cls}">{sign}{gap:.0f}</span>'


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
    """整份報告中跨 target 撿出落差最大的前 5 項。"""
    flat = []
    for t in merged_targets:
        for g in t.get("top_gaps", []):
            flat.append({**g, "target": t["name"]})
    flat.sort(key=lambda r: r["gap"], reverse=True)
    top = flat[:5]
    if not top:
        return ""

    rows = "".join(f"""
      <li class="gap-item">
        <div class="gap-rank">{i+1}</div>
        <div class="gap-body">
          <div class="gap-hint">{_hint_text(g, lang)}</div>
          <div class="gap-meta">
            <span>{g['target']}</span>
            <span>{_t(lang,"gap_meta_config")}<b>{g['config']:.0f}</b></span>
            <span>{_t(lang,"gap_meta_usage")}<b>{(f"{g['usage']:.0f}" if g['usage'] is not None else 'N/A')}</b></span>
            <span>{_t(lang,"gap_meta_gap")}<b>{g['gap']:.0f}</b></span>
          </div>
        </div>
      </li>""" for i, g in enumerate(top))

    return f"""
      <section class="card">
        <h2>{_t(lang,"h2_top_gaps")}</h2>
        <p class="card-sub">{_t(lang,"card_sub_top_gaps")}</p>
        <ol class="gap-list">{rows}</ol>
      </section>"""


def merged_findings_html(target, dim_labels, lang="en"):
    """合併視角:每個維度展開後左右並列 config / usage findings。"""
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


# ----- shared HTML scaffolding ---------------------------------------------

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
  .scale { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 22px; }
  .lv { flex: 1; min-width: 110px; background: var(--panel-2); border: 1px solid var(--line);
        border-radius: 10px; padding: 10px 12px; }
  .lv b { display: block; font-family: 'JetBrains Mono'; color: var(--accent); font-size: 13px; }
  .lv span { display: block; font-size: 12px; color: var(--ink-dim); }
  .lv i { font-style: normal; font-size: 11px; color: var(--ink-dim); font-family: 'JetBrains Mono'; }
  .rank-table { width: 100%; border-collapse: collapse; }
  .rank-table th { text-align: left; font-size: 12px; color: var(--ink-dim); font-weight: 500;
                   padding: 8px 10px; border-bottom: 1px solid var(--line); }
  .rank-table td { padding: 12px 10px; border-bottom: 1px solid var(--line); font-size: 14px; }
  .rank-table .rank { font-family: 'JetBrains Mono'; color: var(--ink-dim); width: 36px; }
  .lvl { font-size: 12px; color: var(--ink-dim); }
  .pill { font-family: 'JetBrains Mono'; font-weight: 700; padding: 3px 10px; border-radius: 999px; font-size: 13px; }
  .pill.good { background: rgba(74,222,128,.15); color: var(--good); }
  .pill.mid { background: rgba(251,191,36,.15); color: var(--mid); }
  .pill.low { background: rgba(248,113,113,.15); color: var(--low); }
  .team-avg { margin-top: 16px; color: var(--ink-dim); font-size: 14px; }
  .team-avg b { color: var(--ink); font-family: 'JetBrains Mono'; font-size: 18px; }
  .target-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
                 margin-bottom: 20px; padding-bottom: 18px; border-bottom: 1px solid var(--line); }
  .target-head h3 { font-size: 20px; }
  .path { font-family: 'JetBrains Mono'; font-size: 11.5px; color: var(--ink-dim); word-break: break-all; }
  .big-score { text-align: right; min-width: 110px; }
  .big-score .num { font-family: 'JetBrains Mono'; font-weight: 800; font-size: 40px; line-height: 1; display: block; }
  .big-score.good .num { color: var(--good); }
  .big-score.mid .num { color: var(--mid); }
  .big-score.low .num { color: var(--low); }
  .lvl-tag { font-size: 11px; color: var(--ink-dim); font-family: 'JetBrains Mono'; }
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
  .na-tag { fill: var(--ink-dim); font-family: 'JetBrains Mono'; font-size: 11px;
            letter-spacing: .08em; }
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
  .gap-list { list-style: none; padding: 0; margin: 8px 0 0; }
  .gap-item { display: flex; gap: 16px; padding: 14px 0;
              border-bottom: 1px dashed var(--line); }
  .gap-item:last-child { border-bottom: none; }
  .gap-rank { font-family: 'JetBrains Mono'; font-weight: 800; font-size: 22px;
              color: var(--accent); min-width: 28px; }
  .gap-hint { font-size: 14.5px; line-height: 1.55; }
  .gap-meta { margin-top: 6px; color: var(--ink-dim); font-size: 12px;
              display: flex; gap: 6px; flex-wrap: wrap; }
  .gap-meta b { color: var(--ink); font-family: 'JetBrains Mono'; }
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
    """Common <html>…</html> wrapper used by both scan and merged reports."""
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


def build_merged_html(merged, lang="en"):
    """Render the dual-track (config vs usage) report."""
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
        f'<span class="swatch">{_t(lang,"dual_legend_na")}</span>'
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
            <span class="lvl-tag">{_level_label(t.get('level_threshold', 0), lang)}</span>
          </div>
        </div>
        {gap_table_html(t, dim_labels, lang=lang)}
        <div style="margin-top: 18px;">{merged_findings_html(t, dim_labels, lang=lang)}</div>
        {"".join(f'<p class="blind"><span>{_t(lang,"blind_label")}</span>{_blind_text(b, lang)}</p>' for b in t.get('blind_spots', []))}
        {"".join(f'<p class="blind"><span>{_t(lang,"note_label")}</span>{n}</p>' for n in t.get('notes', []))}
      </section>""" for t in targets)

    level_thresholds = merged.get("level_thresholds")
    if level_thresholds is None:
        level_thresholds = [th for th, _ in i18n_mod.LEVELS]
    level_scale = "".join(
        _level_scale_item(th, lang) for th in level_thresholds)

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
      <div class="scale">{level_scale}</div>
    </section>

    {top_gaps_html(targets, lang=lang)}

    {target_sections}

    <footer>{_t(lang,"footer_merged")}</footer>
  </div>"""

    return _scaffold_html(lang=lang, title=_t(lang, "title_merged"),
                          body=body, extra_css=_MERGED_EXTRA_CSS)


def _prompt_lang():
    """互動式選單;非 TTY 環境直接回 'en'。"""
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
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", default=None,
                    help="agent-radar scan 產出的 JSON (scan-only 模式)")
    ap.add_argument("--session", default=None,
                    help="agent-radar session 產出的 JSON (可選,加上後報告會多一張運用度雷達)")
    ap.add_argument("--merged", default=None,
                    help="agent-radar merge 產出的 JSON (雙軌雷達模式)")
    ap.add_argument("--lang", choices=["en", "zh"], default=None,
                    help="報告語言 (en|zh)。未指定時若為 TTY 會彈出選單,否則預設 en")
    ap.add_argument("-o", "--output", default="report.html")
    args = ap.parse_args()

    lang = args.lang if args.lang else _prompt_lang()

    if args.merged:
        merged = json.loads(Path(args.merged).read_text(encoding="utf-8"))
        html = build_merged_html(merged, lang=lang)
    else:
        if not args.input:
            ap.error("input 為必要參數 (或改用 --merged)")
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))
        session_data = None
        if args.session:
            session_data = json.loads(Path(args.session).read_text(encoding="utf-8"))
        html = build_html(data, session_data=session_data, lang=lang)
    Path(args.output).write_text(html, encoding="utf-8")
    print(f"[ok] report generated ({lang}): {args.output}")


if __name__ == "__main__":
    main()
