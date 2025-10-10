# isA Platform Logging Infrastructure

## Overview

The isA Platform uses a centralized logging stack built on:
- **Loki** - Log aggregation and storage
- **Promtail** - Log collection agent
- **Grafana** - Log visualization and dashboarding

This infrastructure collects logs from all services registered with Consul:
- isA_user microservices (auth, payment, wallet, etc.)
- isA_Agent service
- isA_MCP service
- isA_Model service
- All other platform services

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  isA_user       │     │  isA_Agent      │     │  isA_MCP/Model  │
│  Microservices  │     │  Service        │     │  Services       │
│                 │     │                 │     │                 │
│  logs/*.log     │     │  logs/*.log     │     │  logs/*.log     │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                          ┌──────▼──────┐
                          │  Promtail   │
                          │ (Collector) │
                          └──────┬──────┘
                                 │
                          ┌──────▼──────┐
                          │    Loki     │
                          │ (Storage &  │
                          │   Query)    │
                          └──────┬──────┘
                                 │
                          ┌──────▼──────┐
                          │   Grafana   │
                          │(Visualization)│
                          └─────────────┘
```

## Quick Start

### 1. Start the Logging Stack

```bash
cd /Users/xenodennis/Documents/Fun/isA_Cloud/deployments

# Start only logging services
docker-compose up -d loki promtail grafana

# Or start entire infrastructure
docker-compose up -d
```

### 2. Access Grafana

- **URL**: http://localhost:3003
- **Username**: `admin`
- **Password**: `admin`

### 3. View Logs

1. Navigate to **Explore** in Grafana sidebar
2. Select **Loki** datasource
3. Use LogQL queries to search logs:

```logql
# All logs from auth service
{service="auth_service"}

# Error logs from all services
{level="ERROR"}

# Logs from isA_Agent
{job="agent_service"}

# Search for specific text
{service="payment_service"} |= "transaction"

# Regex search
{service=~".*_service"} |~ "error|exception"
```

## Log Collection

### Services Being Monitored

Promtail automatically collects logs from:

1. **isA_user Microservices**
   - Path: `/Users/xenodennis/Documents/Fun/isA_user/logs/**/*.log`
   - Labels: `job=user_services`, `service=<service_name>`, `level=<log_level>`

2. **isA_Agent Service**
   - Path: `/Users/xenodennis/Documents/Fun/isA_Agent/logs/**/*.log`
   - Labels: `job=agent_service`, `service=agent`, `level=<log_level>`

3. **Docker Containers**
   - All containers in the `isa-network`
   - Labels: `container=<container_name>`, `service=<compose_service>`

### Log Format

Services should output logs in this format for proper parsing:

```
2025-10-02 14:30:45,123 - service_name - INFO - Log message here
```

Format: `<timestamp> - <service> - <level> - <message>`

## LogQL Query Examples

### Basic Queries

```logql
# All logs
{job=~".*"}

# Logs from specific service
{service="auth_service"}

# Logs by level
{level="ERROR"}
{level=~"ERROR|CRITICAL"}

# Multiple labels
{service="payment_service", level="ERROR"}
```

### Filtering

```logql
# Contains text
{service="auth_service"} |= "login"

# Does not contain
{service="auth_service"} != "debug"

# Regex match
{service="auth_service"} |~ "error|exception"

# Regex does not match
{service="auth_service"} !~ "debug|trace"
```

### Aggregations

```logql
# Count logs per service
sum by (service) (count_over_time({job=~".*"}[5m]))

# Error rate per service
sum by (service) (rate({level="ERROR"}[5m]))

# Top error services
topk(5, sum by (service) (count_over_time({level="ERROR"}[1h])))
```

### Time Range Queries

```logql
# Last 5 minutes
{service="auth_service"}[5m]

# Last hour
{service="auth_service"}[1h]

# Last 24 hours
{service="auth_service"}[24h]
```

## Dashboards

### Pre-configured Dashboard: "isA Platform Logs"

Located at: **Dashboards → isA Platform → isA Platform Logs**

Features:
- **Logs by Service** - Pie chart showing log distribution
- **Logs by Level** - Pie chart showing log levels (INFO, ERROR, etc.)
- **All Logs** - Live log viewer with filtering
- **Error Logs** - Only ERROR and CRITICAL level logs

Variables:
- **service** - Filter by service name
- **level** - Filter by log level

## Configuration

### Loki Configuration

File: `/Users/xenodennis/Documents/Fun/isA_Cloud/deployments/configs/loki-config.yml`

Key settings:
- **Retention**: 720 hours (30 days)
- **Storage**: Local filesystem
- **Compression**: Enabled
- **Max query length**: 721 hours

### Promtail Configuration

File: `/Users/xenodennis/Documents/Fun/isA_Cloud/deployments/configs/promtail-config.yml`

Jobs configured:
- `system` - System logs from /var/log
- `user_services` - isA_user microservices
- `agent_service` - isA_Agent
- `docker` - Docker container logs

### Grafana Datasource

File: `/Users/xenodennis/Documents/Fun/isA_Cloud/deployments/configs/grafana/provisioning/datasources/loki.yml`

- Auto-configured Loki datasource
- Default datasource for new dashboards
- Max lines: 1000 per query

## API Access

### Loki API

Query logs programmatically:

```bash
# Query logs via HTTP API
curl -G -s "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={service="auth_service"}' \
  --data-urlencode 'start=1696262400000000000' \
  | jq .

# Get all labels
curl -s "http://localhost:3100/loki/api/v1/labels" | jq .

# Get label values
curl -s "http://localhost:3100/loki/api/v1/label/service/values" | jq .
```

### Health Checks

```bash
# Loki health
curl http://localhost:3100/ready
curl http://localhost:3100/metrics

# Grafana health
curl http://localhost:3003/api/health
```

## Maintenance

### View Logs

```bash
# Loki logs
docker logs isa-loki

# Promtail logs
docker logs isa-promtail

# Grafana logs
docker logs isa-grafana
```

### Restart Services

```bash
# Restart individual service
docker-compose restart loki
docker-compose restart promtail
docker-compose restart grafana

# Restart all logging services
docker-compose restart loki promtail grafana
```

### Storage Management

Loki automatically manages retention (30 days). To manually clean up:

```bash
# Enter Loki container
docker exec -it isa-loki sh

# Check storage usage
du -sh /loki/*

# Compaction runs automatically every 10 minutes
```

### Backup

```bash
# Backup Grafana dashboards and datasources
docker cp isa-grafana:/var/lib/grafana ./grafana-backup

# Backup Loki data
docker cp isa-loki:/loki ./loki-backup
```

## Troubleshooting

### No logs appearing in Grafana

1. Check Promtail is running:
   ```bash
   docker ps | grep promtail
   docker logs isa-promtail
   ```

2. Verify log files exist and are readable:
   ```bash
   ls -la /Users/xenodennis/Documents/Fun/isA_user/logs/
   ls -la /Users/xenodennis/Documents/Fun/isA_Agent/logs/
   ```

3. Check Loki ingestion:
   ```bash
   curl "http://localhost:3100/loki/api/v1/labels"
   ```

### Loki not starting

```bash
# Check Loki logs
docker logs isa-loki

# Verify config syntax
docker run --rm -v $(pwd)/configs:/configs grafana/loki:2.9.3 \
  -config.file=/configs/loki-config.yml -verify-config
```

### Grafana dashboard not loading

1. Check Grafana logs:
   ```bash
   docker logs isa-grafana
   ```

2. Verify datasource connection:
   - Go to **Configuration → Data Sources → Loki**
   - Click **Save & Test**

3. Restart Grafana:
   ```bash
   docker-compose restart grafana
   ```

## Adding New Services

To add a new service to log collection:

1. **Ensure logs are written to a file**:
   ```python
   import logging
   logging.basicConfig(
       filename='logs/myservice.log',
       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
   )
   ```

2. **Update Promtail config** if needed:
   Edit `deployments/configs/promtail-config.yml` and add a new job:
   ```yaml
   - job_name: my_new_service
     static_configs:
       - targets:
           - localhost
         labels:
           job: my_service
           service: my_service
           __path__: /var/logs/myservice/**/*.log
   ```

3. **Update docker-compose.yml** to mount the log directory:
   ```yaml
   promtail:
     volumes:
       - ../../my_service/logs:/var/logs/myservice:ro
   ```

4. **Restart Promtail**:
   ```bash
   docker-compose restart promtail
   ```

## Best Practices

1. **Log Levels**
   - Use appropriate log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
   - Include service name in logger name: `logging.getLogger("auth_service")`

2. **Structured Logging**
   - Include relevant context: user_id, request_id, transaction_id
   - Use consistent timestamp format

3. **Log Rotation**
   - Rotate logs locally to prevent disk space issues
   - Loki handles long-term storage and retention

4. **Query Optimization**
   - Use specific labels when possible: `{service="auth"}` not `{job=~".*"}`
   - Limit time ranges for better performance
   - Use aggregations for metrics, not raw logs

5. **Alerting**
   - Set up alerts for ERROR/CRITICAL log spikes
   - Monitor log ingestion rate
   - Alert on service-specific patterns

## Resources

- [Loki Documentation](https://grafana.com/docs/loki/latest/)
- [LogQL Query Language](https://grafana.com/docs/loki/latest/logql/)
- [Promtail Configuration](https://grafana.com/docs/loki/latest/clients/promtail/)
- [Grafana Dashboards](https://grafana.com/docs/grafana/latest/dashboards/)

## Support

For issues or questions:
1. Check logs: `docker logs <container_name>`
2. Verify configuration files
3. Check service health endpoints
4. Review this documentation

---

**Version**: 1.0.0
**Last Updated**: 2025-10-02
**Maintained by**: isA Platform Team
