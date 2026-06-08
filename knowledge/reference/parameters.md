# RDS MySQL 参数与默认值偏离判断

## 重点参数清单

| 参数 | 推荐值 | RDS 默认值 | 备注 |
|------|--------|-----------|------|
| `innodb_buffer_pool_size` | 实例内存 60-80% | MySQL 8.0 及以下:`{DBInstanceClassMemory*3/4}`;MySQL 8.4 由 `innodb_dedicated_server` 自动按内存档位设(<1GB→128MB / 1-4GB→×0.5 / >4GB→×0.75) | 静态,改后需重启 |
| `max_connections` | 应用池总和 + 20% buffer | MySQL: `{DBInstanceClassMemory/12582880}`(允许范围 1–100000)。**MySQL 公式不带 LEAST 上限**(LEAST cap 是 PostgreSQL/MariaDB 才有) | 动态 |
| `innodb_log_file_size` | 256M-1G(仅 MySQL 8.0.32 及以下) | 8.0.32 及以下默认 128M | **MySQL 8.0.33 起改用 `innodb_redo_log_capacity`**(默认 2GB),不再使用本参数 |
| `innodb_redo_log_capacity` | 默认值通常足够;大写入负载可调高 | 8.0.33+ 默认 2GB;8.4 由 `innodb_dedicated_server` 按 (vCPU/2)GB 自动扩展,最大 16GB | 动态;取代 `innodb_log_file_size × innodb_log_files_in_group` |
| `tmp_table_size` | 64M | 16M | 与 max_heap_table_size 配对 |
| `max_heap_table_size` | 64M | 16M | 与 tmp_table_size 配对 |
| `slow_query_log` | 1 | 0 | 必须开 |
| `long_query_time` | 1 | 10 | 推荐 1 秒 |
| `log_queries_not_using_indexes` | 0 / 1 看场景 | 0 | 开会噪音多 |
| `performance_schema` | 让 PI 自动管理 | PI 开启时推荐 System default | 手工改成 user 来源后 PI 不再自动管理 |
| `binlog_format` | ROW | MySQL 8.0 及以下默认 MIXED；8.4+ 默认 ROW | 动态；8.0.34 起已弃用,新复制建议 ROW |
| `binlog_expire_logs_seconds` | 7 天 = 604800 | 不同版本不同 | 太短是否影响 PITR 待核对；先按复制/binlog 保留风险处理 |

## 参数类型

- **dynamic** — 改后即生效,无需重启
- **static** — 改后必须重启实例 / 故障转移才生效

```bash
aws rds describe-engine-default-parameters \
    --db-parameter-group-family mysql8.0 \
    --query 'EngineDefaults.Parameters[?ParameterName==`innodb_buffer_pool_size`]'
```

## 偏离判断流程

1. 拿当前参数组所有非默认参数:`aws rds describe-db-parameters --db-parameter-group-name <name> --source user`
2. 对比上述清单,挑明显异常的(如 buffer_pool_size 远小于 60%、long_query_time > 5)
3. 给修改建议时一定带:**新值、是否需要 reboot、回滚方法**

## 公式参数

RDS 默认参数大量使用公式(基于实例规格自动计算),如:
- `innodb_buffer_pool_size = {DBInstanceClassMemory*3/4}`(MySQL 8.0 及以下)
- `max_connections = {DBInstanceClassMemory/12582880}`(RDS for MySQL,允许范围 1–100000;不带 LEAST 上限)
- `DBInstanceClassMemory` 为字节数,且会减去 OS 与 RDS 进程预留内存(因此实际 `max_connections` 比 `内存/12582880` 略小)

改成固定值时需小心 — 升降配后这些固定值不会自动调整。

## 待 API 验证

- `tmp_table_size` / `max_heap_table_size` 的 RDS 默认值(PDF 未列;表中沿用 MySQL 上游默认 16M)
- `binlog_format` 在 RDS for MySQL 8.0 参数组的默认值(PDF 仅说明 8.0.34 起被弃用,未直接列默认值;以 `describe-engine-default-parameters` 输出为准)
- `binlog_expire_logs_seconds` 对 PITR 的实际影响
- 各参数 static/dynamic 完整标注(本表只覆盖重点项,完整以 API `IsModifiable` / `ApplyType` 字段为准)

---

> 校对:2026-06-04,基于 AWS RDS 用户指南 PDF(rds-ug.pdf)。无法从 PDF 验证的项见仓库 issue / 后续真跑 API 验证。
