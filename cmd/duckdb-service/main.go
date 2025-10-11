// DuckDB gRPC 服务端主程序
// 文件名: cmd/duckdb-service/main.go
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
	"github.com/isa-cloud/isa_cloud/cmd/duckdb-service/server"
	"github.com/isa-cloud/isa_cloud/pkg/storage"
)

const (
	serviceName = "duckdb-service"
	defaultPort = 50052
)

func main() {
	factory, err := storage.NewStorageClientFactory()
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	cfg := factory.GetConfig()
	port := cfg.DuckDB.GRPCPort
	if port == 0 {
		port = defaultPort
	}

	ctx := context.Background()
	duckdbClient, err := factory.NewDuckDBClient(ctx)
	if err != nil {
		log.Fatalf("Failed to create DuckDB client: %v", err)
	}
	defer duckdbClient.Close()

	grpcServer := grpc.NewServer()

	duckdbServer, err := server.NewDuckDBServer(duckdbClient, cfg)
	if err != nil {
		log.Fatalf("Failed to create DuckDB server: %v", err)
	}

	pb.RegisterDuckDBServiceServer(grpcServer, duckdbServer)

	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus(serviceName, grpc_health_v1.HealthCheckResponse_SERVING)
	reflection.Register(grpcServer)

	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", port))
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	log.Printf("DuckDB gRPC Service listening on :%d", port)

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


