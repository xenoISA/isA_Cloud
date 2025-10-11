// Package server implements the DuckDB gRPC service
// 文件名: cmd/duckdb-service/server/server.go
package server

import (
	"context"
	"fmt"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	pb "github.com/isa-cloud/isa_cloud/api/proto"
	"github.com/isa-cloud/isa_cloud/pkg/analytics/duckdb"
	"github.com/isa-cloud/isa_cloud/pkg/storage"
)

// DuckDBServer DuckDB gRPC 服务实现
type DuckDBServer struct {
	pb.UnimplementedDuckDBServiceServer

	duckdbClient *duckdb.Client
	authService  *AuthService
	config       *storage.StorageConfig
}

// NewDuckDBServer 创建 DuckDB gRPC 服务实例
func NewDuckDBServer(duckdbClient *duckdb.Client, cfg *storage.StorageConfig) (*DuckDBServer, error) {
	return &DuckDBServer{
		duckdbClient: duckdbClient,
		authService:  NewAuthService(cfg),
		config:       cfg,
	}, nil
}

// ExecuteQuery 执行查询
func (s *DuckDBServer) ExecuteQuery(ctx context.Context, req *pb.ExecuteQueryRequest) (*pb.ExecuteQueryResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 执行查询
	rows, err := s.duckdbClient.Query(ctx, req.Query)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}
	defer rows.Close()

	// 转换结果
	// TODO: 实现完整的结果转换逻辑

	return &pb.ExecuteQueryResponse{
		Success: true,
		Columns: []string{},       // TODO: 从 rows 提取列名
		Rows:    []*pb.QueryRow{}, // TODO: 转换行数据
	}, nil
}

// CreateTable 创建表
func (s *DuckDBServer) CreateTable(ctx context.Context, req *pb.CreateTableRequest) (*pb.CreateTableResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// 表名隔离
	tableName := fmt.Sprintf("user_%s_%s", req.UserId, req.TableName)

	err := s.duckdbClient.CreateTable(ctx, tableName, req.Schema)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &pb.CreateTableResponse{
		Success:   true,
		TableName: tableName,
	}, nil
}

// HealthCheck 健康检查
func (s *DuckDBServer) HealthCheck(ctx context.Context, req *pb.HealthCheckRequest) (*pb.HealthCheckResponse, error) {
	err := s.duckdbClient.Ping(ctx)
	return &pb.HealthCheckResponse{
		Healthy: err == nil,
		Service: "duckdb",
	}, nil
}


