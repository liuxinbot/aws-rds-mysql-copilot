#!/usr/bin/env bash
# aws-rds-mysql-copilot 卸载脚本(幂等)
#
# 删:
#   - ~/.agents/skills/aws-rds-mysql-copilot(skill 软链)
#   - ~/.claude/skills/aws-rds-mysql-copilot(skill 软链,如果之前建了)
#   - ~/.local/share/aws-rds-mysql-copilot/(venv)
#
# 提示但不动(避免误删用户的其他配置):
#   - ~/.aws/config(可能有其他 profile)
#   - ~/.aws/credentials(可能有其他 profile)
#   - 仓库目录本身
#
# 不碰(其他项目可能用):
#   - aws CLI、Homebrew Python、系统 pip 装的包

set -uo pipefail

SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_NAME="aws-rds-mysql-copilot"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/$SKILL_NAME"
AGENT_LINK="$HOME/.agents/skills/$SKILL_NAME"
CLAUDE_LINK="$HOME/.claude/skills/$SKILL_NAME"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
info() { printf "  %s\n" "$*"; }
warn() { printf "\033[33m  WARN:\033[0m %s\n" "$*"; }

bold "=== $SKILL_NAME uninstall ==="
echo ""
info "将删除:"
info "  - $AGENT_LINK(skill 软链)"
info "  - $CLAUDE_LINK(skill 软链,如果之前建了)"
info "  - $DATA_DIR(venv)"
echo ""
info "需要你手动处理(本脚本不动,避免误删其他配置):"
info "  - ~/.aws/config / ~/.aws/credentials(可能有其他 AWS profile)"
info "  - 仓库目录 $SKILL_ROOT"
echo ""

read -r -p "确认卸载?[y/N]: " yn
[[ "$yn" =~ ^[Yy]$ ]] || { echo "取消"; exit 0; }
echo ""

remove_link() {
    local link="$1"
    if [ -L "$link" ]; then
        rm "$link"
        info "✓ 已删 $link"
    elif [ -e "$link" ]; then
        warn "$link 存在但不是软链 — 跳过(请手动确认)"
    else
        info "○ $link 不存在,跳过"
    fi
}

remove_link "$AGENT_LINK"
remove_link "$CLAUDE_LINK"

if [ -d "$DATA_DIR" ]; then
    rm -rf "$DATA_DIR"
    info "✓ 已删 $DATA_DIR(venv)"
else
    info "○ $DATA_DIR 不存在,跳过"
fi

if [ -f "$HOME/.aws/credentials" ] && [ -s "$HOME/.aws/credentials" ]; then
    warn "$HOME/.aws/credentials 存在(可能写过 AWS AK/SK)"
    warn "  - 完全卸载:rm ~/.aws/credentials"
    warn "  - 保留其他 profile:vim 编辑删 [default] 段"
fi

echo ""
bold "=== 卸载完成 ==="
info "未碰:aws CLI / Homebrew Python / brew 装的工具(可能其他项目在用)"
info "如要彻底删仓库:rm -rf $SKILL_ROOT"
