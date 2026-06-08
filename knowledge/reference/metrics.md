# CloudWatch RDS 指标速查

> Namespace: `AWS/RDS`,Dimension: `DBInstanceIdentifier`
> 默认采样间隔:1 分钟；RDS 用户指南确认 60 秒数据点可用 15 天

## 巡检 8 项核心指标

| 指标 | 单位 | 含义 | 关键阈值 |
|------|------|------|---------|
| `CPUUtilization` | % | CPU 使用率 | P95 > 85% critical |
| `DatabaseConnections` | count | 客户端网络连接数(不等同于数据库会话总数) | > max_connections * 90% critical |
| `FreeableMemory` | bytes | 可用内存 | < 总内存 * 10% critical |
| `FreeStorageSpace` | bytes | 可用磁盘 | < 总容量 * 15% critical |
| `ReadIOPS` + `WriteIOPS` | count/s | 读写 IOPS | > 配额 * 90% critical |
| `ReadLatency` + `WriteLatency` | s | IO 延迟 | P95 > 30ms critical |
| `NetworkReceiveThroughput` + `NetworkTransmitThroughput` | bytes/s | 网络吞吐 | 持续打满规格 critical |
| `ReplicaLag` | s | 副本延迟 | > 30s critical |

## 其他常用指标

- `BinLogDiskUsage` — binlog 占用磁盘空间(MySQL)
- `SwapUsage` — swap 使用量,大于 0 即可疑
- `DiskQueueDepth` — 等待访问磁盘的未完成 I/O 请求数,单位 count；持续升高表示 IO 压力
- `BurstBalance` — gp2 卷 burst bucket 中剩余 I/O credits 百分比
- `EBSByteBalance%` / `EBSIOBalance%` — EBS 优化实例突发吞吐 / IOPS 余额百分比,不同于 `BurstBalance`

## 指标拉取方式

- 单指标:`aws cloudwatch get-metric-statistics --namespace AWS/RDS --metric-name CPUUtilization --dimensions Name=DBInstanceIdentifier,Value=<id> --start-time ... --end-time ... --period 60 --statistics Average Maximum`
- 批量(巡检):`scripts/metrics-batch.py <id> --preset health --compare 1d --json`

## 指标 vs PI 数据的区别

| | CloudWatch | Performance Insights |
|---|-----------|---------------------|
| 颗粒度 | 实例 / 集群级 | SQL / 等待事件 / 用户级 |
| 周期 | 60s | 1s 采样,1m 聚合 |
| 范围 | 基础设施 + 部分内核 | 数据库内核负载分布 |
| 适合 | 阈值告警 / 巡检 | 根因定位 / SQL 优化 |

---

> 校对:2026-06-04,基于 AWS RDS 用户指南 PDF(rds-ug.pdf)。无法从 PDF 验证的项见仓库 issue / 后续真跑 API 验证。
