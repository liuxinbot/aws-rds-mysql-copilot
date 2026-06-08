#!/usr/bin/env python3
"""metrics-batch.py — 批量拉 CloudWatch RDS 指标 + 环比.

Usage:
  metrics-batch <db-id> --preset health [--range 2h] [--compare 1d] [--json]
  metrics-batch <db-id> --metrics CPUUtilization,DatabaseConnections [--range 2h]
"""
# venv self-bootstrap: 自动 re-exec 到 aws-rds-mysql-copilot venv,保证依赖可用
# install.sh 创建 venv 在 ~/.local/share/aws-rds-mysql-copilot/venv/,内含 boto3
# 没装 venv 时,fallback 到 #!/usr/bin/env python3 自己(假定用户已自行装好依赖)
import os as _os, sys as _sys
_VENV_PY = _os.path.expanduser("~/.local/share/aws-rds-mysql-copilot/venv/bin/python3")
if _os.path.exists(_VENV_PY) and _sys.executable != _VENV_PY:
    _os.execv(_VENV_PY, [_VENV_PY] + _sys.argv)

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3


PRESET_HEALTH = [
    "CPUUtilization",
    "DatabaseConnections",
    "FreeableMemory",
    "FreeStorageSpace",
    "ReadIOPS", "WriteIOPS",
    "ReadLatency", "WriteLatency",
    "NetworkReceiveThroughput", "NetworkTransmitThroughput",
    "ReplicaLag",
    "SwapUsage",
    "CPUCreditBalance",  # 仅 burstable(t3/t4g)有,其他实例返回空
]


def parse_duration(s: str) -> timedelta:
    """'2h' / '30m' / '1d' → timedelta."""
    m = re.fullmatch(r"(\d+)([mhd])", s)
    if not m:
        raise ValueError(f"invalid duration: {s}")
    n, unit = int(m.group(1)), m.group(2)
    return {"m": timedelta(minutes=n),
            "h": timedelta(hours=n),
            "d": timedelta(days=n)}[unit]


def fetch_metric(cw, db_id: str, metric: str, start, end, period: int) -> list[dict]:
    """Fetch a metric with avg / max / p95 per data point.

    Note: CloudWatch get_metric_statistics 的 Statistics 与 ExtendedStatistics 互斥,
    所以拆两次 API 调用,按时间戳合并.
    """
    common = dict(
        Namespace="AWS/RDS",
        MetricName=metric,
        Dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_id}],
        StartTime=start,
        EndTime=end,
        Period=period,
    )
    r1 = cw.get_metric_statistics(**common, Statistics=["Average", "Maximum"])
    r2 = cw.get_metric_statistics(**common, ExtendedStatistics=["p95"])
    p95_by_ts = {p["Timestamp"]: p.get("ExtendedStatistics", {}).get("p95")
                 for p in r2.get("Datapoints", [])}
    points = sorted(r1.get("Datapoints", []), key=lambda p: p["Timestamp"])
    return [
        {"ts": p["Timestamp"].isoformat(),
         "avg": p.get("Average"),
         "max": p.get("Maximum"),
         "p95": p95_by_ts.get(p["Timestamp"])}
        for p in points
    ]


def summarize(points: list[dict]) -> dict:
    """Aggregate per-point series into one summary.

    p95_of_p95 = 窗口内每个采样点的 p95 中的最大值,代表"最差时段的 p95"
    """
    if not points:
        return {"count": 0, "avg_of_avg": None, "max_of_max": None, "p95_of_p95": None}
    avgs = [p["avg"] for p in points if p["avg"] is not None]
    maxs = [p["max"] for p in points if p["max"] is not None]
    p95s = [p["p95"] for p in points if p.get("p95") is not None]
    return {
        "count": len(points),
        "avg_of_avg": round(sum(avgs) / len(avgs), 3) if avgs else None,
        "max_of_max": round(max(maxs), 3) if maxs else None,
        "p95_of_p95": round(max(p95s), 3) if p95s else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("db_id", help="RDS DB instance identifier")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--preset", choices=["health"], help="预设指标组")
    grp.add_argument("--metrics", help="逗号分隔的指标名")
    ap.add_argument("--range", default="2h", help="时间范围 [默认 2h]")
    ap.add_argument("--compare", default=None, help="环比窗口,如 1d / 7d")
    ap.add_argument("--period", type=int, default=60, help="采样周期秒 [默认 60]")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    metrics = PRESET_HEALTH if args.preset == "health" else args.metrics.split(",")
    end = datetime.now(timezone.utc)
    start = end - parse_duration(args.range)

    cw = boto3.client("cloudwatch")

    result: dict[str, Any] = {
        "db_instance_id": args.db_id,
        "range": args.range,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "current": {},
    }
    for m in metrics:
        pts = fetch_metric(cw, args.db_id, m, start, end, args.period)
        result["current"][m] = {"summary": summarize(pts), "points": pts}

    if args.compare:
        delta = parse_duration(args.compare)
        cmp_start, cmp_end = start - delta, end - delta
        result["compare"] = {
            "shift": args.compare,
            "window": {"start": cmp_start.isoformat(), "end": cmp_end.isoformat()},
            "metrics": {},
        }
        for m in metrics:
            pts = fetch_metric(cw, args.db_id, m, cmp_start, cmp_end, args.period)
            result["compare"]["metrics"][m] = {"summary": summarize(pts), "points": pts}

    if args.json:
        print(json.dumps(result, default=str, indent=2))
    else:
        print(f"DB {args.db_id} | range {args.range}")
        for m in metrics:
            cur = result["current"][m]["summary"]
            line = (f"  {m:32s} avg={cur['avg_of_avg']}  "
                    f"p95={cur['p95_of_p95']}  max={cur['max_of_max']}")
            if args.compare:
                cmp_ = result["compare"]["metrics"][m]["summary"]
                line += (f"  | -{args.compare}: avg={cmp_['avg_of_avg']}  "
                         f"p95={cmp_['p95_of_p95']}  max={cmp_['max_of_max']}")
            print(line)


if __name__ == "__main__":
    main()
