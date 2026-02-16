# DEPRECATED - Legacy Deployment Configurations

> **WARNING**: These configurations are deprecated and kept for historical reference only.
> Do NOT use these for new deployments.

## Current Active Configurations

For current deployment configurations, see:
- `../local/` - Local development (Kind cluster)
- `../staging/` - Staging environment
- `../production/` - Production environment

## Why These Are Deprecated

These configurations were used during early development and have been superseded by:
- Helm charts in `deployments/charts/`
- Environment-specific Kustomize overlays in the active directories
- Terraform infrastructure in `deployments/terraform/`

## Contents (For Reference Only)

- `base/` - Old Kustomize base configurations
- `overlays/` - Old environment overlays
- `compose/` - Docker Compose files for local testing
- `configs/` - Old configuration files
- `dockerfiles/` - Legacy Dockerfiles

## Migration Notes

If you need to understand historical decisions, these files may be useful.
For any new work, use the current active configurations.

---
*Deprecated as of: February 2025*
