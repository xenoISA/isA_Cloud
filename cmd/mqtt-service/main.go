// MQTT gRPC 服务端主程序
// 文件名: cmd/mqtt-service/main.go
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
	"github.com/isa-cloud/isa_cloud/cmd/mqtt-service/server"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/messaging"
)

const (
	serviceName = "mqtt-service"
	defaultPort = 50053
)

func main() {
	// 加载配置
	factory, err := messaging.NewMessagingClientFactory()
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	cfg := factory.GetConfig()
	port := cfg.MQTT.GRPCPort
	if port == 0 {
		port = defaultPort
	}

	// 创建 MQTT 客户端
	ctx := context.Background()
	mqttClient, err := factory.NewMQTTClient(ctx)
	if err != nil {
		log.Fatalf("Failed to create MQTT client: %v", err)
	}
	defer mqttClient.Close()

	log.Printf("MQTT client connected to %s", cfg.MQTT.BrokerURL)

	// 创建 gRPC 服务器
	grpcServer := grpc.NewServer()

	// 创建 MQTT gRPC 服务实现
	mqttServer, err := server.NewMQTTServer(mqttClient, cfg)
	if err != nil {
		log.Fatalf("Failed to create MQTT server: %v", err)
	}

	// 注册服务
	pb.RegisterMQTTServiceServer(grpcServer, mqttServer)

	// 注册健康检查
	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus(serviceName, grpc_health_v1.HealthCheckResponse_SERVING)

	// 注册反射
	reflection.Register(grpcServer)

	// 启动监听
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", port))
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	log.Printf("MQTT gRPC Service listening on :%d", port)

	// 优雅关闭
	go handleShutdown(grpcServer)

	// 启动服务
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
	log.Println("Server stopped")
	os.Exit(0)
}


