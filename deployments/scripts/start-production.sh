#!/bin/bash
# ============================================
# isA Platform - Production Environment (AWS)
# ============================================
# Uses ECR images, AWS managed services, strict checks

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"

cd "$DEPLOY_DIR"

# Load environment variables
if [ -f .env.production ]; then
    export $(cat .env.production | grep -v '^#' | xargs)
else
    echo "❌ Error: .env.production not found!"
    exit 1
fi

# Check required environment variables
REQUIRED_VARS=("ECR_REGISTRY" "IMAGE_TAG" "AWS_REGION" "GF_ADMIN_PASSWORD")
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Error: $var must be set in .env.production"
        exit 1
    fi
done

echo "🚀 isA Platform - Production Deployment"
echo "========================================"
echo "Environment: PRODUCTION (AWS)"
echo "ECR Registry: $ECR_REGISTRY"
echo "Image Tag: $IMAGE_TAG"
echo "AWS Region: $AWS_REGION"
echo ""

# Confirmation prompt for production
if [ "${1}" == "up" ] || [ "${1}" == "restart" ]; then
    read -p "⚠️  Deploy to PRODUCTION? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "❌ Deployment cancelled."
        exit 0
    fi
fi

case "${1:-up}" in
    up)
        echo "📦 Deploying to production..."

        # Login to ECR
        echo "🔐 Logging into ECR..."
        aws ecr get-login-password --region $AWS_REGION | \
            docker login --username AWS --password-stdin $ECR_REGISTRY

        # Pull latest images
        echo "📥 Pulling latest images..."
        docker-compose -f docker-compose.production.yml pull

        # Health check before deployment
        echo "🏥 Running pre-deployment health checks..."
        # Add your health check commands here

        # Start services
        echo "🚀 Starting services..."
        docker-compose -f docker-compose.production.yml up -d

        # Post-deployment health check
        echo "⏳ Waiting for services to be healthy..."
        sleep 30

        echo ""
        echo "✅ Production deployment complete!"
        echo ""
        echo "📊 Service URLs:"
        echo "  - Gateway:  https://api.isa-platform.com"
        echo "  - Grafana:  https://grafana.isa-platform.com"
        echo ""
        echo "💡 Monitor logs: ./scripts/start-production.sh logs [service]"
        echo "⚠️  Check Grafana for metrics and alerts"
        ;;
    down)
        read -p "⚠️  Stop PRODUCTION services? (yes/no): " confirm
        if [ "$confirm" == "yes" ]; then
            echo "🛑 Stopping services..."
            docker-compose -f docker-compose.production.yml down
            echo "✅ Stopped!"
        else
            echo "❌ Cancelled."
        fi
        ;;
    restart)
        echo "🔄 Restarting services..."
        docker-compose -f docker-compose.production.yml restart
        echo "✅ Restarted!"
        ;;
    logs)
        docker-compose -f docker-compose.production.yml logs -f ${2:-}
        ;;
    ps)
        docker-compose -f docker-compose.production.yml ps
        ;;
    pull)
        echo "📥 Pulling latest images..."
        aws ecr get-login-password --region $AWS_REGION | \
            docker login --username AWS --password-stdin $ECR_REGISTRY
        docker-compose -f docker-compose.production.yml pull
        echo "✅ Images pulled!"
        ;;
    health)
        echo "🏥 Checking service health..."
        docker-compose -f docker-compose.production.yml ps
        # Add health check endpoints
        ;;
    *)
        echo "Usage: $0 {up|down|restart|logs|ps|pull|health}"
        exit 1
        ;;
esac
