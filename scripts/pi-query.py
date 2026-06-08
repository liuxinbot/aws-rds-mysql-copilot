#!/usr/bin/env python3
"""pi-query.py — Performance Insights 封装.

Usage:
  pi-query <db-id> --top-sql [--range 1h] [--limit 10]
  pi-query <db-id> --top-wait [--range 1h]
  pi-query <db-id> --slice-by user [--range 1h]
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
import sys
from datetime import datetime, timedelta, timezone

import boto3
import botocore


# 命令行 slice 名 → PI dimension key
SLICE_DIMENSION_MAP = {
    "sql":      "db.sql_tokenized",
    "wait":     "db.wait_event",
    "user":     "db.user",
    "host":     "db.host",
    "database": "db.name",
    "app":      "db.application",
}


def parse_range(r: str) -> timedelta:
    if r.endswith("m"): return timedelta(minutes=int(r[:-1]))
    if r.endswith("h"): return timedelta(hours=int(r[:-1]))
    if r.endswith("d"): return timedelta(days=int(r[:-1]))
    raise ValueError(f"bad range: {r}")


def get_dbi_resource_id(rds, db_id: str) -> str:
    resp = rds.describe_db_instances(DBInstanceIdentifier=db_id)
    insts = resp.get("DBInstances", [])
    if not insts:
        raise ValueError(f"db instance not found: {db_id}")
    inst = insts[0]
    if not inst.get("PerformanceInsightsEnabled"):
        raise ValueError(f"Performance Insights is not enabled for {db_id}")
    rid = inst.get("DbiResourceId")
    if not rid:
        raise ValueError(f"DbiResourceId missing for {db_id}")
    return rid


def query_top(pi, resource_id: str, start, end, dim: str, limit: int) -> list[dict]:
    resp = pi.get_resource_metrics(
        ServiceType="RDS",
        Identifier=resource_id,
        StartTime=start,
        EndTime=end,
        PeriodInSeconds=60,
        MetricQueries=[{
            "Metric": "db.load.avg",
            "GroupBy": {"Group": dim, "Limit": limit},
        }],
    )
    out = []
    for series in resp.get("MetricList", []):
        key = series.get("Key", {})
        dims = key.get("Dimensions", {})
        values = [p.get("Value") for p in series.get("DataPoints", [])
                  if p.get("Value") is not None]
        avg_load = sum(values) / len(values) if values else 0.0
        peak_load = max(values) if values else 0.0
        out.append({
            "dimensions": dims,
            "avg_load": round(avg_load, 4),
            "peak_load": round(peak_load, 4),
        })
    # 按 avg_load 倒序(可与 vCPU 数对比的语义)
    out.sort(key=lambda x: x["avg_load"], reverse=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("db_id")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--top-sql", action="store_true")
    grp.add_argument("--top-wait", action="store_true")
    grp.add_argument("--slice-by", choices=list(SLICE_DIMENSION_MAP.keys()))
    ap.add_argument("--range", default="1h")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    end = datetime.now(timezone.utc)
    try:
        start = end - parse_range(args.range)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(2)

    if args.top_sql:    dim = SLICE_DIMENSION_MAP["sql"]
    elif args.top_wait: dim = SLICE_DIMENSION_MAP["wait"]
    else:               dim = SLICE_DIMENSION_MAP[args.slice_by]

    rds = boto3.client("rds")
    pi  = boto3.client("pi")

    try:
        rid = get_dbi_resource_id(rds, args.db_id)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(3)
    except botocore.exceptions.ClientError as e:
        print(f"AWS error: {e}", file=sys.stderr); sys.exit(2)

    try:
        rows = query_top(pi, rid, start, end, dim, args.limit)
    except botocore.exceptions.ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("NotAuthorizedException", "AccessDeniedException"):
            print(f"error: IAM 权限不足,需 pi:GetResourceMetrics 等只读权限 ({code})",
                  file=sys.stderr)
            sys.exit(3)
        print(f"AWS error: {e}", file=sys.stderr)
        sys.exit(2)

    out = {
        "db_instance_id": args.db_id,
        "dimension": dim,
        "range": args.range,
        "results": rows,
    }
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"DB {args.db_id} | dim={dim} | range={args.range}\n")
        for i, r in enumerate(rows, 1):
            d = r["dimensions"]
            label = next(iter(d.values())) if d else "<unknown>"
            print(f"#{i}  avg_load={r['avg_load']}  peak_load={r['peak_load']}  "
                  f"{str(label)[:200]}")


if __name__ == "__main__":
    main()
