# IsA Cloud Staging Deployment Guide

## Overview

This guide explains how the IsA Cloud staging deployment works, the gateway configuration fix that was implemented, and how to make modifications to the system.

## ✅ Gateway Consul Registration Fix

### Problem Solved
The gateway service was failing to register properly with Consul due to a configuration loading bug in `internal/config/config.go`. The `Load(configFile string)` function was ignoring the `configFile` parameter and always calling `LoadConfig()`, which used hardcoded defaults.

### Root Cause
```go
// Before: internal/config/config.go:249
func Load(configFile string) (*Config, error) {
    return LoadConfig()  // BUG: ignores configFile parameter
}
```

### Solution Applied
```go
// After: internal/config/config.go:249-283
func Load(configFile string) (*Config, error) {
    // Set defaults
    setDefaults()

    // Read environment variables
    viper.AutomaticEnv()
    viper.SetEnvPrefix("ISA_CLOUD")
    viper.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))

    // If configFile is provided, use it
    if configFile != "" {
        viper.SetConfigFile(configFile)
    } else {
        // Set config file defaults
        viper.SetConfigName("gateway")
        viper.SetConfigType("yaml")
        viper.AddConfigPath("./deployments/configs")
        viper.AddConfigPath("../deployments/configs")
        viper.AddConfigPath("/etc/isa_cloud")
    }

    // Read config file
    if err := viper.ReadInConfig(); err != nil {
        if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
            return nil, fmt.Errorf("failed to read config file: %w", err)
        }
        // Config file not found, use defaults and env vars
    }

    // Unmarshal config
    var cfg Config
    if err := viper.Unmarshal(&cfg); err != nil {
        return nil, fmt.Errorf("failed to unmarshal config: %w", err)
    }

    return &cfg, nil
}
```

### Verification Results
- ✅ Gateway loads `/app/configs/staging/gateway.yaml` correctly
- ✅ Connects to Consul at `staging-consul:8500` (not localhost)
- ✅ Registers as `gateway-19561283b27a-8000` in Consul
- ✅ Health checks passing
- ✅ Service discovery working with all services

## 🏗️ Staging Architecture

### Service Components

| Service | Container | Port | Status | Consul Registration |
|---------|-----------|------|--------|-------------------|
| Gateway | `gateway-staging-test` | 8000 | ✅ Running | `gateway-19561283b27a-8000` |
| MCP | `mcp-staging-test` | 8081 | ✅ Running | `mcp_service-mcp-staging-test-8081` |
| Agent | `agent-staging-test` | 8080 | ✅ Running | `agent_service-agent-staging-test-8080` |
| Model | `model-staging-test` | 8082 | ✅ Running | `model_service-ae7fd4cec282-8082` |

### Network Configuration
- **Network**: `staging_staging-network`
- **Consul**: `staging-consul:8500`
- **Service Discovery**: All services registered with `*_service` naming pattern

## 📁 Key Files and Structure

### Gateway Configuration Files
```
deployments/
├── dockerfiles/Staging/
│   └── Dockerfile.gateway.staging      # Staging-specific gateway Dockerfile
├── configs/staging/
│   └── gateway.yaml                    # Staging gateway configuration
└── envs/staging/
    └── .env.gateway                    # Gateway environment variables (gitignored)
```

### Configuration Loading Flow
1. **Container Start**: Gateway container starts with `CMD /app/gateway --config /app/configs/staging/gateway.yaml`
2. **Config Loading**: `main.go:58` calls `config.Load(configFile)`
3. **File Processing**: Config loads YAML file using `viper.SetConfigFile(configFile)`
4. **Consul Connection**: Gateway connects to `staging-consul:8500` from YAML config
5. **Service Registration**: Gateway registers with Consul service discovery

### Critical Configuration Files

#### `deployments/configs/staging/gateway.yaml`
```yaml
consul:
  host: staging-consul  # Changed from consul.staging.isa.local
  port: 8500
  enabled: true
```

#### `deployments/dockerfiles/Staging/Dockerfile.gateway.staging`
```dockerfile
FROM golang:1.23-alpine AS builder
# ... build steps ...
FROM alpine:latest
COPY --from=builder /app/bin/gateway /app/gateway
COPY deployments/configs/staging/ /app/configs/staging/
CMD /app/gateway --config /app/configs/staging/gateway.yaml
```

## 🚀 How to Deploy Changes

### 1. Rebuild Gateway Container
```bash
# Build new gateway image
docker build --platform linux/amd64 --no-cache -t staging-isa-gateway:amd64 \
  -f deployments/dockerfiles/Staging/Dockerfile.gateway.staging .

# Stop and remove old container
docker stop gateway-staging-test && docker rm gateway-staging-test

# Run new container
docker run -d --name gateway-staging-test \
  --network staging_staging-network -p 8000:8000 \
  --env-file deployments/envs/staging/.env.gateway \
  staging-isa-gateway:amd64
```

### 2. Verify Deployment
```bash
# Check container status
docker ps | grep gateway-staging-test

# Check logs
docker logs gateway-staging-test

# Verify health
curl http://localhost:8000/health

# Check Consul registration
curl -s http://localhost:8500/v1/agent/services | jq '.["gateway-*"]'
```

## 🔧 Making Configuration Changes

### Gateway Configuration Changes

1. **Modify YAML Config**:
   ```bash
   # Edit staging gateway config
   vim deployments/configs/staging/gateway.yaml
   ```

2. **Environment Variables**:
   ```bash
   # Edit environment file (gitignored)
   vim deployments/envs/staging/.env.gateway
   ```

3. **Rebuild and Deploy**:
   ```bash
   # Rebuild container
   docker build --platform linux/amd64 --no-cache -t staging-isa-gateway:amd64 \
     -f deployments/dockerfiles/Staging/Dockerfile.gateway.staging .
   
   # Deploy
   docker stop gateway-staging-test && docker rm gateway-staging-test
   docker run -d --name gateway-staging-test \
     --network staging_staging-network -p 8000:8000 \
     --env-file deployments/envs/staging/.env.gateway \
     staging-isa-gateway:amd64
   ```

### Adding New Services

1. **Create Service Dockerfile**:
   ```bash
   # Create staging-specific Dockerfile
   vim deployments/dockerfiles/Staging/Dockerfile.newservice.staging
   ```

2. **Add Service Configuration**:
   ```bash
   # Add YAML config
   vim deployments/configs/staging/newservice.yaml
   
   # Add environment file
   vim deployments/envs/staging/.env.newservice
   ```

3. **Register with Consul**:
   ```go
   // In service initialization
   consulRegistry.RegisterService("newservice_service", serviceHost, servicePort, []string{"api", "newservice"})
   ```

## 🔍 Troubleshooting

### Common Issues and Solutions

#### 1. Gateway Not Registering with Consul
**Symptoms**: Gateway logs show `localhost:8500` instead of `staging-consul:8500`

**Solution**: 
- Check that config file is being loaded: `docker logs gateway-staging-test | grep "config"`
- Verify YAML file exists in container: `docker exec gateway-staging-test ls -la /app/configs/staging/`
- Check config loading code in `internal/config/config.go:249`

#### 2. Service Discovery Failing
**Symptoms**: Gateway can't find other services

**Solution**:
```bash
# Check Consul services
curl -s http://localhost:8500/v1/agent/services | jq keys

# Verify network connectivity
docker exec gateway-staging-test ping staging-consul

# Check gateway logs for connection errors
docker logs gateway-staging-test | grep -i consul
```

#### 3. Configuration Not Loading
**Symptoms**: Service uses default config instead of staging config

**Solution**:
- Verify Dockerfile CMD uses `--config` flag
- Check file paths in container: `docker exec <container> ls -la /app/configs/staging/`
- Validate YAML syntax: `yamllint deployments/configs/staging/gateway.yaml`

### Debug Commands

```bash
# Check container network
docker network inspect staging_staging-network

# Verify Consul connectivity
docker exec gateway-staging-test nslookup staging-consul

# Check service registration
curl -s http://localhost:8500/v1/agent/services | jq 'to_entries[] | select(.key | contains("gateway"))'

# Monitor logs in real-time
docker logs -f gateway-staging-test

# Check environment variables
docker exec gateway-staging-test env | grep -E "(CONSUL|SERVICE|GATEWAY)"
```

## 📈 Monitoring and Health Checks

### Health Endpoints
- **Gateway Health**: `http://localhost:8000/health`
- **Service List**: `http://localhost:8000/api/v1/gateway/services`
- **Consul UI**: `http://localhost:8500/ui/staging/services`

### Key Metrics to Monitor
- Service registration status in Consul
- Health check success rate
- Response times for inter-service communication
- Container resource usage

## 🔐 Security Considerations

### Environment Variables
- All sensitive configuration is in `.env.*` files (gitignored)
- API keys and secrets are not committed to git
- AWS deployment files with secrets are excluded via `.gitignore`

### Network Security
- Services communicate via internal Docker network
- Only gateway exposes external ports
- Consul ACLs can be configured for production

## 📚 Related Documentation

- **Consul Flow**: See `docs/CONSUL_FLOW.md`
- **Infrastructure gRPC**: See `docs/infra_grpc_service.md`
- **Configuration Examples**: See `configs/examples/`

## 🤝 Contributing

### Making Changes to This Deployment

1. **Test Locally First**:
   ```bash
   # Start staging environment
   docker run -d --name test-gateway \
     --network staging_staging-network \
     --env-file deployments/envs/staging/.env.gateway \
     staging-isa-gateway:amd64
   ```

2. **Commit Changes**:
   ```bash
   git add .
   git commit -m "Update staging deployment configuration"
   git push origin release/staging-v0.1.0
   ```

3. **Verify Deployment**:
   - Check gateway health endpoints
   - Verify Consul service registration
   - Test inter-service communication

### Development Workflow

1. **Feature Development**: Work in feature branches
2. **Staging Testing**: Deploy to staging environment for testing
3. **Production Deployment**: Merge to main branch for production

---

**Last Updated**: October 12, 2025  
**Version**: staging-v0.1.0  
**Status**: ✅ Gateway Consul registration working correctly