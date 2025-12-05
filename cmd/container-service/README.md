# Container Service (Firecracker + Ignite)

Cloud OS container management service using Firecracker microVMs via Ignite.

## Overview

This service provides gRPC APIs for managing isolated microVMs for each user, offering true multi-tenant isolation with VM-level security.

### Architecture

```
gRPC API (port 50064)
    ↓
Container Service (Go)
    ↓
Ignite CLI
    ↓
Firecracker MicroVMs
```

## Prerequisites

### 1. Install Firecracker

```bash
release_url="https://github.com/firecracker-microvm/firecracker/releases"
latest=$(curl -sL "${release_url}/latest" | grep -oP 'v\d+\.\d+\.\d+' | head -1)
curl -L ${release_url}/download/${latest}/firecracker-${latest}-x86_64.tgz | tar -xz
sudo mv release-${latest}-x86_64/firecracker-${latest}-x86_64 /usr/local/bin/firecracker
sudo chmod +x /usr/local/bin/firecracker
```

### 2. Install Ignite

```bash
curl -fLo ignite https://github.com/weaveworks/ignite/releases/download/v0.10.0/ignite-amd64
chmod +x ignite
sudo mv ignite /usr/local/bin/
```

### 3. Install CNI Plugins

```bash
sudo mkdir -p /opt/cni/bin
curl -L https://github.com/containernetworking/plugins/releases/download/v1.1.1/cni-plugins-linux-amd64-v1.1.1.tgz | sudo tar -xz -C /opt/cni/bin
```

### 4. Verify Installation

```bash
ignite version
firecracker --version
```

## Build & Run

### Generate Proto Files

```bash
# From isA_Cloud root directory
protoc --go_out=. --go-grpc_out=. api/proto/container.proto
```

### Build Service

```bash
cd cmd/container-service
go mod tidy
go build -o container-service
```

### Run Service

```bash
./container-service
# Or with custom port
CONTAINER_SERVICE_PORT=50064 ./container-service
```

## Usage Examples

### Using grpcurl

```bash
# Health check
grpcurl -plaintext localhost:50064 grpc.health.v1.Health/Check

# Create VM
grpcurl -plaintext -d '{
  "user_id": "user123",
  "image": "ubuntu:22.04",
  "limits": {
    "cpu_count": 2,
    "memory_mb": 4096,
    "disk_size_gb": 20
  }
}' localhost:50064 container.ContainerService/CreateVM

# List VMs
grpcurl -plaintext -d '{
  "user_id": "user123"
}' localhost:50064 container.ContainerService/ListVMs

# Execute command
grpcurl -plaintext -d '{
  "vm_id": "user123-env",
  "command": ["python3", "--version"]
}' localhost:50064 container.ContainerService/ExecuteCommand

# Get VM status
grpcurl -plaintext -d '{
  "vm_id": "user123-env"
}' localhost:50064 container.ContainerService/GetVMStatus

# Stop VM
grpcurl -plaintext -d '{
  "vm_id": "user123-env"
}' localhost:50064 container.ContainerService/StopVM

# Delete VM
grpcurl -plaintext -d '{
  "vm_id": "user123-env",
  "force": true
}' localhost:50064 container.ContainerService/DeleteVM
```

## Features

- ✅ VM lifecycle management (create, start, stop, delete)
- ✅ Command execution in VMs
- ✅ File operations (read, write, delete)
- ✅ Resource monitoring
- ✅ Docker image compatibility (via Ignite)
- ✅ VM-level isolation (Firecracker)
- ✅ SSH key injection
- ✅ Port forwarding
- ✅ Custom labels

## Configuration

Environment variables:

- `CONTAINER_SERVICE_PORT`: gRPC server port (default: 50064)
- `SERVICE_NAME`: Service name for health checks (default: container-grpc)

## Kubernetes Deployment

See `deployments/kubernetes/base/grpc-services/container-grpc/` for K8s manifests.

## Docker Image Compatibility

Ignite supports standard Docker/OCI images:

```bash
# Ubuntu
ignite run ubuntu:22.04

# Python
ignite run python:3.11

# Node.js
ignite run node:18

# Custom images
ignite run myregistry/myimage:tag
```

## Security

- Each VM runs in an isolated Firecracker microVM
- VMs cannot access each other
- Resource limits are enforced at the hypervisor level
- Suitable for multi-tenant SaaS environments

## Performance

- VM startup time: < 1 second
- Memory overhead per VM: ~5-10 MB
- Supports 100+ VMs per host (depending on resources)

## Troubleshooting

### Ignite not found
```bash
sudo ln -s /path/to/ignite /usr/local/bin/ignite
```

### KVM not available
```bash
# Check KVM support
kvm-ok
# or
lscpu | grep Virtualization
```

### Permission denied
```bash
# Add user to kvm group
sudo usermod -aG kvm $USER
```

## References

- [Ignite Documentation](https://ignite.readthedocs.io/)
- [Firecracker Documentation](https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md)
- [gRPC Go Tutorial](https://grpc.io/docs/languages/go/quickstart/)
