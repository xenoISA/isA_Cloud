// Loki gRPC 服务端主程序
// 文件名: cmd/loki-service/main.go
package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"
	"syscall"

	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"

	"github.com/hashicorp/consul/api"
	pb "github.com/isa-cloud/isa_cloud/api/proto"
	"github.com/isa-cloud/isa_cloud/cmd/loki-service/server"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/logging"
)

const (
	serviceName = "loki-service"
	defaultPort = 50054
)

func main() {
	factory, err := logging.NewLoggingClientFactory()
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	cfg := factory.GetConfig()
	port := cfg.Loki.GRPCPort
	if port == 0 {
		port = defaultPort
	}

	ctx := context.Background()
	lokiClient, err := factory.NewLokiClient(ctx)
	if err != nil {
		log.Fatalf("Failed to create Loki client: %v", err)
	}
	defer lokiClient.Close()

	grpcServer := grpc.NewServer()
	lokiServer, err := server.NewLokiServer(lokiClient, cfg)
	if err != nil {
		log.Fatalf("Failed to create Loki server: %v", err)
	}

	pb.RegisterLokiServiceServer(grpcServer, lokiServer)

	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus(serviceName, grpc_health_v1.HealthCheckResponse_SERVING)
	reflection.Register(grpcServer)

	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", port))
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	log.Printf("Loki gRPC Service listening on :%d", port)

	// Register with Consul if enabled
	var consulClient *api.Client
	var serviceID string
	if cfg.Consul.Enabled {
		consulClient, serviceID, err = registerConsul(cfg, port)
		if err != nil {
			log.Printf("Warning: Failed to register with Consul: %v", err)
		} else {
			log.Printf("Registered to Consul with service ID: %s", serviceID)
		}
	}

	go handleShutdown(grpcServer, consulClient, serviceID)

	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}
}

// registerConsul registers service with Consul
func registerConsul(cfg *logging.LoggingConfig, port int) (*api.Client, string, error) {
	consulConfig := api.DefaultConfig()
	consulConfig.Address = fmt.Sprintf("%s:%d", cfg.Consul.Host, cfg.Consul.Port)

	client, err := api.NewClient(consulConfig)
	if err != nil {
		return nil, "", err
	}

	// Get service hostname (prioritize env variable for Docker Compose)
	serviceHostname := os.Getenv("SERVICE_HOSTNAME")
	if serviceHostname == "" {
		serviceHostname = os.Getenv("HOSTNAME")
	}
	if serviceHostname == "" {
		hostname, _ := os.Hostname()
		serviceHostname = hostname
	}

	serviceID := fmt.Sprintf("%s-%s", serviceName, serviceHostname)

	// Register service
	registration := &api.AgentServiceRegistration{
		ID:      serviceID,
		Name:    "loki-grpc-service",
		Address: serviceHostname,
		Port:    port,
		Tags:    []string{"grpc", "logging", "loki"},
		Meta: map[string]string{
			"container_name": serviceHostname,
			"service_type":   "grpc",
		},
		Check: &api.AgentServiceCheck{
			GRPC:                           fmt.Sprintf("%s:%d/%s", serviceHostname, port, serviceName),
			Interval:                       "10s",
			Timeout:                        "5s",
			DeregisterCriticalServiceAfter: "30s",
		},
	}

	if err := client.Agent().ServiceRegister(registration); err != nil {
		return nil, "", err
	}

	return client, serviceID, nil
}

func handleShutdown(grpcServer *grpc.Server, consulClient *api.Client, serviceID string) {
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh
	log.Println("Shutting down gracefully...")

	// Deregister from Consul
	if consulClient != nil && serviceID != "" {
		if err := consulClient.Agent().ServiceDeregister(serviceID); err != nil {
			log.Printf("Error deregistering from Consul: %v", err)
		} else {
			log.Printf("Deregistered from Consul: %s", serviceID)
		}
	}

	grpcServer.GracefulStop()
	os.Exit(0)
}


