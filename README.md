# aws-rds-mysql-copilot

AWS RDS for MySQL 智能诊断与巡检 — 给 AI agent(Claude Code / Cursor / Cline / 任何支持 [Agent Skill](https://github.com/anthropics/skills) 协议的客户端)用的领域知识库 + 工具集。

提供三种工作模式:**问答 / 诊断 / 巡检**(详见 [SKILL.md](SKILL.md))。

## 它能做什么

- **问答**:回答 AWS RDS / CloudWatch / Performance Insights 概念、参数、指标含义,或单点查询监控数据
  > "什么是 PI?" / "my-db 的 CPU 怎么样?" / "gp2 跟 gp3 区别?"
- **巡检**:对一个实例跑 8 项健康度检查(CPU / 连接 / IOPS / 复制延迟 / 存储 / 内存 / 慢日志 / 告警),输出结构化报告
  > "对 my-db 做 AWS RDS 巡检"
- **诊断**:按 5 步法(指标采集 → 异常定位 → 执行计划分析 → 根因判定 → 修复方案)排查具体问题
  > "my-db 慢 SQL 突增,帮我看看"

## 安装

```bash
git clone https://github.com/liuxinbot/aws-rds-mysql-copilot.git
cd aws-rds-mysql-copilot
bash install.sh
```

幂等可重跑。会:
- 装 aws CLI v2(若缺)
- 创建项目级 venv 在 `~/.local/share/aws-rds-mysql-copilot/venv/`,装 boto3
- 引导你输入 AWS AK/SK + region,写入 `~/.aws/{config,credentials}`(权限 600)
- 跑 smoke 验证(`aws sts get-caller-identity` + venv boto3)
- 建 skill 软链 `~/.agents/skills/aws-rds-mysql-copilot`,可选链接到 `~/.claude/skills/`

系统需要 Python 3.11+ 用于创建 venv(脚本内部用了 tomllib)。

## 卸载

```bash
bash uninstall.sh
```

会删:skill 软链 / venv。共享文件(`~/.aws/`、仓库本身)仅提示不动,避免误删其他配置。

## IAM 权限

最小只读 IAM policy 见 [docs/iam-readonly-policy.json](docs/iam-readonly-policy.json),完整说明见 [docs/iam-readonly-policy.md](docs/iam-readonly-policy.md)。

涵盖:
- `rds:Describe*` / `rds:ListTagsForResource`
- `cloudwatch:GetMetricStatistics` / `GetMetricData` / `ListMetrics` / `DescribeAlarms`
- `logs:FilterLogEvents`(限 `/aws/rds/instance/*`)
- `pi:*`(只读子集)
- `sts:GetCallerIdentity`(smoke 用)

**全只读**,不含任何 Create / Modify / Delete / Reboot / Failover 写动作。

## 三种模式

| 模式 | 触发 | 说明 |
|------|------|------|
| 问答 | "查 AWS RDS X 的 CPU"、"什么是 PI" | 读 reference + 单次 aws CLI 查询 |
| 巡检 | "对 X 跑 AWS RDS 巡检" | inspection.yaml 8 项 + 一次 metrics-batch |
| 诊断 | "AWS RDS X 慢 SQL 突增" | diagnosis-playbook + AI 自由编排工具 |

## 工具

| 工具 | 用途 |
|------|------|
| `aws` CLI v2 | 大多数原生查询 |
| `scripts/metrics-batch.py` | 批量 CloudWatch 指标 + 环比 + p95 |
| `scripts/slow-log.py` | RDS 慢日志拉取 + SQL 模板归一化 |
| `scripts/pi-query.py` | Performance Insights(top-sql / top-wait / slice-by) |

## 设计理念

- **诊断不走决策树 yaml,改用 markdown playbook**:AI 在 5 步法框架内自由编排工具,而不是按死板决策树执行
- **巡检 critical 不强制跳诊断**:`inspection.yaml` 用 `on_critical_hint` 给提示,AI / 用户决定要不要进诊断
- **变更必须标注【需 DBA 审核】**:本 skill 是只读范围,绝不发起变更动作 — IAM 也只给只读权限作为护栏

## License

[Apache 2.0](LICENSE)
