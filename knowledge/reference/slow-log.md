# RDS 慢日志获取与解析

## 慢日志位置

CloudWatch Logs log group:`/aws/rds/instance/<db-instance-id>/slowquery`

需要在参数组里开启:
- `slow_query_log = 1`
- `long_query_time = 1`(秒,推荐 1)
- `log_output = FILE`
- 自动导出 CloudWatch Logs:在 RDS 控制台勾选 Log exports；创建实例时用 `--enable-cloudwatch-logs-exports '["slowquery"]'`,修改实例时用 `--cloudwatch-logs-export-configuration '{"EnableLogTypes":["slowquery"]}'`

## 慢日志格式

每条慢查询是一个 entry,跨 4-N 行:

```
# Time: 2026-06-04T10:00:00Z
# User@Host: app_user[app_user] @ [192.168.1.1] Id: 12345
# Query_time: 2.5 Lock_time: 0.001 Rows_sent: 10 Rows_examined: 100000
SET timestamp=1717488000;
SELECT * FROM users WHERE id = 100;
```

字段含义:
- `Query_time` — 实际查询耗时(秒)
- `Lock_time` — 等锁时间(秒)
- `Rows_sent` — 返回客户端的行数
- `Rows_examined` — 扫描的行数
- `Rows_examined / Rows_sent` 比值高 = 全表扫 / 索引不好

## 拉取方式

- 原生 aws CLI:`aws logs filter-log-events --log-group-name /aws/rds/instance/<id>/slowquery --start-time <ms> --end-time <ms>`
- 我们的封装:`scripts/slow-log.py <db-id> --range 24h --top 20`(自动按 SQL 模板归一化 + 聚合)

## SQL 模板归一化

`slow-log.py` 做的归一:

| 输入 | 归一后 |
|------|--------|
| `WHERE id = 100` | `WHERE id = ?` |
| `WHERE name = 'foo'` | `WHERE name = ?` |
| `WHERE id IN (1, 2, 3)` | `WHERE id IN (?)` |
| `SELECT  *  FROM x` | `SELECT * FROM x` |
| 末尾 `;` | 去掉 |

不做的归一:
- 不识别 hint(`/*+ ... */`)
- 不归一表名 / 列名
- 大小写保留(便于对照原 SQL)

## 排序逻辑

`slow-log.py` 默认按 `count × avg_time` 排序 — 这反映"模板带来的总负载",
而不是单条最慢的查询。如果想看单条最慢,看输出里的 `max_time` 字段。

---

> 校对:2026-06-04,基于 AWS RDS 用户指南 PDF(rds-ug.pdf)。无法从 PDF 验证的项见仓库 issue / 后续真跑 API 验证。
