# aws-rds-mysql-copilot

[中文](README.md) | English

A domain knowledge base + tooling for AWS RDS for MySQL diagnosis & inspection, packaged as an Agent Skill for any AI client that speaks the [Agent Skill](https://github.com/anthropics/skills) protocol — Claude Code, Cursor, Cline, and others.

Three operating modes: **Q&A / diagnosis / inspection** (see [SKILL.md](SKILL.md), Chinese).

## What it does

- **Q&A** — answers AWS RDS / CloudWatch / Performance Insights concepts, parameters, and metric semantics, or pulls a single monitoring datapoint
  > "What is PI?" / "How's CPU on my-db?" / "gp2 vs gp3?"
- **Inspection** — runs 8 health checks against an instance (CPU / connections / IOPS / replica lag / storage / memory / slow log / alarms) and emits a structured report
  > "Run an AWS RDS inspection on my-db"
- **Diagnosis** — drives the 5-step DBA flow (collect metrics → locate anomaly → analyze EXPLAIN → identify root cause → propose fix) for a specific incident
  > "my-db is suddenly drowning in slow queries — take a look"

## Install

```bash
git clone https://github.com/liuxinbot/aws-rds-mysql-copilot.git
cd aws-rds-mysql-copilot
bash install.sh
```

Idempotent, safe to re-run. The installer will:
- install aws CLI v2 (if missing)
- create a project-scoped venv at `~/.local/share/aws-rds-mysql-copilot/venv/` and install boto3 into it
- prompt for AWS AK/SK + region, then write `~/.aws/{config,credentials}` with 0600 perms
- smoke-test (`aws sts get-caller-identity` + venv boto3)
- create a skill symlink at `~/.agents/skills/aws-rds-mysql-copilot`, optionally also at `~/.claude/skills/`

Requires system Python 3.11+ for venv creation (the scripts use `tomllib`).

## Uninstall

```bash
bash uninstall.sh
```

Removes the skill symlinks and the venv. Shared files (`~/.aws/`, the repo itself) are flagged for manual review — never auto-deleted, to avoid clobbering unrelated profiles.

## IAM permissions

The minimal read-only IAM policy lives in [docs/iam-readonly-policy.json](docs/iam-readonly-policy.json); see [docs/iam-readonly-policy.md](docs/iam-readonly-policy.md) (Chinese) for the rationale.

Covers:
- `rds:Describe*` / `rds:ListTagsForResource`
- `cloudwatch:GetMetricStatistics` / `GetMetricData` / `ListMetrics` / `DescribeAlarms`
- `logs:FilterLogEvents` (scoped to `/aws/rds/instance/*`)
- `pi:*` (read-only subset)
- `sts:GetCallerIdentity` (used by smoke test)

**Read-only by design** — no Create / Modify / Delete / Reboot / Failover actions. Even if the IAM user is compromised, the attacker cannot mutate RDS.

## The three modes

| Mode | Trigger | How it works |
|------|---------|--------------|
| Q&A | "What's the CPU on my-db?", "What is PI?" | reads `knowledge/reference/` + a single aws-CLI call |
| Inspection | "Run an AWS RDS inspection on my-db" | 8 checks from `inspection.yaml` + one `metrics-batch` call |
| Diagnosis | "my-db slow queries spiked" | follows `diagnosis-playbook.md`, AI orchestrates tools freely |

## Tools

| Tool | Purpose |
|------|---------|
| `aws` CLI v2 | covers most native queries |
| `scripts/metrics-batch.py` | batched CloudWatch metrics + period-over-period delta + p95 |
| `scripts/slow-log.py` | pulls RDS slow query log + canonicalizes SQL into templates |
| `scripts/pi-query.py` | Performance Insights (top-sql / top-wait / slice-by) |

## Design choices

- **Diagnosis is a markdown playbook, not a decision-tree YAML.** AI orchestrates tools freely within a 5-step framework — DBA work is too broad to enumerate exhaustively.
- **Inspection's `critical` does not auto-jump into diagnosis.** `inspection.yaml` uses `on_critical_hint` to surface the next step; the AI/user decides whether to dig deeper.
- **Any change recommendation must be tagged "Requires DBA review".** This skill stays read-only — IAM enforces the same boundary as a hard guardrail.

## License

[Apache 2.0](LICENSE)
