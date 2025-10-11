#!/bin/bash
# 运行单元测试
# Run unit tests

set -e

cd "$(dirname "$0")/.."

echo "=========================================="
echo "运行单元测试"
echo "=========================================="
echo ""

# 运行所有单元测试
echo "1. 运行所有单元测试..."
go test -v ./tests/unit/... 2>&1 | tee /tmp/unit-test-results.txt

# 统计测试结果
PASSED=$(grep -c "PASS:" /tmp/unit-test-results.txt || true)
FAILED=$(grep -c "FAIL:" /tmp/unit-test-results.txt || true)
SKIPPED=$(grep -c "SKIP:" /tmp/unit-test-results.txt || true)

echo ""
echo "=========================================="
echo "测试结果统计"
echo "=========================================="
echo "通过: $PASSED"
echo "失败: $FAILED"
echo "跳过: $SKIPPED"
echo ""

# 生成覆盖率报告
echo "2. 生成覆盖率报告..."
go test -coverprofile=/tmp/coverage.out ./tests/unit/... 2>/dev/null || true
if [ -f /tmp/coverage.out ]; then
    go tool cover -func=/tmp/coverage.out | tail -10
    echo ""
    echo "详细覆盖率报告: /tmp/coverage.out"
    echo "HTML 报告: go tool cover -html=/tmp/coverage.out"
fi

echo ""
echo "=========================================="
if [ "$FAILED" -eq 0 ]; then
    echo "✓ 所有测试通过！"
else
    echo "✗ 有 $FAILED 个测试失败"
fi
echo "=========================================="



