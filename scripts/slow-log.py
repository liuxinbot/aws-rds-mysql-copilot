#!/usr/bin/env python3
"""slow-log.py — 拉 RDS 慢日志 + SQL 模板归一化.

Usage:
  slow-log <db-id> [--range 24h] [--top 20] [--min-time 1] [--json]
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
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean

import boto3
import botocore


# ---------- 慢日志条目解析 ----------
ENTRY_RE = re.compile(
    r"# Time:\s*(?P<time>\S+)\s*\n"
    r"# User@Host:\s*(?P<user>[^\n]+)\n"
    r"# Query_time:\s*(?P<qtime>[\d.]+)\s+Lock_time:\s*(?P<ltime>[\d.]+)\s+"
    r"Rows_sent:\s*(?P<sent>\d+)\s+Rows_examined:\s*(?P<examined>\d+)\s*\n"
    r"(?:[^\n]*\n)*?"        # SET timestamp= / use db; 等元信息行,跳过
    r"(?P<sql>(?:.|\n)*?);(?=\s*(?:#|\Z))",
    re.MULTILINE,
)


# 慢日志体里有 `SET timestamp=...;` 和 `use <db>;` 这类元信息行,从 SQL 体里剥离
META_LINE_RE = re.compile(r'^\s*(?:SET\s+|use\s+\S+\s*;?\s*$)', re.IGNORECASE)


def _strip_sql_meta(sql: str) -> str:
    """剥离慢日志体里的 SET timestamp / use db; 等元信息行,仅保留实际 SQL."""
    kept = []
    for line in sql.splitlines():
        if META_LINE_RE.match(line):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def parse_entries(blob: str):
    for m in ENTRY_RE.finditer(blob):
        sql = _strip_sql_meta(m.group("sql").strip())
        if not sql:
            continue
        yield {
            "time": m.group("time"),
            "qtime": float(m.group("qtime")),
            "ltime": float(m.group("ltime")),
            "rows_sent": int(m.group("sent")),
            "rows_examined": int(m.group("examined")),
            "sql": sql,
        }


# ---------- SQL 模板归一化 ----------
COMMENT_LINE_RE  = re.compile(r"--[^\n]*")
COMMENT_BLOCK_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
STR_LITERAL_RE   = re.compile(r"'(?:[^'\\]|\\.|'')*'")  # 支持 \\、\'、''
IN_LIST_RE       = re.compile(r"\bIN\s*\([^)]*\)", re.IGNORECASE)
NUM_LITERAL_RE   = re.compile(r"\b\d+(\.\d+)?\b")
WHITESPACE_RE    = re.compile(r"\s+")


def normalize(sql: str) -> str:
    # 先去注释,避免后续被换行折叠后吞掉 SQL
    s = COMMENT_BLOCK_RE.sub("", sql)
    s = COMMENT_LINE_RE.sub("", s)
    s = STR_LITERAL_RE.sub("?", s)
    s = IN_LIST_RE.sub("IN (?)", s)
    s = NUM_LITERAL_RE.sub("?", s)
    s = WHITESPACE_RE.sub(" ", s).strip()
    s = s.rstrip(";")
    return s


# ---------- CloudWatch Logs 拉取 ----------
def fetch_logs(db_id: str, start_ms: int, end_ms: int) -> str:
    logs = boto3.client("logs")
    log_group = f"/aws/rds/instance/{db_id}/slowquery"
    chunks = []
    next_token = None
    while True:
        kw = dict(logGroupName=log_group, startTime=start_ms, endTime=end_ms, limit=10000)
        if next_token:
            kw["nextToken"] = next_token
        resp = logs.filter_log_events(**kw)
        chunks.extend(e["message"] for e in resp.get("events", []))
        next_token = resp.get("nextToken")
        if not next_token:
            break
    return "\n".join(chunks)


# ---------- main ----------
def parse_range(rg: str) -> timedelta:
    if rg.endswith("m"): return timedelta(minutes=int(rg[:-1]))
    if rg.endswith("h"): return timedelta(hours=int(rg[:-1]))
    if rg.endswith("d"): return timedelta(days=int(rg[:-1]))
    raise ValueError(f"unknown range: {rg}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("db_id")
    ap.add_argument("--range", default="24h")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--min-time", type=float, default=0.0,
                    help="只看 query_time >= 此值的条目(秒)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    end = datetime.now(timezone.utc)
    try:
        start = end - parse_range(args.range)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(2)

    try:
        blob = fetch_logs(args.db_id,
                          int(start.timestamp() * 1000),
                          int(end.timestamp() * 1000))
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            print(f"slow query log not enabled for {args.db_id} "
                  f"(log group /aws/rds/instance/{args.db_id}/slowquery missing)",
                  file=sys.stderr)
            sys.exit(3)
        raise

    buckets: dict[str, list[dict]] = defaultdict(list)
    for e in parse_entries(blob):
        if e["qtime"] < args.min_time:
            continue
        buckets[normalize(e["sql"])].append(e)

    items = []
    for tmpl, group in buckets.items():
        items.append({
            "template": tmpl,
            "count": len(group),
            "avg_time": round(mean(e["qtime"] for e in group), 3),
            "max_time": round(max(e["qtime"] for e in group), 3),
            "rows_examined_avg": int(mean(e["rows_examined"] for e in group)),
            "rows_sent_avg":     int(mean(e["rows_sent"] for e in group)),
            "first_seen": min(e["time"] for e in group),
            "last_seen":  max(e["time"] for e in group),
            "sample_sql": group[0]["sql"][:500],
        })
    items.sort(key=lambda x: x["count"] * x["avg_time"], reverse=True)
    items = items[: args.top]

    out = {"db_instance_id": args.db_id, "range": args.range, "items": items}
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"DB {args.db_id} | range {args.range} | top {len(items)} templates "
              f"(by count × avg_time)\n")
        for i, it in enumerate(items, 1):
            print(f"#{i}  count={it['count']}  avg={it['avg_time']}s  "
                  f"max={it['max_time']}s  rows_ex_avg={it['rows_examined_avg']}")
            print(f"    template: {it['template'][:200]}")
            print()


if __name__ == "__main__":
    main()
