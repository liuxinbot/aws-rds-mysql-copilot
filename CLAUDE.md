# CLAUDE.md

## 项目概述

aws-rds-mysql-copilot 是 AWS RDS for MySQL 知识域,以 Agent Skill 形态交付给 AI agent(Claude Code / Cursor / Cline 等)。

提供三种工作模式:**问答 / 诊断 / 巡检**(详见 `SKILL.md`)。

## 常用命令

```bash
# 一键安装(幂等可重跑)
bash install.sh

# 卸载(删 skill 软链 / venv;~/.aws 仅提示)
bash uninstall.sh

# 独立 smoke 验证(凭证就位后跑)
bash tests/smoke.sh

# 拉指标(巡检 / 诊断 batch 场景)
./scripts/metrics-batch.py <db-id> --preset health --range 2h --compare 1d --json

# 单指标问答场景(也可用原生 aws cloudwatch get-metric-statistics)
./scripts/metrics-batch.py <db-id> --metrics CPUUtilization --range 30m

# 拉慢日志 top 模板
./scripts/slow-log.py <db-id> --range 24h --top 20

# Performance Insights 三种 case
./scripts/pi-query.py <db-id> --top-sql --range 1h --limit 10
./scripts/pi-query.py <db-id> --top-wait --range 1h
./scripts/pi-query.py <db-id> --slice-by user --range 1h
```

## 架构

```
SKILL.md(入口路由,三模式分流)
  ├── 问答模式 → knowledge/reference/index.md → 子文件 + aws CLI 单次查询
  ├── 诊断模式 → knowledge/diagnosis-playbook.md(标准 5 步法 + AI 自由编排工具)
  └── 巡检模式 → knowledge/inspection.yaml(8 项 + on_critical_hint 不强制跳诊断)
```

## 目录结构

```
aws-rds-mysql-copilot/
├── SKILL.md                          # Skill 入口,三模式路由(全相对路径)
├── install.sh                        # 一键幂等安装(交互式收集 AK/SK)
├── uninstall.sh
├── README.md  CLAUDE.md  LICENSE  .gitignore
│
├── docs/
│   ├── iam-readonly-policy.json      # 推荐的最小只读 IAM policy
│   └── iam-readonly-policy.md        # IAM policy 说明
│
├── scripts/
│   ├── metrics-batch.py              # 批量 CloudWatch + 环比 + p95
│   ├── slow-log.py                   # 慢日志解析 + SQL 模板归一化
│   └── pi-query.py                   # Performance Insights 封装
│
├── knowledge/
│   ├── index.md                      # 内容入口 + 快速路由表
│   ├── inspection.yaml               # 巡检 8 项(每项含 on_critical_hint)
│   ├── diagnosis-playbook.md         # 诊断思路:标准 5 步法 + 起手清单 + AI 护栏
│   ├── optimization-playbook.md      # 性能优化:索引 / 参数 / SQL 重写 / 容量
│   └── reference/                    # 6 个领域知识文件 + index
│       ├── index.md
│       ├── concepts.md               # 引擎 / 规格 / 存储 / 参数组 / 备份 / HA / Proxy
│       ├── metrics.md                # CloudWatch 指标速查 + 8 项核心指标
│       ├── pi-guide.md               # Performance Insights 使用指南
│       ├── slow-log.md               # 慢日志获取与解析
│       ├── parameters.md             # 重点参数与默认值偏离判断
│       └── faq.md                    # FAQ:通用 / 监控 / 连接 / 故障
│
└── tests/
    └── smoke.sh                      # 安装后端到端验证(aws --version + sts + boto3)
```

## 知识文件职责

| 文件 | 存什么 |
|------|--------|
| `knowledge/reference/` | 领域知识:概念、CloudWatch 指标、PI 指南、慢日志格式、参数清单、FAQ |
| `knowledge/diagnosis-playbook.md` | 诊断思路指南:5 步法 + 8 类常见症状起手清单 + 5 条 AI 护栏(不是决策树 yaml) |
| `knowledge/optimization-playbook.md` | 性能优化思路:索引建议 / 参数调优 / SQL 重写 / 容量与版本升降配 |
| `knowledge/inspection.yaml` | 巡检 8 项:每项含 metric / healthy / warn / critical / on_critical_hint |

## 设计决策要点

### 诊断不走决策树 yaml,改用 markdown playbook

让 AI 在 playbook 框架内**自由编排工具**:
- AWS 工具更通用(原生 aws CLI 覆盖广 + PI / CloudWatch / Logs 互补)
- DBA 日常事项广,不适合 yaml 穷举
- AI 按"指标采集 → 异常定位 → 执行计划分析 → 根因判定 → 修复方案输出"5 步法推进,每步产出物明确

### 巡检 critical 不强制跳诊断

`inspection.yaml` 用 `on_critical_hint:` 给提示(下一步看哪里 / 用什么工具),不强制跳决策树。AI / 用户决定要不要进诊断。

### 巡检 CloudWatch p95 的拉取

CloudWatch `get_metric_statistics` 的 `Statistics` 与 `ExtendedStatistics` **互斥**,所以 `metrics-batch.py` 拆两次 API 调用、按时间戳合并出含 avg/max/p95 的数据点。

## Python 环境隔离(venv)

install.sh 在 `~/.local/share/aws-rds-mysql-copilot/venv/` 创建项目级 venv,所有 Python 依赖(boto3)装在这里,不污染系统 / Homebrew Python。

`scripts/*.py` 顶部有 self-bootstrap 代码:运行时检测 venv 存在则自动 re-exec,没装 venv 时 fallback 到系统 python3。这样:

- Clone 后直接 `./scripts/metrics-batch.py` 能跑(只要系统有 boto3 / venv 二选一)
- `git pull` 不破坏 shebang
- Python 升级后重跑 install.sh 重建 venv

## 工具

| 工具 | 用途 | 关键点 |
|------|------|------|
| 原生 aws CLI v2 | `describe-*` / `get-metric-statistics` / `describe-alarms` / `describe-events` | 覆盖 ~90% 调用,配置完凭证后直接用 |
| `scripts/metrics-batch.py` | 批量 CloudWatch + 环比 + p95 | 巡检场景固定 8 项 + 一次往返;`--preset health` / `--metrics A,B` 二选一 |
| `scripts/slow-log.py` | CloudWatch Logs 慢日志 | SQL 模板归一化(常量→? / IN 列表 / 引号转义)+ 元信息剥离 + 注释处理,按 `count×avg_time` 排序 |
| `scripts/pi-query.py` | Performance Insights | `--top-sql` / `--top-wait` / `--slice-by user/host/app/database`;输出 avg_load + peak_load |

## IAM 权限

最小只读 IAM policy 见 [docs/iam-readonly-policy.json](docs/iam-readonly-policy.json),完整说明见 [docs/iam-readonly-policy.md](docs/iam-readonly-policy.md)。

## 语言

所有文档和知识内容使用中文。
