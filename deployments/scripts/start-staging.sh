#!/bin/bash
# ============================================
# isA Platform - Staging Environment (AWS)
# ============================================
# Uses ECR images, AWS managed services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"

cd "$DEPLOY_DIR"

# Load environment variables
if [ -f .env.staging ]; then
    export $(cat .env.staging | grep -v '^#' | xargs)
else
    echo "❌ Error: .env.staging not found!"
    exit 1
fi

# Check required environment variables
if [ -z "$ECR_REGISTRY" ] || [ -z "$IMAGE_TAG" ]; then
    echo "❌ Error: ECR_REGISTRY and IMAGE_TAG must be set in .env.staging"
    exit 1
fi

echo "🎭 Starting isA Platform - Staging Environment"
echo "==============================================="
echo "Environment: staging (AWS)"
echo "ECR Registry: $ECR_REGISTRY"
echo "Image Tag: $IMAGE_TAG"
echo ""

case "${1:-up}" in
    up)
        echo "📦 Deploying to staging..."

        # Login to ECR
        echo "🔐 Logging into ECR..."
        aws ecr get-login-password --region ${AWS_REGION:-us-east-1} | \
            docker login --username AWS --password-stdin $ECR_REGISTRY

        # Pull latest images
        echo "📥 Pulling latest images..."
        docker-compose -f docker-compose.staging.yml pull

        # Start services
        echo "🚀 Starting services..."
        docker-compose -f docker-compose.staging.yml up -d

        echo ""
        echo "✅ Staging environment deployed!"
        echo ""
        echo "📊 Service URLs:"
        echo "  - Gateway:  http://staging-gateway.isa-platform.com"
        echo "  - Grafana:  http://staging-grafana.isa-platform.com"
        echo ""
        echo "💡 Check logs: ./scripts/start-staging.sh logs [service]"
        ;;
    down)
        echo "🛑 Stopping services..."
        docker-compose -f docker-compose.staging.yml down
        echo "✅ Stopped!"
        ;;
    restart)
        echo "🔄 Restarting services..."
        docker-compose -f docker-compose.staging.yml restart
        echo "✅ Restarted!"
        ;;
    logs)
        docker-compose -f docker-compose.staging.yml logs -f ${2:-}
        ;;
    ps)
        docker-compose -f docker-compose.staging.yml ps
        ;;
    pull)
        echo "📥 Pulling latest images..."
        aws ecr get-login-password --region ${AWS_REGION:-us-east-1} | \
            docker login --username AWS --password-stdin $ECR_REGISTRY
        docker-compose -f docker-compose.staging.yml pull
        echo "✅ Images pulled!"
        ;;
    *)
        echo "Usage: $0 {up|down|restart|logs|ps|pull}"
        exit 1
        ;;
esac
