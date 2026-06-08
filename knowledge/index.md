# aws-rds-mysql-copilot 知识入口

| 模式 | 入口文件 | 用途 |
|------|---------|------|
| 问答 | `reference/index.md` → 子文件 | AWS RDS 概念 / 指标 / 参数 / FAQ |
| 巡检 | `inspection.yaml` | 8 项健康度检查 + on_critical_hint |
| 诊断 | `diagnosis-playbook.md` | DBA 排查思路 + 标准 5 步法 + 起手清单 |
| 性能优化 | `optimization-playbook.md` | 索引 / 参数 / SQL 重写 / 容量建议 |

## 工具

- `aws` CLI v2 — 直接通过 Bash 调用,凭证由 `~/.aws/{config,credentials}` 自动取
- `scripts/metrics-batch.py` — 批量 CloudWatch 指标 + 环比
- `scripts/slow-log.py` — 慢日志解析 + SQL 模板归一化
- `scripts/pi-query.py` — Performance Insights 封装

## 路径约定

所有路径都**相对于 SKILL.md 所在目录**,不写绝对路径。
