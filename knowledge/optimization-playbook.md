# AWS RDS 性能优化 playbook

> 性能优化建议的思路指南。**所有具体变更必须标注【需 DBA 审核】**,skill 不发起变更动作。

## 1. 索引建议(基于慢日志 + PI top SQL)

**输入数据**:
- `slow-log <db-id> --range 24h --top 20 --json` — 拿到高频高耗 SQL 模板
- `pi-query <db-id> --top-sql --range 1h` — 验证 PI 视角下负载占比

**分析步骤**:
1. 取 `slow-log` 中 `count × avg_time` 排名前列且 `rows_examined_avg / rows_sent_avg` 比值高的(意味全表扫)
2. 解析 SQL 的 WHERE / JOIN / ORDER BY 列,推导候选索引
3. **先排查冗余/未用索引,再考虑加索引** — 很多库的写入瓶颈是索引太多,不是缺索引:
   - `SELECT * FROM sys.schema_unused_indexes WHERE object_schema NOT IN ('sys','mysql','performance_schema');` — 长期未命中的索引
   - `SELECT * FROM sys.schema_redundant_indexes;` — 前缀重复 / 完全重复索引
   - 如果建议加新索引,同时给出"可考虑同步删除"的列表
4. 用 `aws rds describe-db-instances` 获取引擎版本(决定是否支持降序索引、隐藏索引、函数索引等)
5. 在 MySQL 客户端跑 `EXPLAIN` 验证候选索引能否被命中;**8.0.18+ 用 `EXPLAIN ANALYZE`** 拿到实际执行成本(不仅是估算)

**MySQL 8.0+ 索引特性可考虑**:
- **隐藏索引**(`INVISIBLE`):上线前先用 `INVISIBLE` 创建,确认不影响优化器再 `VISIBLE`,回滚成本低
- **函数索引**:`CREATE INDEX idx ON t ((LOWER(email)));` 可让 `WHERE LOWER(email)=?` 走索引
- **降序索引**:`(col1 DESC, col2 ASC)` 可消除 `ORDER BY` 排序

**在线 DDL 加索引(必须明示)**:
- 优先用 `ALGORITHM=INPLACE, LOCK=NONE`(8.0 加 secondary index 默认就是,但显式写更稳)
- 如果是变列类型 / 主键 / 全文索引等,可能强制 `ALGORITHM=COPY` + 元数据锁,**长事务并发时会卡住**
- 大表加索引耗时与磁盘吞吐相关,**不要给"30-60 分钟"这种凭感觉的估算**;参考公式:`表大小 / EBS 吞吐` 是下界,实际再 ×2-3
- Multi-AZ 实例上加索引会先在备实例做,主切换前不影响主库

**输出格式**:
```sql
-- 表: orders | 命中模板: count=14523, avg=2.3s, rows_ex=850000
-- 同时建议先删冗余索引: idx_status (被新复合索引前缀覆盖)
ALTER TABLE orders
  ADD INDEX idx_status_merchant (status, merchant_id),
  DROP INDEX idx_status,
  ALGORITHM=INPLACE, LOCK=NONE;
-- 预估收益: rows_examined_avg 850000 → ~50, 命中率 ~99%
-- 风险: 写入有轻微影响; orders 表 200GB / gp3 卷,加索引耗时取决于 EBSByteBalance%,实测先在测试环境验证
-- 回滚: ALTER TABLE orders ALTER INDEX idx_status_merchant INVISIBLE; (8.0+,几秒生效,无需删)
-- 【需 DBA 审核】
```

## 2. 参数调优

**输入数据**:`aws rds describe-db-parameters --db-parameter-group-name <pg-name>`

**内存类**(见 `reference/parameters.md`):
- `innodb_buffer_pool_size` — 60-80% 实例内存是经验起点,**记得给 OS / per-thread buffer / binlog cache 留量**;`max_connections × (sort_buffer_size + join_buffer_size + read_buffer_size + …)` 总量不能挤掉 buffer pool,否则会走 swap
- `max_connections` — 与应用连接池总和匹配,留 ~20% buffer;过大会让 per-thread buffer 总量挤占内存
- `tmp_table_size` / `max_heap_table_size` — 配对设置,避免临时表落盘

**InnoDB I/O 三件套(写入性能/持久性权衡的主战场)**:
- `innodb_flush_log_at_trx_commit` — `1` 每事务 fsync redo(默认,持久性最强);`2` 每事务写但每秒 fsync(实例宕机损失最近 1s);`0` 每秒写+fsync(损失最近 1s,且 mysqld crash 也丢) — **对延迟敏感且能容忍 1s 数据丢失的业务可考虑设 2,WriteLatency 通常下降 30-50%**
- `sync_binlog` — `1` 每事务 fsync binlog(默认,主从一致最强);`0` 由 OS flush(crash 时可能丢若干事务但 binlog 与 redo 同步可恢复);**多数业务可设 `100` 或 `1000` 平衡持久性与吞吐**(注意:RDS 启用了 binlog 才生效)
- `innodb_io_capacity` / `innodb_io_capacity_max` — 默认 200/2000,gp3/io2 高 IOPS 卷下偏低,可按 `配额 IOPS × 50-75%` / `配额 IOPS` 设;直接影响脏页 flush 速度,过低会导致 buffer pool 脏页堆积、checkpoint 卡顿
- 三件套放一起评估,不要单调一个

**复制 & 锁**:
- `binlog_format = ROW` — 8.0.34 起 `binlog_format` 已弃用,但建议显式设 ROW;STATEMENT/MIXED 在并发场景下会导致主从不一致
- 事务隔离级别:RDS 默认 `REPEATABLE-READ`(RR),gap lock 多、死锁概率高;**业务侧改 `READ-COMMITTED`(RC)经常能显著降死锁,代价是 binlog 必须是 ROW**
- `innodb_lock_wait_timeout` — 默认 50s,锁竞争多的库可降到 5-10s 让阻塞快速失败,业务侧重试

**日志/可观测性**:
- `slow_query_log` / `long_query_time` — 必须开启,推荐 `long_query_time=1`
- `performance_schema` — PI 依赖,让 PI 自动管理(改成 user 来源会导致 PI 不再自动接管)
- `log_queries_not_using_indexes` — 默认 0;新业务上线初期可短期开启发现问题,但量大时会让慢日志变噪音

**判断方法**:
- 与默认值 / 推荐值对比(`describe-engine-default-parameters` 拿默认基线)
- 结合实际 workload 的 PI 数据判断是否需要调(脏页等待、redo 等待、锁等待是否存在)
- **buffer_pool_size 在线变更**(`SET GLOBAL innodb_buffer_pool_size=...`)会触发 chunk 调整窗口,期间业务延迟有抖动 — 通常建议低峰期改并 reboot 落定
- 给修改建议时同时说明:**新值 / 是否需要 reboot / 影响哪些指标 / 回滚方法**

## 3. SQL 重写建议

**仅对慢日志里 top N 模板做**,且必须有数据支撑(EXPLAIN 结果 / 执行次数 / 扫描行数)。
不基于猜测改写 SQL。

**常见可优化模式**:
- `SELECT *` → 显式列(尤其有 BLOB/TEXT 大列时,可显著降网络 + sort_buffer 占用)
- `LIKE '%xxx'`(前缀通配)→ 全文索引(InnoDB FULLTEXT)或反查列(存反向字符串)
- 大 OFFSET 分页(`LIMIT 100000, 20`)→ 游标分页(`WHERE id > last_id ORDER BY id LIMIT 20`)
- `IN (...)` 列表过长 → 拆批 / 用临时表 JOIN
- 子查询 → JOIN(MySQL 5.7 优化器较弱;8.0 SEMI-JOIN/HASH JOIN 显著改善,可保留子查询写法)
- `OR` 条件命中不同索引 → 拆 `UNION ALL`(让每个分支走各自索引)
- `WHERE func(col) = ?` → 改 `WHERE col = inv_func(?)`,或建函数索引(8.0+)
- `ORDER BY` 后接 `LIMIT N` 但走文件排序 → 加 `(filter_col, order_col)` 复合索引让排序消除

**Schema 设计层(慢日志解决不了的问题)**:
- 表里有大 BLOB/TEXT 但常查的是其他列 → 拆冷表(BLOB 单独一张表,主键关联)
- 单表 > 500GB / 行数 > 5 亿 → 考虑分区表(RANGE/HASH)或归档冷数据
- 写热点(自增主键 + 高并发 INSERT)→ 改 UUIDv7 / 雪花 ID 但保有序;或 `AUTO_INCREMENT` + `innodb_autoinc_lock_mode=2`
- 高频更新的小表 + 大量读副本延迟敏感 → 考虑做 ProxySQL/RDS Proxy 路由读请求到主

## 4. 容量与版本

**存储类型**:
- `gp2` — IOPS 与容量绑定,3 IOPS/GB,有 burst 配额(BurstBalance 监控);credit 耗尽后只剩 baseline
- `gp3` ⭐推荐 — IOPS 与容量解耦,性价比高,无 burst 不稳定;关注 `EBSByteBalance%/EBSIOBalance%`
- `io1` / `io2` — 高 IOPS 场景,贵;`io2 Block Express` 支持更高 IOPS/吞吐
- **Magnetic(标准存储)** — 已于 2026-04-30 弃用,2026-04-29 起 AWS 强制迁 gp3;遇到立即给迁移建议
- 现有 gp2 实例若 IOPS 经常打满或 BurstBalance 低位,**优先建议升级到 gp3**(可在线,无需停机)

**实例规格**(基于 PI DBLoad / CPU / Memory):
- 看 **P95 / P99 + 突发模式**,不看均值 — DBLoad 均值 < vCPU/2 但 P95 > vCPU 的实例,降配会在峰值时炸
- 推荐看至少 7-14 天的负载分布(覆盖工作日 + 周末 + 月初/月末);`pi-query --range 14d --top-wait` 拿等待事件分布
- **降配判定**:P95 DBLoad < vCPU/2 且无突发 P99 > vCPU,才能降;且需评估降配后内存是否还够 buffer pool
- **升配判定**:DBLoad P95 接近 vCPU 数 / 持续 P95 > vCPU → 优化 SQL 优先,SQL 已优化无空间再升配
- **burstable 实例特殊**:t3/t4g 看 CPUCreditBalance 而不是只看 CPU%;credit 经常耗尽就该改 m/r 系列
- Multi-AZ 实例升降配:先在备实例做、然后 failover,业务感知一次 ~30-60s 切换

**引擎版本与升级**:
- 检查是否在 EOL / 即将 EOL(`describe-db-major-engine-versions` 看 LifecycleSupportEndDate)
- 当前关键节点:
  - **MySQL 8.0 标准支持终止 2026-08-01**(在此之前 RDS 不收 Extended Support 费用,之后开始计费)
  - MySQL 5.7 标准支持已结束(2024-02-29),扩展支持到 2027-02-28,优先升 8.x
- 升级路径:同主版本(5.7.x → 5.7.最新)→ 跨主版本(5.7 → 8.0 → 8.4);**5.7 不能直接升 8.4**

**升级工作流(强烈推荐 RDS Blue/Green Deployment)**:
- `aws rds create-blue-green-deployment` — 创建一个与生产同步复制的绿色环境
- 在绿环境上执行升级 / 参数变更 / Schema 修改 / 实例规格变更
- 测试通过后用 `switch-over` 一键切换(典型 < 1 分钟,DNS endpoint 自动切),失败可立刻回滚
- **Blue/Green 是 5.7 → 8.0 跨大版本升级的标准做法**,降低单次升级失败的全量回滚成本
- 跨主版本前还要跑 MySQL 上游 `mysqlcheck --check-upgrade` 做兼容性扫描(orphan FK、deprecated reserved word 等)

## 输出建议结构

每个建议输出时遵循结构:
```
[问题]
基于 <数据源> 看到 <现象>(具体数值 + 时间窗口)

[建议]
<可执行动作 / SQL>

[收益预估]
<量化预估,基于现有指标推算>

[风险与代价]
<执行影响,如锁表时间、回滚成本、reboot 需要等>

【需 DBA 审核】
```
