package gateway

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
	"google.golang.org/grpc"

	"github.com/isa-cloud/isa_cloud/internal/config"
	"github.com/isa-cloud/isa_cloud/pkg/logger"
	"github.com/isa-cloud/isa_cloud/internal/gateway/middleware"
	"github.com/isa-cloud/isa_cloud/internal/gateway/clients"
	"github.com/isa-cloud/isa_cloud/internal/gateway/proxy"
	"github.com/isa-cloud/isa_cloud/internal/gateway/registry"
	"github.com/isa-cloud/isa_cloud/internal/gateway/blockchain"
	"github.com/isa-cloud/isa_cloud/internal/gateway/mqtt"
)

// Gateway represents the main gateway service
type Gateway struct {
	config            *config.Config
	logger            *logger.Logger
	clients           *clients.ServiceClients
	dynamicProxy      *proxy.DynamicProxy
	registry          *registry.ConsulRegistry
	blockchainGateway *blockchain.Gateway
	mqttAdapter       *mqtt.Adapter
}

// New creates a new Gateway instance
func New(cfg *config.Config, logger *logger.Logger) (*Gateway, error) {
	// Initialize service clients
	serviceClients, err := clients.New(cfg, logger)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize service clients: %w", err)
	}

	// Initialize Consul registry (optional - will work without it)
	var consulRegistry *registry.ConsulRegistry
	if cfg.Consul.Enabled {
		consulAddress := fmt.Sprintf("%s:%d", cfg.Consul.Host, cfg.Consul.Port)
		consulRegistry, err = registry.NewConsulRegistry(consulAddress, logger)
		if err != nil {
			logger.Warn("Failed to connect to Consul, using static configuration", "error", err)
			// Continue without Consul - will use static config
		} else {
			logger.Info("Connected to Consul service registry", "address", consulAddress)

			// Register gateway itself with Consul
			gatewayHost := cfg.Server.Host
			if gatewayHost == "0.0.0.0" {
				// Use hostname instead of 0.0.0.0 for Consul registration
				if hostname, err := os.Hostname(); err == nil {
					gatewayHost = hostname
				} else {
					gatewayHost = "localhost"
				}
			}
			err = consulRegistry.RegisterService("gateway", gatewayHost, cfg.Server.HTTPPort, []string{"api", "gateway"})
			if err != nil {
				logger.Warn("Failed to register gateway with Consul", "error", err)
			}
		}
	}

	// Initialize dynamic proxy
	dynamicProxy := proxy.NewDynamicProxy(cfg, logger, consulRegistry)

	// Initialize blockchain gateway
	var blockchainGateway *blockchain.Gateway
	
	blockchainGateway, err = blockchain.NewGateway(cfg, logger)
	if err != nil {
		logger.Warn("Failed to initialize blockchain gateway", "error", err)
		// Continue without blockchain - optional feature
	} else {
		logger.Info("Blockchain gateway initialized successfully")
		
		// Register blockchain services with Consul if available
		if consulRegistry != nil {
			consulIntegration := blockchain.NewConsulIntegration(blockchainGateway, consulRegistry, logger)
			if err := consulIntegration.RegisterBlockchainServices("localhost", 8545); err != nil {
				logger.Warn("Failed to register blockchain services with Consul", "error", err)
			}
		}
	}

	// Initialize MQTT adapter
	var mqttAdapter *mqtt.Adapter
	if cfg.MQTT.Enabled && cfg.DeviceManagement.Enabled {
		mqttAdapter = mqtt.NewAdapter(&cfg.MQTT, &cfg.DeviceManagement, logger)
		if err := mqttAdapter.Connect(); err != nil {
			logger.Warn("Failed to connect MQTT adapter", "error", err)
		} else {
			logger.Info("MQTT adapter initialized successfully")
		}
	}

	return &Gateway{
		config:            cfg,
		logger:            logger,
		clients:           serviceClients,
		dynamicProxy:      dynamicProxy,
		registry:          consulRegistry,
		blockchainGateway: blockchainGateway,
		mqttAdapter:       mqttAdapter,
	}, nil
}

// SetupHTTPRoutes sets up HTTP routes and middleware
func (g *Gateway) SetupHTTPRoutes() *gin.Engine {
	// Create router
	router := gin.New()

	// Add middleware
	router.Use(gin.Recovery())
	router.Use(middleware.RequestLogger(g.logger))
	router.Use(middleware.RequestID())
	
	// CORS middleware
	if g.config.Security.CORS.Enabled {
		corsConfig := cors.Config{
			AllowOrigins:     g.config.Security.CORS.AllowOrigins,
			AllowMethods:     g.config.Security.CORS.AllowMethods,
			AllowHeaders:     g.config.Security.CORS.AllowHeaders,
			AllowCredentials: g.config.Security.CORS.AllowCredentials,
			MaxAge:           12 * time.Hour,
			// Allow all localhost origins dynamically (any port)
			AllowOriginFunc: func(origin string) bool {
				// Always allow if origin is in AllowOrigins list
				for _, allowed := range g.config.Security.CORS.AllowOrigins {
					if allowed == "*" || allowed == origin {
						return true
					}
				}
				// Allow all localhost origins regardless of port
				if strings.HasPrefix(origin, "http://localhost") ||
				   strings.HasPrefix(origin, "http://127.0.0.1") ||
				   strings.HasPrefix(origin, "https://localhost") ||
				   strings.HasPrefix(origin, "https://127.0.0.1") {
					return true
				}
				return false
			},
		}
		router.Use(cors.New(corsConfig))
	}

	// Rate limiting middleware
	if g.config.Security.RateLimit.Enabled {
		switch g.config.Security.RateLimit.Type {
		case "tiered":
			// Tiered rate limiting based on subscription
			freeRPS := g.config.Security.RateLimit.TierLimits["free"]
			proRPS := g.config.Security.RateLimit.TierLimits["pro"]
			enterpriseRPS := g.config.Security.RateLimit.TierLimits["enterprise"]
			if freeRPS == 0 {
				freeRPS = g.config.Security.RateLimit.RPS
			}
			if proRPS == 0 {
				proRPS = g.config.Security.RateLimit.RPS * 5
			}
			if enterpriseRPS == 0 {
				enterpriseRPS = g.config.Security.RateLimit.RPS * 20
			}
			router.Use(middleware.TieredRateLimit(freeRPS, proRPS, enterpriseRPS, g.config.Security.RateLimit.Burst, g.logger))
		case "per_user", "per_ip":
			// Per-user or per-IP rate limiting
			router.Use(middleware.PerUserRateLimit(g.config.Security.RateLimit.RPS, g.config.Security.RateLimit.Burst, g.logger))
		default:
			// Fallback to global rate limiting
			router.Use(middleware.RateLimit(g.config.Security.RateLimit.RPS, g.config.Security.RateLimit.Burst))
		}
	}

	// Health check
	router.GET("/health", g.healthCheck)
	router.HEAD("/health", g.healthCheck)
	router.GET("/ready", g.readinessCheck)

	// Gateway management routes (these don't go through the proxy)
	gateway := router.Group("/api/v1/gateway")
	gateway.Use(middleware.UnifiedAuthentication(g.clients.Auth, g.registry, g.config, g.logger))
	gateway.GET("/services", g.listServices)
	gateway.GET("/metrics", g.getMetrics)
	gateway.GET("/health", g.servicesHealth)

	// Blockchain routes (if blockchain gateway is available)
	if g.blockchainGateway != nil {
		blockchainAPI := router.Group("/api/v1/blockchain")
		blockchainAPI.Use(middleware.UnifiedAuthentication(g.clients.Auth, g.registry, g.config, g.logger))
		
		// Blockchain endpoints
		blockchainAPI.GET("/status", g.blockchainStatus)
		blockchainAPI.GET("/balance/:address", g.getBalance)
		blockchainAPI.POST("/transaction", g.sendTransaction)
		blockchainAPI.GET("/transaction/:hash", g.getTransaction)
		blockchainAPI.GET("/block/:number", g.getBlock)
	}

	// MQTT and Device Management routes (if MQTT adapter is available)
	if g.mqttAdapter != nil {
		deviceAPI := router.Group("/api/v1/devices")
		deviceAPI.Use(middleware.UnifiedAuthentication(g.clients.Auth, g.registry, g.config, g.logger))

		// Device management endpoints
		deviceAPI.GET("/mqtt/status", g.mqttStatus)
		deviceAPI.GET("/mqtt/stats", g.mqttStats)
		deviceAPI.POST("/:device_id/commands", g.sendDeviceCommand)
		deviceAPI.GET("/stats", g.deviceStats)

		// MQTT notification endpoints
		mqttAPI := router.Group("/api/v1/mqtt")
		mqttAPI.Use(middleware.UnifiedAuthentication(g.clients.Auth, g.registry, g.config, g.logger))
		mqttAPI.POST("/publish/notification", g.publishNotification)
	}
	
	// Set up dynamic proxy for service routes
	// Use NoRoute to handle all unmatched requests for dynamic service discovery
	router.NoRoute(g.dynamicProxy.Handler())

	return router
}

// RegisterGRPCServices registers gRPC services
func (g *Gateway) RegisterGRPCServices(server *grpc.Server) {
	// Register gateway management services
	// Note: We'll implement these as needed
}

// GRPCUnaryInterceptor returns a gRPC unary interceptor
func (g *Gateway) GRPCUnaryInterceptor() grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req interface{}, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (interface{}, error) {
		start := time.Now()
		
		// Log request
		g.logger.Debug("gRPC request", 
			"method", info.FullMethod,
			"start_time", start,
		)

		// Call handler
		resp, err := handler(ctx, req)

		// Log response
		duration := time.Since(start)
		if err != nil {
			g.logger.Error("gRPC request failed",
				"method", info.FullMethod,
				"duration", duration,
				"error", err,
			)
		} else {
			g.logger.Debug("gRPC request completed",
				"method", info.FullMethod,
				"duration", duration,
			)
		}

		return resp, err
	}
}

// GRPCStreamInterceptor returns a gRPC stream interceptor
func (g *Gateway) GRPCStreamInterceptor() grpc.StreamServerInterceptor {
	return func(srv interface{}, stream grpc.ServerStream, info *grpc.StreamServerInfo, handler grpc.StreamHandler) error {
		start := time.Now()
		
		g.logger.Debug("gRPC stream started", 
			"method", info.FullMethod,
			"start_time", start,
		)

		err := handler(srv, stream)

		duration := time.Since(start)
		if err != nil {
			g.logger.Error("gRPC stream failed",
				"method", info.FullMethod,
				"duration", duration,
				"error", err,
			)
		} else {
			g.logger.Debug("gRPC stream completed",
				"method", info.FullMethod,
				"duration", duration,
			)
		}

		return err
	}
}

// Shutdown gracefully shuts down the gateway
func (g *Gateway) Shutdown(ctx context.Context) error {
	g.logger.Info("Shutting down gateway...")
	
	// Disconnect MQTT adapter
	if g.mqttAdapter != nil {
		g.mqttAdapter.Disconnect()
		g.logger.Info("MQTT adapter disconnected")
	}
	
	// Close service clients
	if err := g.clients.Close(); err != nil {
		g.logger.Error("Failed to close service clients", "error", err)
		return err
	}

	g.logger.Info("Gateway shutdown completed")
	return nil
}

// Health check endpoint
func (g *Gateway) healthCheck(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status":    "healthy",
		"service":   "isa-cloud-gateway",
		"version":   g.config.App.Version,
		"timestamp": time.Now().UTC(),
	})
}

// Readiness check endpoint
func (g *Gateway) readinessCheck(c *gin.Context) {
	// Check service connectivity
	ready := true
	services := make(map[string]bool)

	// Check each service
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := g.clients.CheckConnectivity(ctx); err != nil {
		ready = false
		g.logger.Error("Service connectivity check failed", "error", err)
	}

	// Get individual service status
	services["user_service"] = g.clients.User != nil
	services["auth_service"] = g.clients.Auth != nil
	services["agent_service"] = g.clients.Agent != nil
	services["model_service"] = g.clients.Model != nil
	services["mcp_service"] = g.clients.MCP != nil
	// services["blockchain_gateway"] = g.clients.Blockchain != nil  // Temporarily disabled

	status := http.StatusOK
	if !ready {
		status = http.StatusServiceUnavailable
	}

	c.JSON(status, gin.H{
		"ready":     ready,
		"services":  services,
		"timestamp": time.Now().UTC(),
	})
}

// List services endpoint
func (g *Gateway) listServices(c *gin.Context) {
	services := []map[string]interface{}{
		{
			"name":      "user_service",
			"host":      g.config.Services.UserService.Host,
			"http_port": g.config.Services.UserService.HTTPPort,
			"grpc_port": g.config.Services.UserService.GRPCPort,
			"status":    "connected",
		},
		{
			"name":      "auth_service", 
			"host":      g.config.Services.AuthService.Host,
			"http_port": g.config.Services.AuthService.HTTPPort,
			"grpc_port": g.config.Services.AuthService.GRPCPort,
			"status":    "connected",
		},
		{
			"name":      "agent_service",
			"host":      g.config.Services.AgentService.Host,
			"http_port": g.config.Services.AgentService.HTTPPort,
			"grpc_port": g.config.Services.AgentService.GRPCPort,
			"status":    "connected",
		},
		{
			"name":      "model_service",
			"host":      g.config.Services.ModelService.Host,
			"http_port": g.config.Services.ModelService.HTTPPort,
			"grpc_port": g.config.Services.ModelService.GRPCPort,
			"status":    "connected",
		},
		{
			"name":      "mcp_service",
			"host":      g.config.Services.MCPService.Host,
			"http_port": g.config.Services.MCPService.HTTPPort,
			"grpc_port": g.config.Services.MCPService.GRPCPort,
			"status":    "connected",
		},
	}

	// Add blockchain service if enabled (temporarily disabled)
	// if g.clients.Blockchain != nil {
	// 	blockchainService := map[string]interface{}{
	// 		"name":         "blockchain_gateway",
	// 		"rpc_endpoint": g.config.Blockchain.RPCEndpoint,
	// 		"chain_id":     g.config.Blockchain.ChainID,
	// 		"network":      g.config.Blockchain.NetworkName,
	// 		"status":       "connected",
	// 	}
	// 	services = append(services, blockchainService)
	// }

	c.JSON(http.StatusOK, gin.H{
		"services": services,
		"total":    len(services),
	})
}

// Get metrics endpoint
func (g *Gateway) getMetrics(c *gin.Context) {
	// TODO: Implement actual metrics collection
	c.JSON(http.StatusOK, gin.H{
		"gateway": map[string]interface{}{
			"uptime":           time.Since(time.Now()).String(),
			"total_requests":   0,
			"active_requests":  0,
			"error_rate":       0.0,
			"average_latency":  "0ms",
		},
		"services": map[string]interface{}{
			"user_service":  map[string]interface{}{"requests": 0, "errors": 0},
			"auth_service":  map[string]interface{}{"requests": 0, "errors": 0},
			"agent_service": map[string]interface{}{"requests": 0, "errors": 0},
			"model_service": map[string]interface{}{"requests": 0, "errors": 0},
			"mcp_service":   map[string]interface{}{"requests": 0, "errors": 0},
		},
	})
}

// Services health endpoint
func (g *Gateway) servicesHealth(c *gin.Context) {
	health := g.dynamicProxy.HealthCheck()
	
	allHealthy := true
	for _, healthy := range health {
		if !healthy {
			allHealthy = false
			break
		}
	}
	
	status := http.StatusOK
	if !allHealthy {
		status = http.StatusServiceUnavailable
	}
	
	c.JSON(status, gin.H{
		"healthy":  allHealthy,
		"services": health,
		"timestamp": time.Now().UTC(),
	})
}

// MQTT status endpoint
func (g *Gateway) mqttStatus(c *gin.Context) {
	if g.mqttAdapter == nil {
		c.JSON(http.StatusNotFound, gin.H{
			"error": "MQTT adapter not available",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"connected": g.mqttAdapter.IsConnected(),
		"stats":     g.mqttAdapter.GetStats(),
		"timestamp": time.Now().UTC(),
	})
}

// MQTT statistics endpoint
func (g *Gateway) mqttStats(c *gin.Context) {
	if g.mqttAdapter == nil {
		c.JSON(http.StatusNotFound, gin.H{
			"error": "MQTT adapter not available",
		})
		return
	}

	c.JSON(http.StatusOK, g.mqttAdapter.GetStats())
}

// Send command to device endpoint
func (g *Gateway) sendDeviceCommand(c *gin.Context) {
	if g.mqttAdapter == nil {
		c.JSON(http.StatusNotFound, gin.H{
			"error": "MQTT adapter not available",
		})
		return
	}

	deviceID := c.Param("device_id")
	if deviceID == "" {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": "device_id is required",
		})
		return
	}

	var command map[string]interface{}
	if err := c.ShouldBindJSON(&command); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": "Invalid JSON payload",
		})
		return
	}

	// Add metadata to command
	command["timestamp"] = time.Now().UTC().Format(time.RFC3339)
	command["source"] = "gateway"

	if err := g.mqttAdapter.SendCommandToDevice(deviceID, command); err != nil {
		g.logger.Error("Failed to send device command", 
			"device_id", deviceID, 
			"error", err,
		)
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": "Failed to send command",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success":   true,
		"device_id": deviceID,
		"command":   command,
		"timestamp": time.Now().UTC(),
	})
}

// Device statistics endpoint
func (g *Gateway) deviceStats(c *gin.Context) {
	// This would typically aggregate stats from device management services
	// For now, return basic info
	c.JSON(http.StatusOK, gin.H{
		"mqtt": map[string]interface{}{
			"enabled":   g.config.MQTT.Enabled,
			"connected": g.mqttAdapter != nil && g.mqttAdapter.IsConnected(),
		},
		"device_management": map[string]interface{}{
			"enabled": g.config.DeviceManagement.Enabled,
		},
		"timestamp": time.Now().UTC(),
	})
}

// Publish notification via MQTT endpoint
func (g *Gateway) publishNotification(c *gin.Context) {
	if g.mqttAdapter == nil {
		c.JSON(http.StatusNotFound, gin.H{
			"error": "MQTT adapter not available",
		})
		return
	}

	var req struct {
		Type         string                 `json:"type" binding:"required"`          // "user", "broadcast", "system"
		UserID       string                 `json:"user_id"`                          // Required for type="user"
		SystemID     string                 `json:"system_id"`                        // Required for type="system"
		Notification map[string]interface{} `json:"notification" binding:"required"` // Notification payload
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": "Invalid JSON payload: " + err.Error(),
		})
		return
	}

	// Add timestamp to notification
	req.Notification["timestamp"] = time.Now().UTC().Format(time.RFC3339)
	req.Notification["source"] = "gateway"

	var err error
	switch req.Type {
	case "user":
		if req.UserID == "" {
			c.JSON(http.StatusBadRequest, gin.H{
				"error": "user_id is required for user notifications",
			})
			return
		}
		err = g.mqttAdapter.PublishNotificationToUser(req.UserID, req.Notification)

	case "broadcast":
		err = g.mqttAdapter.PublishBroadcastNotification(req.Notification)

	case "system":
		if req.SystemID == "" {
			c.JSON(http.StatusBadRequest, gin.H{
				"error": "system_id is required for system notifications",
			})
			return
		}
		err = g.mqttAdapter.PublishSystemNotification(req.SystemID, req.Notification)

	default:
		c.JSON(http.StatusBadRequest, gin.H{
			"error": "Invalid notification type. Must be 'user', 'broadcast', or 'system'",
		})
		return
	}

	if err != nil {
		g.logger.Error("Failed to publish notification via MQTT",
			"type", req.Type,
			"user_id", req.UserID,
			"system_id", req.SystemID,
			"error", err,
		)
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": "Failed to publish notification: " + err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success":   true,
		"type":      req.Type,
		"user_id":   req.UserID,
		"system_id": req.SystemID,
		"timestamp": time.Now().UTC(),
	})
}