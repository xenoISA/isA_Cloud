package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"
	"syscall"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"

	pb "github.com/isa-cloud/isa_cloud/api/proto/container"
	"github.com/isa-cloud/isa_cloud/cmd/container-service/server"
)

const (
	defaultPort        = "50064"
	defaultServiceName = "container-grpc"
)

func main() {
	// Get port from environment or use default
	port := os.Getenv("CONTAINER_SERVICE_PORT")
	if port == "" {
		port = defaultPort
	}

	// Get service name from environment or use default
	serviceName := os.Getenv("SERVICE_NAME")
	if serviceName == "" {
		serviceName = defaultServiceName
	}

	log.Printf("Starting %s on port %s", serviceName, port)

	// Create TCP listener
	lis, err := net.Listen("tcp", fmt.Sprintf(":%s", port))
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	// Create gRPC server
	grpcServer := grpc.NewServer(
		grpc.MaxRecvMsgSize(100 * 1024 * 1024), // 100MB max message size
		grpc.MaxSendMsgSize(100 * 1024 * 1024),
	)

	// Initialize backend (Docker or Ignite)
	backend := os.Getenv("CONTAINER_BACKEND")
	if backend == "" {
		backend = "ignite" // default to ignite
	}

	var containerBackend server.ContainerBackend
	if backend == "docker" {
		log.Printf("Using Docker backend")
		dockerClient, err := server.NewDockerClient()
		if err != nil {
			log.Fatalf("Failed to create Docker client: %v", err)
		}
		containerBackend = dockerClient
	} else {
		log.Printf("Using Ignite backend")
		igniteClient, err := server.NewIgniteClient()
		if err != nil {
			log.Fatalf("Failed to create Ignite client: %v", err)
		}
		containerBackend = igniteClient
	}

	// Create container service
	containerService := server.NewContainerService(containerBackend)

	// Register service
	pb.RegisterContainerServiceServer(grpcServer, containerService)

	// Register health check
	healthServer := health.NewServer()
	healthServer.SetServingStatus(serviceName, grpc_health_v1.HealthCheckResponse_SERVING)
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)

	// Register reflection (for grpcurl)
	reflection.Register(grpcServer)

	// Graceful shutdown
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
		<-sigChan

		log.Println("Shutting down gracefully...")
		healthServer.SetServingStatus(serviceName, grpc_health_v1.HealthCheckResponse_NOT_SERVING)

		// Give 30 seconds for graceful shutdown
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()

		done := make(chan struct{})
		go func() {
			grpcServer.GracefulStop()
			close(done)
		}()

		select {
		case <-done:
			log.Println("Graceful shutdown completed")
		case <-ctx.Done():
			log.Println("Shutdown timeout, forcing stop")
			grpcServer.Stop()
		}
	}()

	// Start server
	log.Printf("✅ %s listening on :%s", serviceName, port)
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}
}
