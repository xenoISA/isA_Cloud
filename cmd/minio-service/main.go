// MinIO gRPC 服务端主程序
// 文件名: cmd/minio-service/main.go
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
	"github.com/isa-cloud/isa_cloud/cmd/minio-service/server"
	"github.com/isa-cloud/isa_cloud/pkg/storage"
)

const (
	serviceName = "minio-service"
	defaultPort = 50051
)

func main() {
	factory, err := storage.NewStorageClientFactory()
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	cfg := factory.GetConfig()
	port := cfg.MinIO.GRPCPort
	if port == 0 {
		port = defaultPort
	}

	ctx := context.Background()
	minioClient, err := factory.NewMinIOClient(ctx)
	if err != nil {
		log.Fatalf("Failed to create MinIO client: %v", err)
	}
	defer minioClient.Close()

	grpcServer := grpc.NewServer(
		grpc.MaxRecvMsgSize(50*1024*1024), // 50MB
		grpc.MaxSendMsgSize(50*1024*1024),
	)

	minioServer, err := server.NewMinIOServer(minioClient, cfg)
	if err != nil {
		log.Fatalf("Failed to create MinIO server: %v", err)
	}

	pb.RegisterMinIOServiceServer(grpcServer, minioServer)

	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus(serviceName, grpc_health_v1.HealthCheckResponse_SERVING)
	reflection.Register(grpcServer)

	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", port))
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	log.Printf("MinIO gRPC Service listening on :%d", port)

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


