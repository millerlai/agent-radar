"""CLI: read an OTel events file → score → write usage.json.

Example
-------
  # MVP 流程 (個人,離線):
  export CLAUDE_CODE_ENABLE_TELEMETRY=1
  export OTEL_LOGS_EXPORTER=console
  export OTEL_METRICS_EXPORTER=console
  export OTEL_LOG_TOOL_DETAILS=1
  claude 2>> ~/.agent-radar/otel-events.log

  agent-radar usage \\
      --otel-log ~/.agent-radar/otel-events.log \\
      --scan scan.json \\
      --target my-repo \\
      -o usage.json

If --scan / --target are omitted, usage runs without static denominators
(ratios fall back to event-derived counts).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .collectors.otlp_file import OTLPFileCollector
from .merge import scan_context_for
from .usage_score import USAGE_DIMENSION_KEYS, score_window


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    # accept "...Z" too
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main():
    ap = argparse.ArgumentParser(prog="agent-radar usage",
                                 description="Score OTel events → usage.json")
    ap.add_argument("--otel-log", required=True,
                    help="Console exporter 落檔 (一行一筆 JSON)")
    ap.add_argument("--scan", default=None,
                    help="agent-radar scan 產出的 JSON,提供配置側分母")
    ap.add_argument("--target", default=None,
                    help="當 --scan 提供時,指定要對齊的 target 名稱 "
                         "(若 scan.json 只有 1 個 target 可省略)")
    ap.add_argument("--account", default=None,
                    help="僅統計符合此 user.email / user.account_uuid 的事件")
    ap.add_argument("--since", default=None, help="ISO 時間下界 (含),可選")
    ap.add_argument("--until", default=None, help="ISO 時間上界 (含),可選")
    ap.add_argument("-o", "--output", default="-")
    args = ap.parse_args()

    # 1. collect
    collector = OTLPFileCollector(args.otel_log)
    window = collector.fetch(
        since=_parse_iso(args.since) or datetime.fromtimestamp(0, tz=timezone.utc),
        until=_parse_iso(args.until) or datetime.now(tz=timezone.utc),
        account_filter=args.account,
    )

    # 2. derive scan_context if scan.json provided
    scan_ctx = None
    target_name = args.target
    if args.scan:
        scan_data = json.loads(Path(args.scan).read_text(encoding="utf-8"))
        scan_targets = scan_data.get("targets", [])
        if not scan_targets:
            print("[warn] --scan 提供的 JSON 沒有任何 target", file=sys.stderr)
        else:
            if target_name is None:
                if len(scan_targets) == 1:
                    target_name = scan_targets[0]["name"]
                else:
                    names = ", ".join(t["name"] for t in scan_targets)
                    print(f"[err] --scan 含 {len(scan_targets)} 個 target,"
                          f"請用 --target 指定其一: {names}", file=sys.stderr)
                    sys.exit(2)
            chosen = next((t for t in scan_targets if t["name"] == target_name), None)
            if not chosen:
                print(f"[err] --target {target_name} 不存在於 scan.json", file=sys.stderr)
                sys.exit(2)
            scan_ctx = scan_context_for(chosen)

    # default target name when scan not used
    if target_name is None:
        target_name = "self"

    # 3. score
    scored = score_window(window, scan_context=scan_ctx)

    out = {
        "usage_dimensions": USAGE_DIMENSION_KEYS,
        "scan_context": scan_ctx or {},
        "account_filter": args.account,
        "targets_by_name": {
            target_name: {
                "name": target_name,
                "scores": scored["scores"],
                "overall": scored["overall"],
                "findings_by_dim": scored["findings_by_dim"],
                "totals": scored["totals"],
                "notes": scored["notes"],
                "window": scored["window"],
            },
        },
    }

    payload = json.dumps(out, ensure_ascii=False, indent=2)
    if args.output == "-":
        print(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"[ok] 已寫入 {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
