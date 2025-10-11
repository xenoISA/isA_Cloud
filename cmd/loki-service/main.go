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

	go handleShutdown(grpcServer)

	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}
}

func handleShutdown(grpcServer *grpc.Server) {
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh
	log.Println("Shutting down gracefully...")
	grpcServer.GracefulStop()
	os.Exit(0)
}


