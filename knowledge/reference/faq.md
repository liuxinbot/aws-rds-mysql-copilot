# AWS RDS FAQ

## 通用

**Q:RDS for MySQL 和自建 MySQL 有啥不一样?**
- RDS 是 managed 服务,AWS 帮你管 OS / 备份 / patch
- 不能 SSH 登实例,不能改文件
- 部分参数被 AWS 锁死(如 sql_mode 的某些值)
- 主用户名创建时指定；控制台教程常用 `admin`,但可自定义
- 必须经过 AWS 提供的 endpoint 访问

**Q:为啥实例可用性不达标?**
- 看 RDS Events(`aws rds describe-events`)
- 看 Multi-AZ 配置,单 AZ 实例的 SLA 较低
- failover 期间会短暂不可用

## 监控

**Q:CloudWatch 数据延迟?**
- RDS 指标默认 1 分钟粒度
- 实际写入 CloudWatch 有 1-2 分钟延迟
- 紧急排查不要看最新 1 分钟,看过去 5 分钟趋势

**Q:Enhanced Monitoring 跟 PI 有啥区别?**
- Enhanced Monitoring:OS 层细粒度指标(秒级,CPU/内存/进程),需开
- Performance Insights:数据库内核层(SQL / wait event)
- 两者互补,生产建议都开

## 连接

**Q:DatabaseConnections 跟 max_connections 的关系?**
- DatabaseConnections 是当前活跃连接数
- max_connections 是上限,默认按内存公式计算
- 一旦达到上限,新连接被拒绝(报 too many connections)

**Q:连接数突增怎么排查?**
- `pi-query --slice-by user` 看是哪个用户
- `pi-query --slice-by host` 看是哪台主机
- 看应用是否泄漏(连接池配置 / 没正确 close)

## 故障

**Q:实例自动重启了?**
- `aws rds describe-events --source-identifier <db-id>` 看事件流
- 常见原因:OOM、磁盘满、AZ failover、维护窗口

**Q:磁盘满了怎么办?**
- 立刻看 binlog 占用(BinLogDiskUsage)、慢日志占用、临时表
- 长期方案:开启 storage autoscaling
- 紧急扩容:`aws rds modify-db-instance --allocated-storage <new-gb> --apply-immediately`(不重启)

## CLI 性能

**Q:`aws rds describe-db-instances` 很慢、卡住几分钟?**

大概率是用了 `--query "DBInstances[?Engine=='mysql']"` 这种**客户端过滤**。`--query` 是 JMESPath 表达式,在 CLI 客户端跑 — 服务端会先返回**所有引擎**(MySQL / PG / DocDB / Oracle...)的全量实例,客户端再过滤。账号下实例多时,网络传输 + 分页 + 解析能耗几分钟。

正确做法用**服务端过滤** `--filters`:

```bash
# ✅ 服务端过滤,只返回 MySQL
aws rds describe-db-instances \
    --filters Name=engine,Values=mysql \
    --query "DBInstances[].DBInstanceIdentifier" \
    --output text --no-cli-pager
```

```bash
# ❌ 全量下载 + 客户端过滤,大账号秒级飙到分钟级
aws rds describe-db-instances \
    --query "DBInstances[?Engine=='mysql'].DBInstanceIdentifier" \
    --output text
```

更进一步:`--filters` 支持的 key 见 [RDS API DescribeDBInstances](https://docs.aws.amazon.com/AmazonRDS/latest/APIReference/API_DescribeDBInstances.html) 的 `Filters` 段(engine / db-instance-id / db-cluster-id / dbi-resource-id 等)。

**Q:输出超过一屏弹了 `less` 怎么关?**

按 `q` 退出 less。永久关:`~/.aws/config` 加 `cli_pager =`(空值)。install.sh 写的 config 已默认带这一行(2026-06-04 之后版本)。

---

> 校对:2026-06-04,基于 AWS RDS 用户指南 PDF(rds-ug.pdf)。无法从 PDF 验证的项见仓库 issue / 后续真跑 API 验证。
