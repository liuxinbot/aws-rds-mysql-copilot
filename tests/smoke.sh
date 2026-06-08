#!/usr/bin/env bash
# 独立 smoke 脚本,可单独跑做验证
set -euo pipefail
echo "[1/3] aws CLI version"
aws --version
echo ""
echo "[2/3] aws sts get-caller-identity"
aws sts get-caller-identity
echo ""
echo "[3/3] python boto3 import"
python3 -c "import boto3; print('boto3', boto3.__version__)"
echo ""
echo "✓ smoke 通过"
