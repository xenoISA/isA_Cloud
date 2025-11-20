#!/bin/bash
echo "🧹 清理 Docker 空间..."

# 1. 删除悬空镜像
echo "1️⃣ 删除悬空镜像..."
docker image prune -f

# 2. 删除未使用的镜像
echo "2️⃣ 删除未使用的镜像（24小时前）..."
docker image prune -a -f --filter "until=24h"

# 3. 清理构建缓存（保留最近 7 天）
echo "3️⃣ 清理构建缓存（保留7天内）..."
docker buildx prune -f --filter "until=168h"

# 4. 清理停止的容器
echo "4️⃣ 清理停止的容器..."
docker container prune -f

# 5. 清理未使用的网络
echo "5️⃣ 清理未使用的网络..."
docker network prune -f

echo ""
echo "✅ 清理完成！最终状态："
docker system df
