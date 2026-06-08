# Changelog

[中文](CHANGELOG.zh.md) | English

## 0.1.0 - 2026-06-08

Initial open-source release.

### Features

- Three operating modes: Q&A, inspection, and diagnosis (see [SKILL.md](SKILL.md))
- 8-item health inspection driven by `knowledge/inspection.yaml` with `on_critical_hint` (does not force a jump into diagnosis)
- Markdown diagnosis playbook (`knowledge/diagnosis-playbook.md`) — AI orchestrates tools freely within a 5-step DBA framework, instead of executing a rigid decision-tree YAML
- Optimization playbook (`knowledge/optimization-playbook.md`) covering indexing, parameter tuning, SQL rewrites, and capacity sizing
- Reference knowledge base under `knowledge/reference/` — concepts, CloudWatch metrics, Performance Insights guide, slow log format, parameter cheatsheet, FAQ
- Three Python tools, all with venv self-bootstrap: `metrics-batch.py` (batched CloudWatch + period-over-period delta + p95), `slow-log.py` (slow log + SQL template canonicalization), `pi-query.py` (Performance Insights — top-sql / top-wait / slice-by)
- Idempotent `install.sh` — installs aws CLI v2, creates a project-scoped venv at `~/.local/share/aws-rds-mysql-copilot/venv/`, prompts for AK/SK, runs smoke test, creates skill symlinks
- `uninstall.sh` — removes symlinks and venv; flags shared files for manual review

### Documentation

- Bilingual README (`README.md` Chinese, `README.en.md` English)
- Minimal read-only IAM policy with detailed rationale (`docs/iam-readonly-policy.json` + `docs/iam-readonly-policy.md`)
- Apache 2.0 license
