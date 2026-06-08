#!/usr/bin/env bash
# aws-rds-mysql-copilot 安装脚本(幂等)
#
# 装:aws CLI v2(若缺) + Python 3.11+ 检查 + 项目级 venv + boto3
# 配:静态 AWS AK/SK 写入 ~/.aws/{config,credentials}
# 链:~/.agents/skills/aws-rds-mysql-copilot 软链(可选 ~/.claude/skills/)
# 验:aws sts get-caller-identity + venv boto3

set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_NAME="aws-rds-mysql-copilot"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/$SKILL_NAME"
AWS_CONFIG_DIR="$HOME/.aws"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
info() { printf "  %s\n" "$*"; }
warn() { printf "\033[33m  WARN:\033[0m %s\n" "$*"; }
err()  { printf "\033[31m  ERR:\033[0m  %s\n" "$*" >&2; }

# ---------- aws CLI v2 ----------
ensure_aws_cli() {
    if command -v aws >/dev/null 2>&1; then
        info "aws CLI 已存在: $(aws --version 2>&1 | head -n1)"
        return 0
    fi
    bold "装 aws CLI v2..."
    case "$(uname -s)" in
        Darwin)
            if command -v brew >/dev/null 2>&1; then
                brew install awscli
            else
                err "macOS 需要 brew,或下载官方 pkg 安装:"
                err "  https://awscli.amazonaws.com/AWSCLIV2.pkg"
                err "下载后双击安装,然后重跑 install.sh"
                exit 1
            fi
            ;;
        Linux)
            local arch; arch="$(uname -m)"
            local url
            case "$arch" in
                x86_64)  url="https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" ;;
                aarch64) url="https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" ;;
                *) err "不支持的 Linux 架构: $arch(仅 x86_64 / aarch64)"; exit 1 ;;
            esac
            local tmp; tmp="$(mktemp -d)"
            trap 'rm -rf "$tmp"' EXIT
            ( cd "$tmp" && \
              curl -fsSL "$url" -o awscliv2.zip && \
              unzip -q awscliv2.zip && \
              sudo ./aws/install )
            ;;
        *) err "不支持的 OS: $(uname -s)"; exit 1 ;;
    esac
    info "aws CLI 装完: $(aws --version 2>&1 | head -n1)"
}

# ---------- 输入校验 ----------
require_pattern() {
    local name="$1" pat="$2" val="$3"
    if [[ ! "$val" =~ $pat ]]; then
        err "$name 格式不合法: $val (期望: $pat)"
        exit 1
    fi
}
validate_aws_region() { require_pattern "AWS region" '^[a-z0-9-]+$' "$1"; }
validate_aws_ak()     { require_pattern "AWS Access Key ID" '^[A-Z0-9]+$' "$1"; }
validate_aws_sk()     { require_pattern "AWS Secret Access Key" '^[A-Za-z0-9/+=]+$' "$1"; }

# ---------- 安全写文件 ----------
write_secure() {
    local path="$1"
    mkdir -p "$(dirname "$path")"
    ( umask 077; cat > "$path" )
    chmod 600 "$path"
}

backup_aws_config_if_exists() {
    if [ -f "$AWS_CONFIG_DIR/config" ]; then
        local bak="$AWS_CONFIG_DIR/config.bak.$(date +%s)"
        cp "$AWS_CONFIG_DIR/config" "$bak"
        warn "已存在 $AWS_CONFIG_DIR/config,备份到 $bak(避免丢失其他 profile)"
    fi
}

# ---------- Python 3.11+ ----------
ensure_python() {
    if ! command -v python3 >/dev/null 2>&1; then
        err "需要系统 Python 3.11+(用于创建 venv),系统未发现 python3"
        err "macOS: brew install python@3.11"
        err "Linux: apt/yum 装 python3.11+,或用 pyenv"
        exit 1
    fi
    local v; v="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    local major minor; IFS='.' read -r major minor <<< "$v"
    if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 11 ]; }; then
        err "需要系统 Python 3.11+(用于创建 venv,内部代码用 tomllib),当前 $v"
        exit 1
    fi
    info "Python: $v ✓"
}

# ---------- venv 隔离 ----------
setup_venv() {
    local venv_dir="$DATA_DIR/venv"
    if [ ! -d "$venv_dir" ]; then
        bold "创建项目级 venv: $venv_dir"
        mkdir -p "$DATA_DIR"
        python3 -m venv "$venv_dir"
    else
        info "venv 已存在: $venv_dir"
    fi
    "$venv_dir/bin/pip" install --quiet --upgrade pip
    info "venv pip: $("$venv_dir/bin/pip" --version)"
}

venv_pip_install() {
    "$DATA_DIR/venv/bin/pip" install --quiet "$@"
}

# ---------- 静态 AK/SK 模式 ----------
setup_credentials() {
    bold "收集 AWS AK/SK..."
    read -r -p "  AWS Access Key ID: " AWS_AK; validate_aws_ak "$AWS_AK"
    read -r -s -p "  AWS Secret Access Key: " AWS_SK; echo ""; validate_aws_sk "$AWS_SK"
    read -r -p "  AWS region(如 ap-southeast-1): " AWS_REGION; validate_aws_region "$AWS_REGION"

    write_secure "$AWS_CONFIG_DIR/credentials" <<EOF
[default]
aws_access_key_id = $AWS_AK
aws_secret_access_key = $AWS_SK
EOF
    info "已写入 $AWS_CONFIG_DIR/credentials(权限 600)"

    backup_aws_config_if_exists
    write_secure "$AWS_CONFIG_DIR/config" <<EOF
[default]
region = $AWS_REGION
cli_pager =
EOF
    info "已写入 $AWS_CONFIG_DIR/config"

    setup_venv
    bold "向 venv 装 boto3..."
    venv_pip_install boto3
}

# ---------- smoke ----------
smoke_test() {
    bold "Smoke test: aws sts get-caller-identity"
    if aws sts get-caller-identity; then
        info "✓ 凭证可用"
    else
        err "✗ 凭证验证失败,请按上面报错排查"
        exit 1
    fi

    bold "验证 venv boto3 可用"
    if "$DATA_DIR/venv/bin/python3" -c "import boto3; boto3.client('sts').get_caller_identity()" 2>/dev/null; then
        info "✓ venv boto3 可用"
    else
        err "venv boto3 验证失败 — 检查 $DATA_DIR/venv 是否完好"
        exit 1
    fi
}

# ---------- skill 软链 ----------
# 中间层 ~/.agents/skills/<name>(所有 agent 通用) → SKILL_ROOT
# Claude 层 ~/.claude/skills/<name> → 中间层(可选,询问)
setup_skill_links() {
    local agent_link="$HOME/.agents/skills/$SKILL_NAME"
    local claude_link="$HOME/.claude/skills/$SKILL_NAME"

    bold "建 skill 软链..."

    mkdir -p "$(dirname "$agent_link")"
    if [ -L "$agent_link" ] && [ "$(readlink "$agent_link")" = "$SKILL_ROOT" ]; then
        info "agent skill 软链已存在: $agent_link → $SKILL_ROOT"
    elif [ -e "$agent_link" ] && [ ! -L "$agent_link" ]; then
        warn "$agent_link 已存在但不是软链,跳过(请手动确认)"
    else
        ln -sfn "$SKILL_ROOT" "$agent_link"
        info "已建 agent 软链: $agent_link → $SKILL_ROOT"
    fi

    echo ""
    read -r -p "  是否同时链接到 ~/.claude/skills/(让 Claude Code 识别)?[Y/n]: " yn
    if [[ "$yn" =~ ^[Nn]$ ]]; then
        info "跳过 Claude 链接(可后续手动: ln -sfn $agent_link $claude_link)"
        return 0
    fi

    mkdir -p "$(dirname "$claude_link")"
    if [ -L "$claude_link" ]; then
        local current; current="$(readlink "$claude_link")"
        if [ "$current" = "$agent_link" ] || [ "$current" = "$SKILL_ROOT" ]; then
            info "Claude skill 软链已存在: $claude_link"
        else
            warn "$claude_link 指向 $current,改指向 $agent_link"
            ln -sfn "$agent_link" "$claude_link"
        fi
    elif [ -e "$claude_link" ]; then
        warn "$claude_link 已存在但不是软链,跳过(请手动确认)"
    else
        ln -sfn "$agent_link" "$claude_link"
        info "已建 Claude 软链: $claude_link → $agent_link"
    fi
}

# ---------- main ----------
main() {
    bold "=== $SKILL_NAME install ==="
    ensure_aws_cli
    ensure_python
    setup_credentials
    smoke_test
    setup_skill_links
    bold "=== 安装完成 ==="
    cat <<EOF

下一步:
  - 在 Claude / Cursor / 任何 agent 对话里说 "查 AWS RDS 实例 my-db 的 CPU" 验证问答模式
  - 或 "对 my-db 做 AWS RDS 巡检" 验证巡检模式

如需查看 IAM 权限要求,见 docs/iam-readonly-policy.md。
如需卸载,bash uninstall.sh。
EOF
}

main "$@"
