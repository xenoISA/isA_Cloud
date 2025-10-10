package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/spf13/cobra"
	"github.com/spf13/viper"
	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"

	"github.com/isa-cloud/isa_cloud/internal/gateway"
	"github.com/isa-cloud/isa_cloud/internal/config"
	"github.com/isa-cloud/isa_cloud/pkg/logger"
)

var (
	configFile string
	rootCmd    = &cobra.Command{
		Use:   "gateway",
		Short: "IsA Cloud Gateway Service",
		Long:  "Unified gateway service for IsA Cloud ecosystem",
		Run:   runGateway,
	}
)

func init() {
	rootCmd.PersistentFlags().StringVar(&configFile, "config", "", "config file (default is deployments/configs/gateway.yaml)")
	rootCmd.PersistentFlags().String("host", "0.0.0.0", "server host")
	rootCmd.PersistentFlags().Int("http-port", 8080, "HTTP server port")
	rootCmd.PersistentFlags().Int("grpc-port", 9080, "gRPC server port")
	rootCmd.PersistentFlags().String("log-level", "info", "log level")
	rootCmd.PersistentFlags().Bool("debug", false, "debug mode")

	viper.BindPFlag("server.host", rootCmd.PersistentFlags().Lookup("host"))
	viper.BindPFlag("server.http_port", rootCmd.PersistentFlags().Lookup("http-port"))
	viper.BindPFlag("server.grpc_port", rootCmd.PersistentFlags().Lookup("grpc-port"))
	viper.BindPFlag("logging.level", rootCmd.PersistentFlags().Lookup("log-level"))
	viper.BindPFlag("debug", rootCmd.PersistentFlags().Lookup("debug"))
}

func main() {
	if err := rootCmd.Execute(); err != nil {
		log.Fatal(err)
	}
}

func runGateway(cmd *cobra.Command, args []string) {
	// Load configuration
	cfg, err := config.Load(configFile)
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	// Initialize logger
	logger := logger.New(cfg.Logging.Level, cfg.Debug)
	logger.Info("Starting IsA Cloud Gateway", 
		"version", cfg.App.Version,
		"environment", cfg.Environment,
	)

	// Create gateway instance
	gw, err := gateway.New(cfg, logger)
	if err != nil {
		logger.Error("Failed to create gateway", "error", err)
		log.Fatal(err)
	}

	// Start servers
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start gRPC server
	go func() {
		if err := startGRPCServer(ctx, gw, cfg, logger); err != nil {
			logger.Error("gRPC server failed", "error", err)
			cancel()
		}
	}()

	// Start HTTP server
	go func() {
		if err := startHTTPServer(ctx, gw, cfg, logger); err != nil {
			logger.Error("HTTP server failed", "error", err)
			cancel()
		}
	}()

	// Wait for shutdown signal
	shutdownCh := make(chan os.Signal, 1)
	signal.Notify(shutdownCh, syscall.SIGINT, syscall.SIGTERM)

	select {
	case <-shutdownCh:
		logger.Info("Shutdown signal received")
	case <-ctx.Done():
		logger.Info("Context cancelled")
	}

	// Graceful shutdown
	logger.Info("Shutting down gateway...")
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if err := gw.Shutdown(shutdownCtx); err != nil {
		logger.Error("Gateway shutdown failed", "error", err)
	} else {
		logger.Info("Gateway shutdown completed")
	}
}

func startGRPCServer(ctx context.Context, gw *gateway.Gateway, cfg *config.Config, logger *logger.Logger) error {
	addr := fmt.Sprintf("%s:%d", cfg.Server.Host, cfg.Server.GRPCPort)
	lis, err := net.Listen("tcp", addr)
	if err != nil {
		return fmt.Errorf("failed to listen on %s: %w", addr, err)
	}

	// Create gRPC server with interceptors
	grpcServer := grpc.NewServer(
		grpc.UnaryInterceptor(gw.GRPCUnaryInterceptor()),
		grpc.StreamInterceptor(gw.GRPCStreamInterceptor()),
	)

	// Register services
	gw.RegisterGRPCServices(grpcServer)

	// Enable reflection for development
	if cfg.Debug {
		reflection.Register(grpcServer)
	}

	logger.Info("Starting gRPC server", "address", addr)

	// Graceful shutdown
	go func() {
		<-ctx.Done()
		logger.Info("Stopping gRPC server...")
		grpcServer.GracefulStop()
	}()

	return grpcServer.Serve(lis)
}

func startHTTPServer(ctx context.Context, gw *gateway.Gateway, cfg *config.Config, logger *logger.Logger) error {
	// Set gin mode
	if !cfg.Debug {
		gin.SetMode(gin.ReleaseMode)
	}

	// Create HTTP router
	router := gw.SetupHTTPRoutes()

	addr := fmt.Sprintf("%s:%d", cfg.Server.Host, cfg.Server.HTTPPort)
	server := &http.Server{
		Addr:         addr,
		Handler:      router,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	logger.Info("Starting HTTP server", "address", addr)

	// Graceful shutdown
	go func() {
		<-ctx.Done()
		logger.Info("Stopping HTTP server...")
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		
		if err := server.Shutdown(shutdownCtx); err != nil {
			logger.Error("HTTP server shutdown failed", "error", err)
		}
	}()

	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		return fmt.Errorf("HTTP server failed: %w", err)
	}

	return nil
}