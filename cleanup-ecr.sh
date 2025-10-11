#!/bin/bash

# 清理所有 ECR 仓库中的镜像
REGION="us-east-1"

# 基础设施服务仓库列表
REPOS=(
    "isa-consul"
    "isa-redis"
    "isa-minio"
    "isa-nats"
    "isa-mosquitto"
    "isa-loki"
    "isa-grafana"
    "isa-influxdb"
    "isa-neo4j"
    "isa-postgresql"
)

# 应用服务仓库列表
APP_REPOS=(
    "isa-gateway"
    "isa-model"
    "isa-mcp"
    "isa-agent"
    "isa-user"
    "isa-user-base"
    "isa-blockchain"
)

echo "🗑️  开始清理 ECR 镜像..."

# 清理基础设施服务镜像
for repo in "${REPOS[@]}"; do
    echo "清理仓库: $repo"
    
    # 删除所有镜像
    aws ecr list-images --repository-name $repo --region $REGION --query 'imageIds[*]' --output json | \
    jq '.[]' | \
    while read imageId; do
        aws ecr batch-delete-image --repository-name $repo --region $REGION --image-ids "$imageId" --output text
    done
    
    echo "✅ $repo 清理完成"
done

# 清理应用服务镜像
for repo in "${APP_REPOS[@]}"; do
    echo "清理仓库: $repo"
    
    # 删除所有镜像
    aws ecr list-images --repository-name $repo --region $REGION --query 'imageIds[*]' --output json | \
    jq '.[]' | \
    while read imageId; do
        aws ecr batch-delete-image --repository-name $repo --region $REGION --image-ids "$imageId" --output text
    done
    
    echo "✅ $repo 清理完成"
done

echo "🎉 所有 ECR 镜像清理完成！"