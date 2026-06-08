# 变更日志

中文 | [English](CHANGELOG.md)

## 0.1.0 - 2026-06-08

首次开源发布。

### 新功能

- 三种工作模式:问答、巡检、诊断(详见 [SKILL.md](SKILL.md))
- 8 项健康度巡检,基于 `knowledge/inspection.yaml`,critical 项用 `on_critical_hint` 给提示,不强制跳诊断
- Markdown 诊断 playbook(`knowledge/diagnosis-playbook.md`)— AI 在 5 步法框架内自由编排工具,而不是按死板决策树 yaml 执行
- 性能优化 playbook(`knowledge/optimization-playbook.md`)— 索引建议 / 参数调优 / SQL 重写 / 容量与版本升降配
- 领域知识库 `knowledge/reference/` — 概念、CloudWatch 指标、Performance Insights 指南、慢日志格式、参数清单、FAQ
- 三个 Python 工具,全部带 venv self-bootstrap:`metrics-batch.py`(批量 CloudWatch + 环比 + p95)、`slow-log.py`(慢日志 + SQL 模板归一化)、`pi-query.py`(Performance Insights — top-sql / top-wait / slice-by)
- 幂等的 `install.sh` — 装 aws CLI v2、创建项目级 venv 在 `~/.local/share/aws-rds-mysql-copilot/venv/`、引导填 AK/SK、跑 smoke、建 skill 软链
- `uninstall.sh` — 删软链 + venv,共享文件提示不动

### 文档

- 双语 README(`README.md` 中文,`README.en.md` English)
- 最小只读 IAM policy 与详细说明(`docs/iam-readonly-policy.json` + `docs/iam-readonly-policy.md`)
- Apache 2.0 协议
