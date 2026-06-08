# Performance Insights 使用指南

## 是什么

AWS RDS 的内核级性能分析功能,采集数据库的 active sessions(Performance Insights 每秒采样 DBLoad),
按多个维度切分(SQL / wait event / user / host / database / application)。

核心指标 `db.load.avg` = 平均活跃会话数(AAS)。

## 开启

```bash
aws rds modify-db-instance \
    --db-instance-identifier <db-id> \
    --enable-performance-insights \
    --apply-immediately
```

或在创建实例时勾选 PI。开启后等 5-10 分钟有数据。

## 关键 API

- `pi:GetResourceMetrics` — 拿时序数据,可按维度 GroupBy
- `pi:DescribeDimensionKeys` — 列维度可用值
- 我们的 `scripts/pi-query.py` 封装了最常用的三种 case

## 三种典型查询

### Top SQL by load(找最吃负载的 SQL)

```bash
pi-query <db-id> --top-sql --range 1h --limit 10
```

输出按 `db.load.avg` 总和排序的 top SQL 模板(已 tokenize)。

### Top wait events(看负载分布在哪些等待上)

```bash
pi-query <db-id> --top-wait --range 1h
```

常见等待:
- `wait/io/file/innodb/innodb_data_file` — IO 瓶颈
- `wait/synch/mutex/sql/LOCK_open` — 元数据锁
- `wait/io/file/sql/binlog` — binlog 写盘
- `wait/lock/table/sql/handler` — 行锁
- `CPU` — 纯 CPU,无等待

### 按维度切分(看 load 集中在哪个用户/应用)

```bash
pi-query <db-id> --slice-by user --range 1h
pi-query <db-id> --slice-by host --range 1h
pi-query <db-id> --slice-by app --range 1h
pi-query <db-id> --slice-by database --range 1h
```

## 注意事项

- **必须先开 PI** — 未开实例的 `pi-query` 会报错退出
- **保留期 / EOL** — 默认免费 7 天；旧 PI 灵活保留期 1-24 月、PI 控制台体验及关联定价将在 2026-06-30 后 EOL；不升级时实例默认进入 Database Insights 标准模式,可能只能访问 7 天历史
- **Database Insights 高级模式** — 2026-06-30 后执行计划和按需分析只在高级模式支持；高级模式保留期为 15 个月
- **PI API 不会消失** — 可以放心继续用 `pi:GetResourceMetrics`

---

> 校对:2026-06-04,基于 AWS RDS 用户指南 PDF(rds-ug.pdf)。无法从 PDF 验证的项见仓库 issue / 后续真跑 API 验证。
