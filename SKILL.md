---
name: aws-rds-mysql-copilot
description: AWS RDS for MySQL 智能诊断与巡检。当用户提到 AWS RDS、AWS MySQL、CloudWatch、Performance Insights、PI、DBLoad、CloudWatch Logs、慢SQL(AWS)、AWS数据库等关键词时使用。
---

# aws-rds-mysql-copilot — AWS RDS for MySQL 智能诊断与巡检

> **重要约束**:先判断工作模式,再按该模式的加载规则读取文件。禁止在判断模式前遍历目录。

## 路径约定

所有路径(`knowledge/...` / `scripts/...`)都**相对于本 SKILL.md 所在目录**,直接用相对路径访问即可。

## Step 1: 判断工作模式

根据用户意图选择**唯一**模式:

| 模式 | 触发条件 | 示例 |
|------|---------|------|
| 问答 | 用户在问知识 / 概念 / 原理,或查具体监控数据 | "什么是 PI"、"my-db 的 CPU"、"gp2 跟 gp3 区别" |
| 诊断 | 用户在描述问题 / 异常 / 告警 | "my-db CPU 飙到 95%"、"慢 SQL 突增" |
| 巡检 | 被要求做巡检 / 健康度评估 | "对 my-db 做 AWS RDS 巡检" |

## Step 2: 按模式加载文件

### 问答模式

**只读**:`knowledge/reference/` 目录下的文件
- 先读 `knowledge/reference/index.md` 确定哪个子文件包含答案
- 再读对应子文件回答
- 涉及具体监控数据(指标值)时,直接调 `aws cloudwatch get-metric-statistics` **单次查询**,不要调 `metrics-batch.py`(那是巡检场景的批量工具)

**不要读**:inspection.yaml、diagnosis-playbook.md(除非用户问的就是巡检 / 诊断的概念)

### 诊断模式

**按顺序读**:
1. `knowledge/diagnosis-playbook.md` — DBA 排查思路指南 + 标准 5 步法
2. 必要时参考 `knowledge/reference/`(如查指标含义、参数推荐值)

**诊断执行原则**(MUST 严格遵守):
1. **跟随标准 5 步法**:指标采集 → 异常定位 → 执行计划分析 → 根因判定 → 修复方案输出。允许根据现场跳步,但每步产出物必须在最终结论里呈现
2. **不要凭 1 个指标下结论**:至少交叉验证 2 个
3. **引用具体数据**:给结论时附数值 + 时间窗口
4. **变更建议必须标注【需 DBA 审核】**:本 skill 是只读范围,绝不发起变更动作
5. **承认不知道**:不要编 SQL 改写或编造数据

### 巡检模式

**只读**:`knowledge/inspection.yaml`
- 按 `collect` 一次性拉指标(`metrics-batch <id> --preset health --range 2h --compare 1d --json`)
- 按 `checks` 列表逐项判断 healthy / warn / critical
- critical 项**触发** `on_critical_hint` 提示给用户(不强制跳诊断)
- 输出结构化巡检报告

**不要读**:diagnosis-playbook.md / reference/(除非需要解释某个指标含义)

## 工具

| 工具 | 用途 |
|------|------|
| `aws` CLI v2 | 大多数原生查询(describe-* / get-metric-statistics / describe-alarms / describe-events) |
| `scripts/metrics-batch.py` | 批量 CloudWatch 指标 + 环比(巡检 / 诊断时拉一组) |
| `scripts/slow-log.py` | 慢日志拉取 + SQL 模板归一化 |
| `scripts/pi-query.py` | Performance Insights(--top-sql / --top-wait / --slice-by) |

凭证由 `~/.aws/{config,credentials}` 自动取,skill 内部**不处理凭证**。

### 工具缺失降级

诊断 / 巡检过程中调用脚本时,如果工具不可用:
1. **跳过该步骤**,在输出中标注 `[跳过: <tool> 不可用,原因: ...]`
2. **继续后续步骤**,不要因单工具失败中断
3. **汇总不可用工具**到最终结论,提示用户重跑 `install.sh` 或检查 IAM 权限

## 安装

```bash
bash install.sh
```

幂等可重跑,引导:装 aws CLI v2 + 创建项目级 venv(`~/.local/share/aws-rds-mysql-copilot/venv/`)装 Python 依赖,配置静态 AK/SK,smoke 验证。
