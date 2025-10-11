// NATS gRPC 服务端主程序
// 文件名: cmd/nats-service/main.go
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
	"github.com/isa-cloud/isa_cloud/cmd/nats-service/server"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/event"
)

const (
	serviceName = "nats-service"
	defaultPort = 50056
)

func main() {
	factory, err := event.NewEventClientFactory()
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	cfg := factory.GetConfig()
	port := cfg.NATS.GRPCPort
	if port == 0 {
		port = defaultPort
	}

	ctx := context.Background()
	natsClient, err := factory.NewNATSClient(ctx)
	if err != nil {
		log.Fatalf("Failed to create NATS client: %v", err)
	}
	defer natsClient.Close()

	grpcServer := grpc.NewServer()
	natsServer, err := server.NewNATSServer(natsClient, cfg)
	if err != nil {
		log.Fatalf("Failed to create NATS server: %v", err)
	}

	pb.RegisterNATSServiceServer(grpcServer, natsServer)

	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus(serviceName, grpc_health_v1.HealthCheckResponse_SERVING)
	reflection.Register(grpcServer)

	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", port))
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	log.Printf("NATS gRPC Service listening on :%d", port)

	go handleShutdown(grpcServer)

	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}
}

func handleShutdown(grpcServer *grpc.Server) {
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh
	grpcServer.GracefulStop()
	os.Exit(0)
}


