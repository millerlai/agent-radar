#!/usr/bin/env python3
"""
agent-radar :: report.py
========================
讀取 scanner.py 產出的 JSON，生成單檔 HTML 雷達圖診斷報告。

用法:
  python scanner.py <paths...> -o scan.json
  python report.py scan.json -o report.html
"""

import argparse
import json
import math
from pathlib import Path


# 色票：暗色「診斷儀表板」風
PALETTE = ["#4ade80", "#38bdf8", "#fbbf24", "#f472b6", "#a78bfa", "#fb923c", "#2dd4bf", "#f87171"]


def radar_svg(targets, dim_keys, dim_labels, size=460, idx_offset=0):
    """產生多目標疊圖的雷達圖 SVG。"""
    cx = cy = size / 2
    radius = size * 0.34
    n = len(dim_keys)
    rings = 4

    def point(value, i):
        # value 0..100 -> 半徑；i -> 角度 (從正上方順時針)
        ang = -math.pi / 2 + (2 * math.pi * i / n)
        r = radius * (value / 100)
        return cx + r * math.cos(ang), cy + r * math.sin(ang)

    parts = [f'<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg" '
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
        # 中文標籤拆兩段更好讀
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


def findings_html(target):
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
                  <span class="f-label">{f['label']}</span>
                  <span class="f-score">{f['score']:.0f}/{f['weight']:.0f}</span>
                </div>
                <div class="f-bar"><i style="width:{ratio*100:.0f}%"></i></div>
                <div class="f-detail">{f['detail']}</div>
              </div>""")
        tone = "good" if score >= 60 else ("mid" if score >= 30 else "low")
        blocks.append(f"""
          <details class="dim-block">
            <summary>
              <span class="d-name">{DIM_LABELS[dim]}</span>
              <span class="d-score {tone}">{score:.0f}</span>
            </summary>
            <div class="findings">{''.join(rows)}</div>
          </details>""")
    return "".join(blocks)


DIM_LABELS = {}  # 由 main 注入


def build_usage_section(session_data):
    """生成「實際運用度」雷達卡 (來自 session_scanner.py 輸出)。"""
    if not session_data:
        return ""
    dims = session_data.get("usage_dimensions", {})
    targets = session_data.get("targets", [])
    if not targets or not dims:
        return ""

    dim_keys = list(dims.keys())
    # 重複使用 radar_svg,需要把 usage targets 的 scores 套上 dim_keys
    radar = radar_svg(targets, dim_keys, dims, idx_offset=3)

    legend = "".join(
        f'<span class="leg"><i style="background:{PALETTE[(i+3)%len(PALETTE)]}"></i>'
        f'{t["name"]} <b>{t["overall"]:.0f}</b></span>'
        for i, t in enumerate(targets))

    blind = "".join(
        f'<p class="blind"><span>盲區</span>{b}</p>'
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
                  <span class="f-label">{f['label']}</span>
                  <span class="f-score">{f['score']:.0f}/{f['weight']:.0f}</span>
                </div>
                <div class="f-bar"><i style="width:{ratio*100:.0f}%"></i></div>
                <div class="f-detail">{f['detail']}</div>
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
      <h2>運用度雷達 · Actual Usage</h2>
      <p class="card-sub">讀取本機 ~/.claude/projects/ JSONL,量化 session 內真正發生的工具呼叫、
      Skill 觸發、MCP 呼叫、使用者糾正率。與上方配置雷達的「落差」即為改善空間。</p>
      <div class="radar-wrap">
        {radar}
        <div class="legend">{legend}</div>
      </div>
      <div style="margin-top: 22px;">{''.join(rows)}</div>
      {blind}
    </section>"""


def build_html(data, session_data=None):
    global DIM_LABELS
    DIM_LABELS = data["dimensions"]
    dim_keys = list(data["dimensions"].keys())
    targets = data["targets"]

    if not targets:
        return "<html><body>No targets scanned.</body></html>"

    # 團隊聚合 (>1 目標時顯示)
    is_team = len(targets) > 1
    team_avg = {}
    for k in dim_keys:
        vals = [t["scores"].get(k, 0) for t in targets]
        team_avg[k] = round(sum(vals) / len(vals), 1)
    team_overall = round(sum(team_avg.values()) / len(team_avg), 1)

    # --- 雷達圖 ---
    radar = radar_svg(targets, dim_keys, data["dimensions"])

    # --- 圖例 ---
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
                  <td class="lvl">{t['level']}</td>
                </tr>""" for i, t in enumerate(ranked))
        ranking = f"""
        <section class="card">
          <h2>團隊排行 · Team Benchmark</h2>
          <table class="rank-table">
            <thead><tr><th>#</th><th>目標</th><th>總分</th><th>層級</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
          <p class="team-avg">團隊平均成熟度 <b>{team_overall:.0f}</b> / 100</p>
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
            <span class="lvl-tag">{t['level']}</span>
          </div>
        </div>
        {findings_html(t)}
        {"".join(f'<p class="blind"><span>盲區</span>{b}</p>' for b in t.get('blind_spots', []))}
      </section>""" for t in targets)

    # --- 層級量尺 ---
    level_scale = "".join(
        f'<div class="lv"><b>{lbl.split("·")[0].strip()}</b>'
        f'<span>{lbl.split("·")[1].strip() if "·" in lbl else ""}</span>'
        f'<i>{th}+</i></div>'
        for th, lbl in data["levels"])

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Agent 能力邊界診斷</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&family=Noto+Sans+TC:wght@400;500;700;900&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0b0f14;
    --panel: #121821;
    --panel-2: #0f141b;
    --line: #1f2a37;
    --ink: #e4ecf4;
    --ink-dim: #8195a9;
    --good: #4ade80;
    --mid: #fbbf24;
    --low: #f87171;
    --accent: #38bdf8;
  }}
  body {{
    background:
      radial-gradient(900px 600px at 80% -10%, rgba(56,189,248,.08), transparent),
      radial-gradient(700px 500px at 0% 100%, rgba(74,222,128,.06), transparent),
      var(--bg);
    color: var(--ink);
    font-family: 'Noto Sans TC', system-ui, sans-serif;
    line-height: 1.6;
    padding: 48px 20px 80px;
    min-height: 100vh;
  }}
  .wrap {{ max-width: 1080px; margin: 0 auto; }}
  .masthead {{ margin-bottom: 36px; }}
  .kicker {{
    font-family: 'JetBrains Mono', monospace; font-size: 12px; letter-spacing: .28em;
    color: var(--accent); text-transform: uppercase; margin-bottom: 12px;
  }}
  h1 {{ font-size: clamp(28px, 5vw, 46px); font-weight: 900; line-height: 1.1; letter-spacing: -.02em; }}
  h1 .em {{ color: var(--accent); }}
  .sub {{ color: var(--ink-dim); margin-top: 14px; max-width: 60ch; font-size: 15px; }}

  .card {{
    background: linear-gradient(180deg, var(--panel), var(--panel-2));
    border: 1px solid var(--line); border-radius: 16px;
    padding: 28px; margin-bottom: 22px;
  }}
  h2 {{ font-size: 18px; margin-bottom: 18px; display: flex; align-items: center; gap: 10px; }}
  h2::before {{ content: ""; width: 4px; height: 18px; background: var(--accent); border-radius: 2px; }}
  .card-sub {{ color: var(--ink-dim); font-size: 13.5px; max-width: 70ch; margin: -8px 0 18px; }}

  .radar-wrap {{ display: grid; grid-template-columns: 1.1fr .9fr; gap: 24px; align-items: center; }}
  @media (max-width: 760px) {{ .radar-wrap {{ grid-template-columns: 1fr; }} }}
  .radar {{ width: 100%; height: auto; }}
  .grid-ring {{ fill: none; stroke: var(--line); stroke-width: 1; }}
  .axis {{ stroke: var(--line); stroke-width: 1; }}
  .axis-label {{ fill: var(--ink-dim); font-size: 12.5px; font-family: 'Noto Sans TC'; font-weight: 500; }}
  .series {{ filter: drop-shadow(0 0 8px color-mix(in srgb, var(--c) 40%, transparent)); }}

  .legend {{ display: flex; flex-direction: column; gap: 10px; }}
  .leg {{ display: flex; align-items: center; gap: 10px; font-size: 14px; color: var(--ink-dim); }}
  .leg i {{ width: 14px; height: 14px; border-radius: 4px; display: inline-block; }}
  .leg b {{ margin-left: auto; color: var(--ink); font-family: 'JetBrains Mono'; }}

  .scale {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 22px; }}
  .lv {{ flex: 1; min-width: 110px; background: var(--panel-2); border: 1px solid var(--line);
         border-radius: 10px; padding: 10px 12px; }}
  .lv b {{ display: block; font-family: 'JetBrains Mono'; color: var(--accent); font-size: 13px; }}
  .lv span {{ display: block; font-size: 12px; color: var(--ink-dim); }}
  .lv i {{ font-style: normal; font-size: 11px; color: var(--ink-dim); font-family: 'JetBrains Mono'; }}

  .rank-table {{ width: 100%; border-collapse: collapse; }}
  .rank-table th {{ text-align: left; font-size: 12px; color: var(--ink-dim); font-weight: 500;
                    padding: 8px 10px; border-bottom: 1px solid var(--line); }}
  .rank-table td {{ padding: 12px 10px; border-bottom: 1px solid var(--line); font-size: 14px; }}
  .rank-table .rank {{ font-family: 'JetBrains Mono'; color: var(--ink-dim); width: 36px; }}
  .lvl {{ font-size: 12px; color: var(--ink-dim); }}
  .pill {{ font-family: 'JetBrains Mono'; font-weight: 700; padding: 3px 10px; border-radius: 999px; font-size: 13px; }}
  .pill.good {{ background: rgba(74,222,128,.15); color: var(--good); }}
  .pill.mid {{ background: rgba(251,191,36,.15); color: var(--mid); }}
  .pill.low {{ background: rgba(248,113,113,.15); color: var(--low); }}
  .team-avg {{ margin-top: 16px; color: var(--ink-dim); font-size: 14px; }}
  .team-avg b {{ color: var(--ink); font-family: 'JetBrains Mono'; font-size: 18px; }}

  .target-head {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
                  margin-bottom: 20px; padding-bottom: 18px; border-bottom: 1px solid var(--line); }}
  .target-head h3 {{ font-size: 20px; }}
  .path {{ font-family: 'JetBrains Mono'; font-size: 11.5px; color: var(--ink-dim); word-break: break-all; }}
  .big-score {{ text-align: right; min-width: 110px; }}
  .big-score .num {{ font-family: 'JetBrains Mono'; font-weight: 800; font-size: 40px; line-height: 1; display: block; }}
  .big-score.good .num {{ color: var(--good); }}
  .big-score.mid .num {{ color: var(--mid); }}
  .big-score.low .num {{ color: var(--low); }}
  .lvl-tag {{ font-size: 11px; color: var(--ink-dim); font-family: 'JetBrains Mono'; }}

  .dim-block {{ border: 1px solid var(--line); border-radius: 12px; margin-bottom: 10px; overflow: hidden; }}
  .dim-block summary {{ list-style: none; cursor: pointer; display: flex; justify-content: space-between;
                        align-items: center; padding: 14px 18px; background: var(--panel-2); }}
  .dim-block summary::-webkit-details-marker {{ display: none; }}
  .dim-block summary:hover {{ background: #141b25; }}
  .d-name {{ font-weight: 700; font-size: 15px; }}
  .d-score {{ font-family: 'JetBrains Mono'; font-weight: 800; font-size: 18px; }}
  .d-score.good {{ color: var(--good); }} .d-score.mid {{ color: var(--mid); }} .d-score.low {{ color: var(--low); }}
  .findings {{ padding: 8px 18px 16px; }}
  .finding {{ padding: 12px 0; border-bottom: 1px dashed var(--line); }}
  .finding:last-child {{ border-bottom: none; }}
  .f-head {{ display: flex; justify-content: space-between; font-size: 14px; }}
  .f-label {{ font-weight: 500; }}
  .f-score {{ font-family: 'JetBrains Mono'; color: var(--ink-dim); font-size: 12px; }}
  .f-bar {{ height: 5px; background: var(--line); border-radius: 3px; margin: 7px 0; overflow: hidden; }}
  .f-bar i {{ display: block; height: 100%; border-radius: 3px; }}
  .finding.good .f-bar i {{ background: var(--good); }}
  .finding.mid .f-bar i {{ background: var(--mid); }}
  .finding.low .f-bar i {{ background: var(--low); }}
  .f-detail {{ font-size: 12.5px; color: var(--ink-dim); }}

  .blind {{ margin-top: 16px; font-size: 13px; color: var(--ink-dim); background: rgba(56,189,248,.06);
            border-left: 3px solid var(--accent); padding: 10px 14px; border-radius: 0 8px 8px 0; }}
  .blind span {{ font-family: 'JetBrains Mono'; color: var(--accent); font-weight: 700; margin-right: 8px;
                 text-transform: uppercase; font-size: 11px; letter-spacing: .1em; }}

  footer {{ text-align: center; color: var(--ink-dim); font-size: 12px; margin-top: 40px;
            font-family: 'JetBrains Mono'; }}
</style>
</head>
<body>
  <div class="wrap">
    <header class="masthead">
      <div class="kicker">agent-radar · capability boundary scan</div>
      <h1>AI Agent <span class="em">能力邊界</span>診斷報告</h1>
      <p class="sub">透過掃描檔案系統指紋 (CLAUDE.md · skills · MCP · hooks · subagents · git history)，
      量化 Claude Code 生態的「配置成熟度」。分數反映設定完整度，非實際運用度。</p>
    </header>

    <section class="card">
      <h2>成熟度雷達 · Maturity Radar</h2>
      <div class="radar-wrap">
        {radar}
        <div class="legend">{legend}</div>
      </div>
      <div class="scale">{level_scale}</div>
    </section>

    {ranking}

    {build_usage_section(session_data)}

    {details}

    <footer>agent-radar · static fingerprint scan · 配置完整度 ≠ 實際運用度</footer>
  </div>
</body>
</html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="scanner.py 產出的 JSON")
    ap.add_argument("--session", default=None,
                    help="session_scanner.py 產出的 JSON (可選,加上後報告會多一張運用度雷達)")
    ap.add_argument("-o", "--output", default="report.html")
    args = ap.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    session_data = None
    if args.session:
        session_data = json.loads(Path(args.session).read_text(encoding="utf-8"))
    html = build_html(data, session_data=session_data)
    Path(args.output).write_text(html, encoding="utf-8")
    print(f"[ok] 報告已生成: {args.output}")


if __name__ == "__main__":
    main()
