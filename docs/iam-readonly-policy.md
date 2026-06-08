# IAM Policy 说明

附加给 aws-rds-mysql-copilot 使用的 IAM user。

**全只读**,无任何写 / 创建 / 修改 / 删除动作。

## 一键附加

### 命令行

```bash
aws iam put-user-policy \
    --user-name <YOUR_USER_NAME> \
    --policy-name aws-rds-mysql-copilot-readonly \
    --policy-document file://docs/iam-readonly-policy.json
```

### Console

IAM → Users → 选 user → Permissions → Add inline policy → JSON 标签页 → 粘贴 [iam-readonly-policy.json](iam-readonly-policy.json) → Name `aws-rds-mysql-copilot-readonly` → Create policy

## 每组 action 用途

### 1. RDSReadOnly:`rds:Describe*` + `rds:ListTagsForResource`

| 命令 / 脚本 | 用到的 action |
|------------|--------------|
| `aws rds describe-db-instances` | DescribeDBInstances |
| `aws rds describe-db-parameters` | DescribeDBParameters |
| `aws rds describe-events` | DescribeEvents |
| `aws rds describe-db-engine-versions` | DescribeDBEngineVersions |
| `aws rds describe-db-major-engine-versions` | DescribeDBMajorEngineVersions |
| `aws rds describe-engine-default-parameters` | DescribeEngineDefaultParameters |
| `pi-query.py` 内部(取 DbiResourceId) | DescribeDBInstances |

**为什么 Resource 是 `*`?** RDS 的 Describe* 多数 API 不支持 resource-level ARN(AWS 官方设计限制)。

### 2. CloudWatchMetricsRead

| 命令 / 脚本 | 用到的 action |
|------------|--------------|
| `metrics-batch.py`(批量拉 + 环比 + p95) | GetMetricStatistics |
| 问答模式 `aws cloudwatch get-metric-statistics` | GetMetricStatistics |
| 巡检 `metrics-batch <id> --preset health --compare 1d` | GetMetricStatistics |
| `aws cloudwatch describe-alarms` | DescribeAlarms |

### 3. CloudWatchLogsReadForSlowQuery

| 命令 / 脚本 | 用到的 action |
|------------|--------------|
| `slow-log.py`(拉 RDS 慢日志) | FilterLogEvents |
| `aws logs filter-log-events --log-group-name /aws/rds/instance/<id>/slowquery` | FilterLogEvents |

**Resource 收敛**:`arn:aws:logs:*:*:log-group:/aws/rds/instance/*:*`

- `/aws/rds/instance/*` 是 log group name 通配符,只匹配 RDS 实例的 log group(slowquery / general / error / audit)
- **末尾 `:*` 必需** —— 这是 log-group ARN 完整格式的 stream wildcard,缺了 `FilterLogEvents` 会被 IAM 拒绝
- 不开放整个 CloudWatch Logs 读权限,降低横向访问风险

### 4. PerformanceInsightsRead

| 命令 / 脚本 | 用到的 action |
|------------|--------------|
| `pi-query.py --top-sql / --top-wait / --slice-by` | GetResourceMetrics |
| 维度查询(后续可能用) | DescribeDimensionKeys / GetDimensionKeyDetails / ListAvailableResourceMetrics |

**前提**:实例必须开启 Performance Insights(`aws rds modify-db-instance --enable-performance-insights`)。否则 `pi-query.py` 直接 exit 3 + 给提示。

### 5. STSCallerIdentity

| 命令 / 脚本 | 用到的 action |
|------------|--------------|
| `install.sh` smoke | GetCallerIdentity |

仅用于安装末尾验证凭证链路可用,无实际数据访问。

## 管理员排查 explicit deny 来源

如果用户撞到 `explicit deny in an identity-based policy`:

```bash
# user 直接挂的 inline policy
aws iam list-user-policies --user-name <USER>

# user 直接挂的 managed policy
aws iam list-attached-user-policies --user-name <USER>

# user 所在 group 的 policy(group 上挂的 policy 也会继承)
aws iam list-groups-for-user --user-name <USER>

# permission boundary(常见 deny 来源,优先级最高)
aws iam get-user --user-name <USER>

# AWS Organizations SCP(若启用,在 org 主账号下查)
aws organizations list-policies-for-target --target-id <ACCOUNT_ID> \
    --filter SERVICE_CONTROL_POLICY
```

## 收紧 Resource(可选)

如果安全策略要求把 Resource 限到特定 account / region:

| Sid | 当前 Resource | 可否收紧 | 收紧示例 |
|-----|--------------|---------|---------|
| RDSReadOnly | `*` | ❌ API 不支持 resource-level | — |
| CloudWatchMetricsRead | `*` | ❌ API 不支持 resource-level | — |
| CloudWatchLogsReadForSlowQuery | `arn:aws:logs:*:*:log-group:/aws/rds/instance/*:*` | ✅ 可限 region / account | `arn:aws:logs:us-east-1:<account-id>:log-group:/aws/rds/instance/*:*` |
| PerformanceInsightsRead | `*` | ⚠️ 部分 API 支持 ARN,但 `pi:GetResourceMetrics` 用 RDS DbiResourceId,不是标准 ARN,通常保持 `*` | — |
| STSCallerIdentity | `*` | ❌ 该 action 无 resource | — |

## 安全性备注

- **全只读**:不含任何 Create/Modify/Delete/Reboot/Failover 等写动作
- 即使 IAM user 被攻破,攻击者**不能**改 RDS / 删数据 / 修改参数
- skill 设计上也有"变更必须标注【需 DBA 审核】"的护栏,且当前不实现变更动作

## 关联

- Policy JSON:[iam-readonly-policy.json](iam-readonly-policy.json)
