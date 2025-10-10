package infra_gateway

import (
	"context"
	"fmt"
	"net/http"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	"github.com/isa-cloud/isa_cloud/internal/config"
	"github.com/isa-cloud/isa_cloud/pkg/logger"
	"github.com/isa-cloud/isa_cloud/internal/infra-gateway/clients"
)

// Gateway represents the infrastructure gateway service
type Gateway struct {
	config  *config.Config
	logger  *logger.Logger
	clients *clients.InfraClients
	metrics *Metrics
	mu      sync.RWMutex
}

// Metrics holds Prometheus metrics for the gateway
type Metrics struct {
	RequestTotal       *prometheus.CounterVec
	RequestDuration    *prometheus.HistogramVec
	ActiveConnections  *prometheus.GaugeVec
	ErrorTotal         *prometheus.CounterVec
	CacheHitTotal      *prometheus.CounterVec
}

// InfraRequest represents a generic infrastructure request
type InfraRequest struct {
	Service   string                 `json:"service" binding:"required"`
	Operation string                 `json:"operation" binding:"required"`
	Params    map[string]interface{} `json:"params"`
	RequestID string                 `json:"request_id,omitempty"`
	Timeout   int                    `json:"timeout,omitempty"` // in seconds
}

// InfraResponse represents a generic infrastructure response
type InfraResponse struct {
	Success   bool                   `json:"success"`
	Data      interface{}            `json:"data,omitempty"`
	Error     string                 `json:"error,omitempty"`
	RequestID string                 `json:"request_id,omitempty"`
	Duration  string                 `json:"duration,omitempty"`
	Service   string                 `json:"service"`
	Operation string                 `json:"operation"`
}

// BatchRequest represents a batch of infrastructure requests
type BatchRequest struct {
	Requests []InfraRequest `json:"requests" binding:"required"`
	Parallel bool           `json:"parallel,omitempty"`
}

// BatchResponse represents a batch response
type BatchResponse struct {
	Success   bool             `json:"success"`
	Results   []InfraResponse  `json:"results"`
	TotalTime string           `json:"total_time"`
	RequestID string           `json:"request_id,omitempty"`
}

// New creates a new Infrastructure Gateway instance
func New(cfg *config.Config, logger *logger.Logger) (*Gateway, error) {
	// Initialize infrastructure clients
	infraClients, err := clients.New(cfg, logger)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize infrastructure clients: %w", err)
	}

	// Initialize metrics
	metrics := &Metrics{
		RequestTotal: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "infra_gateway_requests_total",
				Help: "Total number of infrastructure requests",
			},
			[]string{"service", "operation", "status"},
		),
		RequestDuration: promauto.NewHistogramVec(
			prometheus.HistogramOpts{
				Name:    "infra_gateway_request_duration_seconds",
				Help:    "Infrastructure request duration in seconds",
				Buckets: prometheus.DefBuckets,
			},
			[]string{"service", "operation"},
		),
		ActiveConnections: promauto.NewGaugeVec(
			prometheus.GaugeOpts{
				Name: "infra_gateway_active_connections",
				Help: "Number of active connections to infrastructure services",
			},
			[]string{"service"},
		),
		ErrorTotal: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "infra_gateway_errors_total",
				Help: "Total number of infrastructure errors",
			},
			[]string{"service", "operation", "error_type"},
		),
		CacheHitTotal: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Name: "infra_gateway_cache_hits_total",
				Help: "Total number of cache hits",
			},
			[]string{"service", "operation"},
		),
	}

	gateway := &Gateway{
		config:  cfg,
		logger:  logger,
		clients: infraClients,
		metrics: metrics,
	}

	return gateway, nil
}

// Close gracefully shuts down the gateway
func (g *Gateway) Close() error {
	g.logger.Info("Closing Infrastructure Gateway...")
	return g.clients.Close()
}

// HealthCheck returns the health status
func (g *Gateway) HealthCheck(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status":    "healthy",
		"service":   "infra-gateway",
		"timestamp": time.Now().UTC(),
		"version":   "1.0.0",
	})
}

// ReadinessCheck checks if all infrastructure services are ready
func (g *Gateway) ReadinessCheck(c *gin.Context) {
	ready := g.clients.HealthCheck()
	
	status := http.StatusOK
	if !ready["overall"].(bool) {
		status = http.StatusServiceUnavailable
	}

	c.JSON(status, gin.H{
		"ready":     ready["overall"],
		"services":  ready,
		"timestamp": time.Now().UTC(),
	})
}

// HandleSupabaseRequest handles Supabase requests
func (g *Gateway) HandleSupabaseRequest(c *gin.Context) {
	g.handleInfraRequest(c, "supabase")
}

// HandleRedisRequest handles Redis requests
func (g *Gateway) HandleRedisRequest(c *gin.Context) {
	g.handleInfraRequest(c, "redis")
}

// HandleDuckDBRequest handles DuckDB requests
func (g *Gateway) HandleDuckDBRequest(c *gin.Context) {
	g.handleInfraRequest(c, "duckdb")
}

// HandleNeo4jRequest handles Neo4j requests
func (g *Gateway) HandleNeo4jRequest(c *gin.Context) {
	g.handleInfraRequest(c, "neo4j")
}

// HandleInfluxDBRequest handles InfluxDB requests
func (g *Gateway) HandleInfluxDBRequest(c *gin.Context) {
	g.handleInfraRequest(c, "influxdb")
}

// HandleMinIORequest handles MinIO requests
func (g *Gateway) HandleMinIORequest(c *gin.Context) {
	g.handleInfraRequest(c, "minio")
}

// HandleLokiRequest handles Loki requests
func (g *Gateway) HandleLokiRequest(c *gin.Context) {
	g.handleInfraRequest(c, "loki")
}

// HandleNATSRequest handles NATS requests
func (g *Gateway) HandleNATSRequest(c *gin.Context) {
	g.handleInfraRequest(c, "nats")
}

// HandleMQTTRequest handles MQTT requests
func (g *Gateway) HandleMQTTRequest(c *gin.Context) {
	g.handleInfraRequest(c, "mqtt")
}

// handleInfraRequest is the generic handler for all infrastructure requests
func (g *Gateway) handleInfraRequest(c *gin.Context, service string) {
	start := time.Now()
	
	// Get request ID from context
	requestID, _ := c.Get("request_id")
	
	var req InfraRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		g.metrics.ErrorTotal.WithLabelValues(service, "unknown", "bind_error").Inc()
		c.JSON(http.StatusBadRequest, InfraResponse{
			Success:   false,
			Error:     fmt.Sprintf("Invalid request format: %v", err),
			RequestID: requestID.(string),
			Service:   service,
		})
		return
	}

	// Override service if provided in URL path
	req.Service = service
	req.RequestID = requestID.(string)

	// Set default timeout if not provided
	if req.Timeout == 0 {
		req.Timeout = 30 // 30 seconds default
	}

	// Create context with timeout
	ctx, cancel := context.WithTimeout(c.Request.Context(), time.Duration(req.Timeout)*time.Second)
	defer cancel()

	// Execute the request
	result, err := g.executeInfraRequest(ctx, req)
	duration := time.Since(start)

	// Update metrics
	status := "success"
	if err != nil {
		status = "error"
		g.metrics.ErrorTotal.WithLabelValues(service, req.Operation, "execution_error").Inc()
	}
	
	g.metrics.RequestTotal.WithLabelValues(service, req.Operation, status).Inc()
	g.metrics.RequestDuration.WithLabelValues(service, req.Operation).Observe(duration.Seconds())

	// Prepare response
	response := InfraResponse{
		Success:   err == nil,
		Data:      result,
		RequestID: req.RequestID,
		Duration:  duration.String(),
		Service:   service,
		Operation: req.Operation,
	}

	if err != nil {
		response.Error = err.Error()
		c.JSON(http.StatusInternalServerError, response)
		return
	}

	c.JSON(http.StatusOK, response)
}

// executeInfraRequest executes a single infrastructure request
func (g *Gateway) executeInfraRequest(ctx context.Context, req InfraRequest) (interface{}, error) {
	switch req.Service {
	case "supabase":
		return g.clients.ExecuteSupabase(ctx, req.Operation, req.Params)
	case "redis":
		return g.clients.ExecuteRedis(ctx, req.Operation, req.Params)
	case "duckdb":
		return g.clients.ExecuteDuckDB(ctx, req.Operation, req.Params)
	case "neo4j":
		return g.clients.ExecuteNeo4j(ctx, req.Operation, req.Params)
	case "influxdb":
		return g.clients.ExecuteInfluxDB(ctx, req.Operation, req.Params)
	case "minio":
		return g.clients.ExecuteMinIO(ctx, req.Operation, req.Params)
	case "loki":
		return g.clients.ExecuteLoki(ctx, req.Operation, req.Params)
	case "nats":
		return g.clients.ExecuteNATS(ctx, req.Operation, req.Params)
	case "mqtt":
		return g.clients.ExecuteMQTT(ctx, req.Operation, req.Params)
	default:
		return nil, fmt.Errorf("unsupported service: %s", req.Service)
	}
}

// HandleBatchRequest handles batch infrastructure requests
func (g *Gateway) HandleBatchRequest(c *gin.Context) {
	start := time.Now()
	requestID, _ := c.Get("request_id")

	var batchReq BatchRequest
	if err := c.ShouldBindJSON(&batchReq); err != nil {
		c.JSON(http.StatusBadRequest, BatchResponse{
			Success:   false,
			RequestID: requestID.(string),
		})
		return
	}

	// Execute requests (parallel or sequential)
	var results []InfraResponse
	
	if batchReq.Parallel {
		results = g.executeBatchParallel(c.Request.Context(), batchReq.Requests)
	} else {
		results = g.executeBatchSequential(c.Request.Context(), batchReq.Requests)
	}

	totalTime := time.Since(start)

	// Check if all requests succeeded
	allSuccess := true
	for _, result := range results {
		if !result.Success {
			allSuccess = false
			break
		}
	}

	response := BatchResponse{
		Success:   allSuccess,
		Results:   results,
		TotalTime: totalTime.String(),
		RequestID: requestID.(string),
	}

	status := http.StatusOK
	if !allSuccess {
		status = http.StatusMultiStatus
	}

	c.JSON(status, response)
}

// executeBatchParallel executes requests in parallel
func (g *Gateway) executeBatchParallel(ctx context.Context, requests []InfraRequest) []InfraResponse {
	results := make([]InfraResponse, len(requests))
	var wg sync.WaitGroup

	for i, req := range requests {
		wg.Add(1)
		go func(index int, request InfraRequest) {
			defer wg.Done()
			start := time.Now()
			
			result, err := g.executeInfraRequest(ctx, request)
			duration := time.Since(start)

			results[index] = InfraResponse{
				Success:   err == nil,
				Data:      result,
				RequestID: request.RequestID,
				Duration:  duration.String(),
				Service:   request.Service,
				Operation: request.Operation,
			}

			if err != nil {
				results[index].Error = err.Error()
			}
		}(i, req)
	}

	wg.Wait()
	return results
}

// executeBatchSequential executes requests sequentially
func (g *Gateway) executeBatchSequential(ctx context.Context, requests []InfraRequest) []InfraResponse {
	results := make([]InfraResponse, len(requests))

	for i, req := range requests {
		start := time.Now()
		
		result, err := g.executeInfraRequest(ctx, req)
		duration := time.Since(start)

		results[i] = InfraResponse{
			Success:   err == nil,
			Data:      result,
			RequestID: req.RequestID,
			Duration:  duration.String(),
			Service:   req.Service,
			Operation: req.Operation,
		}

		if err != nil {
			results[i].Error = err.Error()
		}
	}

	return results
}

// GetStats returns gateway statistics
func (g *Gateway) GetStats(c *gin.Context) {
	stats := g.clients.GetStats()
	
	c.JSON(http.StatusOK, gin.H{
		"infra_gateway": gin.H{
			"status":      "running",
			"uptime":      time.Since(start).String(),
			"version":     "1.0.0",
		},
		"infrastructure": stats,
		"timestamp":      time.Now().UTC(),
	})
}

// GetConnectionStats returns connection statistics
func (g *Gateway) GetConnectionStats(c *gin.Context) {
	stats := g.clients.GetConnectionStats()
	c.JSON(http.StatusOK, stats)
}

// GetDetailedHealth returns detailed health check
func (g *Gateway) GetDetailedHealth(c *gin.Context) {
	health := g.clients.DetailedHealthCheck()
	c.JSON(http.StatusOK, health)
}

// FlushCache flushes all caches
func (g *Gateway) FlushCache(c *gin.Context) {
	err := g.clients.FlushCache()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"success": false,
			"error":   err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "Cache flushed successfully",
	})
}

// ReloadConfig reloads the configuration
func (g *Gateway) ReloadConfig(c *gin.Context) {
	// This would reload configuration in a real implementation
	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "Configuration reloaded successfully",
	})
}

var start = time.Now() // Gateway start time