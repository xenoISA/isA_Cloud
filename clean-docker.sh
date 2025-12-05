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

# 6. 清理 Kind K8s 集群内的镜像
echo "6️⃣ 清理 Kind K8s 集群内的镜像..."
# 通过 kubectl 获取节点名，这些节点名也是 docker 容器名
KIND_NODES=$(kubectl get nodes -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)
if [ -n "$KIND_NODES" ]; then
    for node in $KIND_NODES; do
        echo "   清理节点: $node"
        echo "   清理前镜像数量: $(docker exec $node crictl images -q 2>/dev/null | wc -l)"
        docker exec $node crictl rmi --prune 2>/dev/null || echo "   跳过 (无未使用镜像)"
        echo "   清理后镜像数量: $(docker exec $node crictl images -q 2>/dev/null | wc -l)"
    done
else
    echo "   未发现 Kind 集群节点，跳过"
fi

echo ""
echo "✅ 清理完成！最终状态："
docker system df
