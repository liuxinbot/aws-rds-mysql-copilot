# AWS RDS 概念速查

## 引擎与版本

- 本 skill 仅覆盖 **RDS for MySQL**
- 版本生命周期:RDS for MySQL 主版本有标准支持 → RDS Extended Support(最多 3 年,付费) → 自动主版本升级,通过 `describe-db-major-engine-versions` 查
- 重要节点:
  - MySQL 5.7 标准支持已于 **2024-02-29** 结束,RDS 扩展支持到 **2027-02-28**(`describe-db-major-engine-versions` 实测确认)
  - MySQL 8.0 标准支持终止日期 **2026-08-01**(在该日期之前 RDS 不会因 Extended Support 计费;之后开始计费)
  - 8.0.33 起 `innodb_log_file_size` 已被 `innodb_redo_log_capacity` 取代;8.4 起默认开启 `innodb_dedicated_server` 自动算 buffer pool / redo capacity

## 实例规格

| 系列 | 用途 |
|------|------|
| db.t* | Burstable,适合开发 / 低负载 |
| db.m* | 通用 |
| db.r* | 内存优化 |
| db.x* | 极大内存 |

实际选型看 PI DBLoad / CPU / Memory 实测。

## 存储类型

| 类型 | 特点 | 推荐场景 |
|------|------|---------|
| gp2 | IOPS 与容量绑定(3 IOPS/GB),有 burst 配额 | 旧实例,逐步迁 gp3 |
| **gp3** ⭐ | IOPS 与容量解耦,可独立买 IOPS,无 burst 不稳定 | 默认推荐 |
| io1 / io2 | 预调配 IOPS；io2 Block Express 支持更高 IOPS/吞吐 | OLTP 高负载 |
| Magnetic(标准存储) | 旧标准磁盘,**已于 2026-04-30 弃用**;2026-04-29 起 AWS 开始强制迁到 gp3;还原磁性卷快照默认存储类型 2026-06-01 起改 gp3 | 不再可选(遇到立即建议迁移) |

## 参数组(Parameter Group)

- `default.mysql8.0` 等是 AWS 默认参数组,**不可改**
- 自定义参数组才能改参数;某些参数(static)改后需重启实例
- `aws rds describe-db-parameters --db-parameter-group-name <name>` 查当前值

## 备份与恢复

- 自动备份(快照)+ 事务日志,可做 PITR(point-in-time recovery)
- 保留期 0-35 天(0 = 关闭自动备份)
- 手动快照不会自动删除
- 跨区域复制需手动配置

## 高可用

- Multi-AZ:同步复制到备 AZ,自动 failover
- 只读副本(Read Replica):异步复制,只读,可跨 region
- ReplicaLag 是只读副本的关键指标

## RDS Proxy

- 连接池中间件,缓解连接风暴
- 使用 Secrets Manager 存储数据库凭证；也支持端到端 IAM 数据库身份验证
- 本 skill 不直接对接 Proxy 监控,但用户可能在用

---

> 校对:2026-06-04,基于 AWS RDS 用户指南 PDF(rds-ug.pdf)。无法从 PDF 验证的项见仓库 issue / 后续真跑 API 验证。
