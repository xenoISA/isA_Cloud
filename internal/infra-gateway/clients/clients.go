package clients

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/isa-cloud/isa_cloud/internal/config"
	"github.com/isa-cloud/isa_cloud/pkg/logger"
)

// InfraClients holds all infrastructure service clients
type InfraClients struct {
	config  *config.Config
	logger  *logger.Logger
	
	// Database clients
	supabase *SupabaseClient
	// Other clients will be added later
	// redis    *RedisClient
	// duckdb   *DuckDBClient
	// neo4j    *Neo4jClient
	// influx   *InfluxDBClient
	// minio    *MinIOClient
	// loki     *LokiClient
	// nats     *NATSClient
	// mqtt     *MQTTClient
	
	// Connection management
	mu       sync.RWMutex
	stats    *Stats
}

// Stats holds statistics for all infrastructure clients
type Stats struct {
	TotalRequests     int64                 `json:"total_requests"`
	TotalErrors       int64                 `json:"total_errors"`
	ActiveConnections map[string]int        `json:"active_connections"`
	ServiceStats      map[string]ServiceStat `json:"service_stats"`
	StartTime         time.Time             `json:"start_time"`
}

// ServiceStat holds statistics for a single service
type ServiceStat struct {
	Requests       int64         `json:"requests"`
	Errors         int64         `json:"errors"`
	AvgLatency     time.Duration `json:"avg_latency"`
	LastRequest    time.Time     `json:"last_request"`
	Status         string        `json:"status"`
	ConnectionPool int           `json:"connection_pool"`
}

// New creates a new InfraClients instance
func New(cfg *config.Config, logger *logger.Logger) (*InfraClients, error) {
	clients := &InfraClients{
		config: cfg,
		logger: logger,
		stats: &Stats{
			ActiveConnections: make(map[string]int),
			ServiceStats:      make(map[string]ServiceStat),
			StartTime:         time.Now(),
		},
	}
	
	// Initialize all clients
	if err := clients.initializeClients(); err != nil {
		return nil, fmt.Errorf("failed to initialize clients: %w", err)
	}
	
	return clients, nil
}

// initializeClients initializes all infrastructure clients
func (c *InfraClients) initializeClients() error {
	var err error
	
	// Initialize Supabase client
	c.supabase, err = NewSupabaseClient(c.config, c.logger)
	if err != nil {
		c.logger.Warn("Failed to initialize Supabase client", "error", err)
	}
	
	// Other clients will be initialized later
	// TODO: Add Redis, DuckDB, Neo4j, InfluxDB, MinIO, Loki, NATS, MQTT clients
	
	c.logger.Info("Infrastructure clients initialized")
	return nil
}

// Close gracefully closes all client connections
func (c *InfraClients) Close() error {
	c.logger.Info("Closing infrastructure clients...")
	
	var errors []error
	
	if c.supabase != nil {
		if err := c.supabase.Close(); err != nil {
			errors = append(errors, fmt.Errorf("supabase: %w", err))
		}
	}
	
	// Other clients will be added later
	// TODO: Close Redis, DuckDB, Neo4j, InfluxDB, MinIO, Loki, NATS, MQTT clients
	
	if len(errors) > 0 {
		return fmt.Errorf("errors closing clients: %v", errors)
	}
	
	return nil
}

// HealthCheck performs a basic health check on all services
func (c *InfraClients) HealthCheck() map[string]interface{} {
	health := make(map[string]interface{})
	
	overall := true
	
	// Check each service
	services := map[string]func() bool{
		"supabase": func() bool { return c.supabase != nil && c.supabase.Ping() == nil },
		// Other services will be added as they are implemented
	}
	
	for service, checkFunc := range services {
		healthy := checkFunc()
		health[service] = healthy
		if !healthy {
			overall = false
		}
	}
	
	health["overall"] = overall
	health["timestamp"] = time.Now()
	
	return health
}

// DetailedHealthCheck performs a detailed health check
func (c *InfraClients) DetailedHealthCheck() map[string]interface{} {
	health := make(map[string]interface{})
	
	// Basic health check
	basicHealth := c.HealthCheck()
	health["basic"] = basicHealth
	
	// Detailed stats
	health["stats"] = c.GetStats()
	
	// Connection details
	health["connections"] = c.GetConnectionStats()
	
	return health
}

// GetStats returns current statistics
func (c *InfraClients) GetStats() *Stats {
	c.mu.RLock()
	defer c.mu.RUnlock()
	
	// Create a copy of stats to avoid race conditions
	statsCopy := &Stats{
		TotalRequests:     c.stats.TotalRequests,
		TotalErrors:       c.stats.TotalErrors,
		ActiveConnections: make(map[string]int),
		ServiceStats:      make(map[string]ServiceStat),
		StartTime:         c.stats.StartTime,
	}
	
	// Copy maps
	for k, v := range c.stats.ActiveConnections {
		statsCopy.ActiveConnections[k] = v
	}
	
	for k, v := range c.stats.ServiceStats {
		statsCopy.ServiceStats[k] = v
	}
	
	return statsCopy
}

// GetConnectionStats returns connection statistics
func (c *InfraClients) GetConnectionStats() map[string]interface{} {
	stats := make(map[string]interface{})
	
	if c.supabase != nil {
		stats["supabase"] = c.supabase.GetConnectionStats()
	}
	
	// Other clients will be added as they are implemented
	
	return stats
}

// FlushCache flushes all caches
func (c *InfraClients) FlushCache() error {
	// TODO: Add cache flush operations when Redis client is implemented
	return nil
}

// Execute methods for each service

// ExecuteSupabase executes a Supabase operation
func (c *InfraClients) ExecuteSupabase(ctx context.Context, operation string, params map[string]interface{}) (interface{}, error) {
	if c.supabase == nil {
		return nil, fmt.Errorf("supabase client not initialized")
	}
	
	c.updateStats("supabase")
	return c.supabase.Execute(ctx, operation, params)
}

// ExecuteRedis executes a Redis operation
func (c *InfraClients) ExecuteRedis(ctx context.Context, operation string, params map[string]interface{}) (interface{}, error) {
	return nil, fmt.Errorf("redis client not implemented yet")
}

// ExecuteDuckDB executes a DuckDB operation
func (c *InfraClients) ExecuteDuckDB(ctx context.Context, operation string, params map[string]interface{}) (interface{}, error) {
	return nil, fmt.Errorf("duckdb client not implemented yet")
}

// ExecuteNeo4j executes a Neo4j operation
func (c *InfraClients) ExecuteNeo4j(ctx context.Context, operation string, params map[string]interface{}) (interface{}, error) {
	return nil, fmt.Errorf("neo4j client not implemented yet")
}

// ExecuteInfluxDB executes an InfluxDB operation
func (c *InfraClients) ExecuteInfluxDB(ctx context.Context, operation string, params map[string]interface{}) (interface{}, error) {
	return nil, fmt.Errorf("influxdb client not implemented yet")
}

// ExecuteMinIO executes a MinIO operation
func (c *InfraClients) ExecuteMinIO(ctx context.Context, operation string, params map[string]interface{}) (interface{}, error) {
	return nil, fmt.Errorf("minio client not implemented yet")
}

// ExecuteLoki executes a Loki operation
func (c *InfraClients) ExecuteLoki(ctx context.Context, operation string, params map[string]interface{}) (interface{}, error) {
	return nil, fmt.Errorf("loki client not implemented yet")
}

// ExecuteNATS executes a NATS operation
func (c *InfraClients) ExecuteNATS(ctx context.Context, operation string, params map[string]interface{}) (interface{}, error) {
	return nil, fmt.Errorf("nats client not implemented yet")
}

// ExecuteMQTT executes an MQTT operation
func (c *InfraClients) ExecuteMQTT(ctx context.Context, operation string, params map[string]interface{}) (interface{}, error) {
	return nil, fmt.Errorf("mqtt client not implemented yet")
}

// updateStats updates request statistics
func (c *InfraClients) updateStats(service string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	
	c.stats.TotalRequests++
	
	stat := c.stats.ServiceStats[service]
	stat.Requests++
	stat.LastRequest = time.Now()
	c.stats.ServiceStats[service] = stat
}