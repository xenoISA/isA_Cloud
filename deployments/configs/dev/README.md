# Brew Services Configuration

This directory contains configuration files for Homebrew services used in dev environment.

## Services

All services are managed by the `start-dev.sh` script which uses Homebrew.

### Auto-configured Services (brew services)
- **PostgreSQL@15** - `brew services start postgresql@15`
- **Redis** - `brew services start redis`
- **Neo4j** - `brew services start neo4j`
- **InfluxDB** - `brew services start influxdb`
- **Mosquitto** - `brew services start mosquitto`
- **Grafana** - `brew services start grafana`

### Manually Started Services (with custom configs)
- **MinIO** - Started with nohup
- **Consul** - Started in dev mode
- **NATS** - Started on port 4222
- **Loki** - Started with custom config (if exists)
- **Promtail** - Started with custom config (if exists)

## Custom Configurations

Place custom configuration files here:
- `loki.yml` - Loki configuration
- `promtail.yml` - Promtail configuration

## Default Locations (brew)

Brew installs services with default configs at:
- **PostgreSQL**: `/opt/homebrew/var/postgresql@15/`
- **Redis**: `/opt/homebrew/etc/redis.conf`
- **Neo4j**: `/opt/homebrew/var/neo4j/`
- **Grafana**: `/opt/homebrew/etc/grafana/`
- **Mosquitto**: `/opt/homebrew/etc/mosquitto/`

## Usage

```bash
# Start all services
./scripts/start-dev.sh start

# Stop all services
./scripts/start-dev.sh stop

# Check status
./scripts/start-dev.sh status

# Install missing services
./scripts/start-dev.sh install
```
