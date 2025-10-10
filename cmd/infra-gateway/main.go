package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/spf13/cobra"
	"github.com/spf13/viper"

	infra_gateway "github.com/isa-cloud/isa_cloud/internal/infra-gateway"
	"github.com/isa-cloud/isa_cloud/internal/config"
	"github.com/isa-cloud/isa_cloud/pkg/logger"
)

var (
	configFile string
	rootCmd    = &cobra.Command{
		Use:   "infra-gateway",
		Short: "IsA Cloud Infrastructure Gateway Service",
		Long:  "Unified gateway service for infrastructure access (Redis, PostgreSQL, MinIO, etc.)",
		Run:   runInfraGateway,
	}
)

func main() {
	rootCmd.PersistentFlags().StringVar(&configFile, "config", "", "config file (default is $HOME/.isa-infra-gateway.yaml)")
	
	if err := rootCmd.Execute(); err != nil {
		fmt.Println(err)
		os.Exit(1)
	}
}

func runInfraGateway(cmd *cobra.Command, args []string) {
	// Initialize configuration
	if err := initConfig(); err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	cfg, err := config.LoadConfig()
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	// Initialize logger
	logger := logger.New(cfg.Logging.Level, cfg.Debug)

	// Initialize infrastructure gateway
	gateway, err := infra_gateway.New(cfg, logger)
	if err != nil {
		log.Fatalf("Failed to initialize infrastructure gateway: %v", err)
	}
	defer gateway.Close()

	// Setup HTTP server
	router := setupRouter(gateway)

	srv := &http.Server{
		Addr:    fmt.Sprintf("%s:%d", cfg.InfraGateway.Host, cfg.InfraGateway.Port),
		Handler: router,
	}

	// Start server in a goroutine
	go func() {
		logger.Info("Starting Infrastructure Gateway", "address", srv.Addr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Error("Failed to start server", "error", err)
		}
	}()

	// Start metrics server
	go func() {
		if cfg.Monitoring.Enabled {
			metricsAddr := fmt.Sprintf(":%d", cfg.Monitoring.Port)
			logger.Info("Starting metrics server", "address", metricsAddr)
			http.ListenAndServe(metricsAddr, promhttp.Handler())
		}
	}()

	// Wait for interrupt signal to gracefully shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logger.Info("Shutting down Infrastructure Gateway...")

	// Graceful shutdown with timeout
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		logger.Error("Server forced to shutdown", "error", err)
	}

	logger.Info("Infrastructure Gateway stopped")
}

func initConfig() error {
	if configFile != "" {
		viper.SetConfigFile(configFile)
	} else {
		viper.SetConfigName(".isa-infra-gateway")
		viper.SetConfigType("yaml")
		viper.AddConfigPath("$HOME")
		viper.AddConfigPath(".")
		viper.AddConfigPath("./configs")
	}

	viper.AutomaticEnv()

	if err := viper.ReadInConfig(); err != nil {
		// Config file not found; ignore error for now
		fmt.Println("Warning: Config file not found, using defaults and environment variables")
	}

	return nil
}

func setupRouter(gateway *infra_gateway.Gateway) *gin.Engine {
	// Set Gin mode based on environment
	if viper.GetBool("debug") {
		gin.SetMode(gin.DebugMode)
	} else {
		gin.SetMode(gin.ReleaseMode)
	}

	router := gin.New()

	// Middleware
	router.Use(gin.Recovery())
	router.Use(corsMiddleware())
	router.Use(requestIDMiddleware())
	router.Use(loggingMiddleware())

	// Health endpoints
	router.GET("/health", gateway.HealthCheck)
	router.GET("/ready", gateway.ReadinessCheck)

	// Infrastructure API endpoints
	api := router.Group("/api/v1/infra")
	{
		// Database operations
		api.POST("/supabase", gateway.HandleSupabaseRequest)
		api.POST("/redis", gateway.HandleRedisRequest)
		api.POST("/duckdb", gateway.HandleDuckDBRequest)
		api.POST("/neo4j", gateway.HandleNeo4jRequest)
		api.POST("/influxdb", gateway.HandleInfluxDBRequest)

		// Object storage
		api.POST("/minio", gateway.HandleMinIORequest)

		// Logging
		api.POST("/loki", gateway.HandleLokiRequest)

		// Message queues
		api.POST("/nats", gateway.HandleNATSRequest)
		api.POST("/mqtt", gateway.HandleMQTTRequest)

		// Batch operations for multiple infrastructure calls
		api.POST("/batch", gateway.HandleBatchRequest)
	}

	// Admin endpoints
	admin := router.Group("/admin")
	{
		admin.GET("/stats", gateway.GetStats)
		admin.GET("/connections", gateway.GetConnectionStats)
		admin.GET("/health-detailed", gateway.GetDetailedHealth)
		admin.POST("/flush-cache", gateway.FlushCache)
		admin.POST("/reload-config", gateway.ReloadConfig)
	}

	return router
}

func corsMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Header("Access-Control-Allow-Origin", "*")
		c.Header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		c.Header("Access-Control-Allow-Headers", "Origin, Content-Type, Accept, Authorization, X-Request-ID, X-Trace-ID")

		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}

		c.Next()
	}
}

func requestIDMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		requestID := c.GetHeader("X-Request-ID")
		if requestID == "" {
			requestID = fmt.Sprintf("%d", time.Now().UnixNano())
		}
		c.Set("request_id", requestID)
		c.Header("X-Request-ID", requestID)
		c.Next()
	}
}

func loggingMiddleware() gin.HandlerFunc {
	return gin.LoggerWithFormatter(func(param gin.LogFormatterParams) string {
		return fmt.Sprintf("[%s] %s %s %d %s %s %s\n",
			param.TimeStamp.Format("2006-01-02 15:04:05"),
			param.Method,
			param.Path,
			param.StatusCode,
			param.Latency,
			param.ClientIP,
			param.ErrorMessage,
		)
	})
}