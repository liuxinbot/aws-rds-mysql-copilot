# AWS RDS 诊断 playbook

> 给 AI 看的"DBA 排查思路指南"。**不是决策树,允许根据现场自由编排工具**;但每次诊断必须能引用本指南的"标准 5 步法"和"护栏"。

## 标准排查流程(推荐)

DBA 日常排障的通用方法论,默认按以下 6 步推进(Step 0 是最常被 AI 忽略、但 DBA 真实习惯的第一动作)。允许 AI 根据现场实际情况调整 / 跳步,但每步的产出物必须在最终结论里明确呈现。

0. **控制面对账** — 先看是否是"AWS 自己干的事 / 人为变更"造成的:
   - `aws rds describe-events --source-identifier <db-id> --duration <分钟>` 看实例事件流(failover / 维护窗口 / storage autoscale / parameter-change / read-replica 状态)
   - `aws rds describe-db-parameters --source user --db-parameter-group-name <pg>` 对比近期参数组改动
   - `aws rds describe-db-instances --db-instance-identifier <db-id>` 看当前规格 / 存储类型 / Multi-AZ / Engine 版本是否近期改过
   - **DBA 经验**:50%+ 的"突发问题"是 events 第一行就能解释的(failover、维护重启、自动扩容、参数生效) — 不先看 events 直接埋头查指标是浪费时间
1. **指标采集** — 用 `metrics-batch` / `aws cloudwatch get-metric-statistics` /
   `pi-query` 拿一组相关指标(关注异常窗口)
2. **异常定位** — 在采集到的数据里圈出偏离基线 / 阈值的指标(支持环比 `--compare 1d` / 同比)
3. **假设缩窄** — 基于 Step 2 异常类型选下一步证据来源,**不要默认就奔执行计划**:
   - SQL/CPU 类异常 → PI top SQL + `slow-log` + EXPLAIN
   - 锁/事务类 → `information_schema.innodb_trx` + `performance_schema.events_waits_current` + PI wait events
   - IO/存储类 → IOPS/Latency 分布 + 卷类型 + binlog/临时表占用 + storage autoscale 历史
   - 复制类 → `SHOW SLAVE STATUS` + binlog 流量 + 主库长事务/DDL + 副本规格对称性
   - 内存/连接类 → SwapUsage + per-thread-buffer 估算 + PI by user/host
4. **根因判定** — 基于 0-3 步证据交叉验证,给出根因(避免单指标定论)
5. **修复方案输出** — 给出可执行建议(变更必须标注【需 DBA 审核】),并附预估收益 / 风险

## 通用排查原则

- **控制面变更优先排除** — Step 0 看 events / 参数组改动,很多"突发"是人为/AWS 自动操作引起
- **收敛时间窗口 / 影响面** — 第一步把问题限定到一个明确窗口
- **核对告警类型 → 选起手指标** — 用最贴切的入口指标开始,而不是泛泛把所有指标都拉
- **横向看 + 纵向看** — 横向:同一 RDS 多指标关联;纵向:对比基线 / 环比
- **锁定到具体 SQL / 事件 / 变更** — 别停在"指标异常",一定追到具体动作

## 指标读法陷阱(AI 最容易误判的地方)

| 表象 | 直觉解读 | DBA 实际解读 |
|------|---------|--------------|
| `CPUUtilization` 100%,burstable 实例(t3/t4g) | "CPU 不够,需要升配" | 多半是 **CPUCreditBalance 耗尽**,不是真 CPU bound;先看 credit 余额、考虑切非 burstable 规格(m/r) |
| `FreeableMemory` 持续低位 | "内存不足" | 不一定 — InnoDB 倾向把 buffer pool 填满,这是健康表现;**只有 `SwapUsage > 0` 才是真内存压力** |
| `ReadIOPS` 飙高 + `ReadLatency` 平稳 | "IO 压力大" | 通常是好事 —— 缓存命中良好,IO 完成快;**反向(IOPS 平稳但 Latency 飙)才是真问题** |
| `DatabaseConnections` 高位但稳定 | "连接数压力大" | 单看绝对值意义不大,要对比 `max_connections`、看趋势、看是否有 RDS Proxy pinning |
| `WriteLatency` 单独高 | "磁盘写慢" | 常见原因是 `sync_binlog=1` + `innodb_flush_log_at_trx_commit=1` 双 fsync;不是 EBS 慢 |
| `BurstBalance` 满(=100%) | "存储 IO 没问题" | 这是 gp2 才有的指标,**gp3 实例没有 burst 概念**;gp3 看 `EBSByteBalance%/EBSIOBalance%` |
| `ReplicaLag = 0` | "复制健康" | 也可能是副本**没在跑**(IO_THREAD/SQL_THREAD 停);要交叉 `SHOW SLAVE STATUS` |
| `FreeStorageSpace` 充足 | "磁盘没满" | binlog 占同一 EBS 卷但**不计入** FreeStorageSpace,binlog 暴涨能让实例 stuck;要单独看 `BinLogDiskUsage` |
| 单时刻 `SHOW PROCESSLIST` 看到很多查询 | "并发高" | processlist 是瞬时快照,**不能等同于负载**;PI 的 DBLoad / AAS 才是真实负载衡量 |
| PI wait events 中 `CPU` 占大头 | "CPU 瓶颈" | 在 PI 语义里 `CPU` = "无等待,正在跑",CPU 占大头说明 **SQL 执行效率问题**(比如全表扫),不一定是机器 CPU 不够 |

## 常见症状起手清单

| 症状 | 起手查 | 重点工具 / 漏项提醒 |
|------|--------|---------|
| 慢 SQL 突增 | PI top SQL → 慢日志模板归一 | `pi-query --top-sql`、`slow-log`;注意先看 events 排除参数变更 |
| 连接数突增 | DatabaseConnections + PI by user/host | `metrics-batch`、`pi-query --slice-by user`;注意区分应用泄漏 vs RDS Proxy pinning(`DatabaseConnectionsCurrentlySessionPinned`) |
| CPU 飙高 | PI by sql/wait + DBLoad | `pi-query --top-sql / --top-wait`;**burstable 实例先看 `CPUCreditBalance`,credit 耗尽时降速不是"真 CPU bound"** |
| 主从延迟 | ReplicaLag + binlog 流量 + 长事务/DDL | `metrics-batch`、`pi-query`;**漏项**:大事务 / online DDL 阻塞 IO_THREAD、副本规格/存储不对称、网络打满 |
| 磁盘满 | FreeStorageSpace 趋势 + binlog 保留 + ibd 增长 | `describe-db-instances`、`metrics-batch`;**漏项**:binlog 占同一 EBS 但**不计入** FreeStorageSpace、ibdata1 不可缩、临时表落盘、表碎片 |
| 存储 IOPS 打满 | ReadIOPS/WriteIOPS + 卷类型(gp2/gp3/io1/io2) | `describe-db-instances`、`metrics-batch`;**gp2 实例先看 `BurstBalance`(credit 耗尽时只剩 baseline IOPS)** |
| 内存压力 | **SwapUsage 优先于 FreeableMemory** + PI wait events | `metrics-batch`、`pi-query --top-wait`;FreeableMemory 低位**不一定**是问题,SwapUsage > 0 才是 |
| 锁/死锁 | PI wait events lock 类 + 长事务 + 隔离级别 | `pi-query --top-wait`、`SHOW ENGINE INNODB STATUS`;RR 隔离级别下 gap lock 多,RC 下死锁可显著减少 |
| 实例突然重启 / 不可用 | **先看 events**(failover / OOM / 维护) | `aws rds describe-events`;再交叉 CPU / Memory / Disk / Replica |
| 备份/PITR 异常 | BackupRetentionPeriod + binlog 保留 + 自动备份是否被关 | `describe-db-instances`(`BackupRetentionPeriod=0` 直接关闭 binlog) |

## 给 AI 的护栏

1. **不要凭 1 个指标下结论**,至少交叉验证 2 个
2. **给结论时引用数据**(具体数值 + 时间窗口),不要笼统说"CPU 高"
3. **不知道的承认不知道**,不要编 SQL 改写建议或编造数据
4. **任何"建议变更"必须标注【需 DBA 审核】**;skill 当前为只读范围,绝不发起变更动作
5. **优先沿用 0-5 步流程**,跳步必须解释为什么跳(尤其 Step 0 几乎不该跳)
6. **核对"指标读法陷阱"表**,避免把 burstable credit 耗尽误判为 CPU bound、把 FreeableMemory 低位误判为内存不足之类的常见错

## 样例诊断流程(参考)

用户:"my-db CPU 飙到 95%,什么情况?"

```
[Step 0 控制面对账]
$ aws rds describe-events --source-identifier my-db --duration 120
→ 近 2h 无事件(无 failover / 无参数变更 / 无维护)
$ aws rds describe-db-instances --db-instance-identifier my-db \
    --query 'DBInstances[0].{Class:DBInstanceClass,Storage:StorageType}'
→ db.r6g.xlarge / gp3 — 非 burstable,可排除 CPU credit 耗尽场景
排除:控制面变更 / burstable credit 耗尽

[Step 1 指标采集]
$ metrics-batch my-db --preset health --range 30m --compare 1d --json
→ CPUUtilization 当前 P95=95%,昨日同时段 P95=35%,日环比 +170%
  DatabaseConnections 正常,FreeableMemory 正常,SwapUsage=0

[Step 2 异常定位]
明显 CPU 单点突增,无连接数 / 内存伴随异常 → 倾向 SQL 层面问题

[Step 3 假设缩窄 → 走 SQL/CPU 路径]
$ pi-query my-db --top-sql --range 30m
→ #1 SQL avg_load=45.2:  SELECT * FROM orders WHERE status = ? AND merchant_id = ?
   (执行频率 800/min,预估在做大量扫描)
$ pi-query my-db --top-wait --range 30m
→ CPU 占比 85% (PI 语义:无等待事件,在跑 SQL — 进一步坐实 SQL 效率问题)
$ slow-log my-db --range 30m --top 5
→ 上述模板 count=23000 max=4.2s rows_examined_avg=850000(全表扫)
(在 MySQL 客户端执行)EXPLAIN SELECT ... → type=ALL,无索引

[Step 4 根因判定]
orders 表 (status, merchant_id) 组合查询无索引,应用突增的查询导致全表扫,
CPU 因 buffer pool 反复加载页面 + 大量比较而飙高
(交叉证据:Step 0 无控制面变更、Step 2 单维度异常、Step 3 PI+slow-log+EXPLAIN 一致)

[Step 5 修复方案]
建议在低峰期添加复合索引(在线 DDL,INPLACE 模式,锁元数据短暂):
  ALTER TABLE orders ADD INDEX idx_status_merchant (status, merchant_id), ALGORITHM=INPLACE, LOCK=NONE;
预估收益:rows_examined_avg 850000 → 数百量级,CPU 应回落到 30% 区间
风险:200GB 表加索引耗时与磁盘吞吐相关,gp3 卷预估 1-2h(参考实测,不是 30-60min);
     期间写入会有轻微影响,完成前不要做规格变更
【需 DBA 审核】
```
