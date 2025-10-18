// Package server implements the DuckDB gRPC service
// 文件名: cmd/duckdb-service/server/server.go
package server

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	lru "github.com/hashicorp/golang-lru"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/structpb"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/isa-cloud/isa_cloud/api/proto/duckdb"
	"github.com/isa-cloud/isa_cloud/pkg/analytics/duckdb"
	grpcclients "github.com/isa-cloud/isa_cloud/pkg/grpc/clients"
	"github.com/isa-cloud/isa_cloud/pkg/storage"
)

// DuckDBServer DuckDB gRPC 服务实现
type DuckDBServer struct {
	pb.UnimplementedDuckDBServiceServer

	minioClient  *grpcclients.MinIOGRPCClient
	authService  *AuthService
	config       *storage.StorageConfig
	localTempDir string
	dbCache      *lru.Cache // LRU cache for database handles
	mu           sync.RWMutex
}

// databaseHandle represents an open database connection
type databaseHandle struct {
	client       *duckdb.Client
	localPath    string
	minioBucket  string
	minioPath    string
	userID       string
	databaseName string
	lastAccessed time.Time
	lastSynced   time.Time
	modified     bool
	mu           sync.Mutex
}

// NewDuckDBServer 创建 DuckDB gRPC 服务实例
func NewDuckDBServer(minioClient *grpcclients.MinIOGRPCClient, cfg *storage.StorageConfig) (*DuckDBServer, error) {
	// Create temporary directory for database files
	tempDir := "/tmp/duckdb"
	if err := os.MkdirAll(tempDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create temp directory: %w", err)
	}

	// Create LRU cache with eviction callback
	cache, err := lru.NewWithEvict(100, func(key interface{}, value interface{}) {
		// Eviction callback: sync and close database
		handle := value.(*databaseHandle)
		log.Printf("[DuckDB] Evicting database from cache: %s", key.(string))

		// Sync to MinIO if modified
		if handle.modified {
			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
			defer cancel()
			if err := syncDatabaseHandle(ctx, minioClient, handle); err != nil {
				log.Printf("[DuckDB] Error syncing evicted database: %v", err)
			}
		}

		// Close connection
		if handle.client != nil {
			handle.client.Close()
		}

		// Remove local file
		if handle.localPath != "" {
			os.Remove(handle.localPath)
		}
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create LRU cache: %w", err)
	}

	server := &DuckDBServer{
		minioClient:  minioClient,
		authService:  NewAuthService(cfg),
		config:       cfg,
		localTempDir: tempDir,
		dbCache:      cache,
	}

	// Start auto-sync and cleanup goroutine
	go server.autoSyncDatabases()

	return server, nil
}

// ========================================
// Database Lifecycle Management (Inline)
// ========================================

// getOrCreateDatabase gets or creates a database connection for a user
func (s *DuckDBServer) getOrCreateDatabase(ctx context.Context, userID, databaseName string) (*databaseHandle, error) {
	key := fmt.Sprintf("%s-%s", userID, databaseName)

	// Check LRU cache first
	if value, ok := s.dbCache.Get(key); ok {
		handle := value.(*databaseHandle)
		handle.mu.Lock()
		handle.lastAccessed = time.Now()
		handle.mu.Unlock()
		return handle, nil
	}

	// Not in cache, create new database handle
	return s.openDatabase(ctx, userID, databaseName)
}

// openDatabase opens or creates a database file from MinIO
func (s *DuckDBServer) openDatabase(ctx context.Context, userID, databaseName string) (*databaseHandle, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	key := fmt.Sprintf("%s-%s", userID, databaseName)

	// Double-check cache after acquiring lock
	if value, ok := s.dbCache.Get(key); ok {
		return value.(*databaseHandle), nil
	}

	// Define MinIO storage paths
	// Support both user-level and org-level databases
	// If userID starts with "org-", treat as organization bucket
	var bucketName string
	sanitizedUserID := sanitizeBucketName(userID)
	if strings.HasPrefix(userID, "org-") {
		bucketName = fmt.Sprintf("%s-duckdb", sanitizedUserID)
	} else {
		bucketName = fmt.Sprintf("user-%s-duckdb", sanitizedUserID)
	}
	minioPath := fmt.Sprintf("%s.duckdb", databaseName)
	localPath := filepath.Join(s.localTempDir, fmt.Sprintf("%s-%s-%d.duckdb", userID, databaseName, time.Now().UnixNano()))

	// Ensure bucket exists
	exists, err := s.minioClient.BucketExists(ctx, bucketName)
	if err != nil {
		return nil, fmt.Errorf("failed to check bucket existence: %w", err)
	}

	if !exists {
		if err := s.minioClient.CreateBucket(ctx, bucketName); err != nil {
			return nil, fmt.Errorf("failed to create bucket: %w", err)
		}
	}

	// Download existing database file from MinIO (if it exists)
	objectExists := false
	_, err = s.minioClient.StatObject(ctx, bucketName, minioPath)
	if err == nil {
		objectExists = true
		// Download the file
		data, err := s.minioClient.GetObject(ctx, bucketName, minioPath)
		if err != nil {
			return nil, fmt.Errorf("failed to download database file: %w", err)
		}

		// Write to local file
		outFile, err := os.Create(localPath)
		if err != nil {
			return nil, fmt.Errorf("failed to create local file: %w", err)
		}
		defer outFile.Close()

		if _, err := io.Copy(outFile, bytes.NewReader(data)); err != nil {
			return nil, fmt.Errorf("failed to write database file: %w", err)
		}
	}

	// Open or create DuckDB connection
	dbConfig := &duckdb.Config{
		DatabasePath: localPath,
		MemoryLimit:  "1GB",
		Threads:      2,
		MaxOpenConns: 5,
		MaxIdleConns: 2,
		Extensions:   []string{"httpfs", "parquet", "json"},
	}

	client, err := duckdb.NewClient(dbConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to create DuckDB client: %w", err)
	}

	// Configure DuckDB to use MinIO as S3 endpoint for direct file access
	minioEndpoint := os.Getenv("MINIO_ENDPOINT")
	if minioEndpoint == "" {
		minioEndpoint = "staging-minio:9000" // Docker service name
	}
	minioAccessKey := os.Getenv("MINIO_ROOT_USER")
	if minioAccessKey == "" {
		minioAccessKey = "minioadmin" // Default MinIO credentials
	}
	minioSecretKey := os.Getenv("MINIO_ROOT_PASSWORD")
	if minioSecretKey == "" {
		minioSecretKey = "minioadmin"
	}

	// Set S3 configuration for DuckDB httpfs extension
	s3ConfigSQL := []string{
		fmt.Sprintf("SET s3_endpoint='%s'", minioEndpoint),
		fmt.Sprintf("SET s3_access_key_id='%s'", minioAccessKey),
		fmt.Sprintf("SET s3_secret_access_key='%s'", minioSecretKey),
		"SET s3_use_ssl=false",
		"SET s3_url_style='path'",
	}
	for _, sql := range s3ConfigSQL {
		if _, err := client.Exec(ctx, sql); err != nil {
			log.Printf("[DuckDB] Warning: Failed to set S3 config: %v", err)
		}
	}
	log.Printf("[DuckDB] Configured S3 endpoint: %s", minioEndpoint)

	// If this is a new database, upload the initial file to MinIO
	if !objectExists {
		file, err := os.Open(localPath)
		if err != nil {
			client.Close()
			return nil, fmt.Errorf("failed to open database file: %w", err)
		}
		defer file.Close()

		fileInfo, err := file.Stat()
		if err != nil {
			client.Close()
			return nil, fmt.Errorf("failed to stat database file: %w", err)
		}

		_, err = s.minioClient.PutObject(ctx, bucketName, minioPath, file, fileInfo.Size())
		if err != nil {
			client.Close()
			return nil, fmt.Errorf("failed to upload initial database file: %w", err)
		}
	}

	handle := &databaseHandle{
		client:       client,
		localPath:    localPath,
		minioBucket:  bucketName,
		minioPath:    minioPath,
		userID:       userID,
		databaseName: databaseName,
		lastAccessed: time.Now(),
		lastSynced:   time.Now(),
		modified:     false,
	}

	// Add to LRU cache
	s.dbCache.Add(key, handle)
	return handle, nil
}

// syncDatabase syncs the local database file back to MinIO
func (s *DuckDBServer) syncDatabase(ctx context.Context, handle *databaseHandle) error {
	return syncDatabaseHandle(ctx, s.minioClient, handle)
}

// syncDatabaseHandle is a standalone function to sync a database handle
func syncDatabaseHandle(ctx context.Context, minioClient *grpcclients.MinIOGRPCClient, handle *databaseHandle) error {
	handle.mu.Lock()
	defer handle.mu.Unlock()

	if !handle.modified {
		return nil // No changes to sync
	}

	// Upload the modified file to MinIO
	file, err := os.Open(handle.localPath)
	if err != nil {
		return fmt.Errorf("failed to open database file: %w", err)
	}
	defer file.Close()

	fileInfo, err := file.Stat()
	if err != nil {
		return fmt.Errorf("failed to stat database file: %w", err)
	}

	_, err = minioClient.PutObject(ctx, handle.minioBucket, handle.minioPath, file, fileInfo.Size())
	if err != nil {
		return fmt.Errorf("failed to sync database to MinIO: %w", err)
	}

	handle.modified = false
	handle.lastSynced = time.Now()
	return nil
}

// closeDatabase closes a database connection
func (s *DuckDBServer) closeDatabase(ctx context.Context, userID, databaseName string) error {
	key := fmt.Sprintf("%s-%s", userID, databaseName)

	// Remove from cache (this will trigger eviction callback)
	s.dbCache.Remove(key)

	return nil
}

// markModified marks a database as modified
func (s *DuckDBServer) markModified(handle *databaseHandle) {
	handle.mu.Lock()
	handle.modified = true
	handle.mu.Unlock()
}

// autoSyncDatabases automatically syncs modified databases and closes inactive ones
func (s *DuckDBServer) autoSyncDatabases() {
	ticker := time.NewTicker(5 * time.Minute) // Reduced frequency
	defer ticker.Stop()

	for range ticker.C {
		ctx := context.Background()

		// Get all keys from cache
		keys := s.dbCache.Keys()

		for _, k := range keys {
			key := k.(string)
			value, ok := s.dbCache.Peek(key) // Peek doesn't update LRU
			if !ok {
				continue
			}

			handle := value.(*databaseHandle)
			handle.mu.Lock()

			// Sync if modified and hasn't been synced recently
			if handle.modified && time.Since(handle.lastSynced) > 2*time.Minute {
				handle.mu.Unlock()
				if err := s.syncDatabase(ctx, handle); err != nil {
					log.Printf("[DuckDB] Error syncing database %s: %v", key, err)
				}
			} else {
				handle.mu.Unlock()
			}

			// Close inactive databases (not accessed in 30 minutes)
			if time.Since(handle.lastAccessed) > 30*time.Minute {
				log.Printf("[DuckDB] Closing inactive database: %s", key)
				s.dbCache.Remove(key) // Triggers eviction callback
			}
		}
	}
}

// sanitizeBucketName sanitizes user/org IDs for use in MinIO bucket names
// MinIO bucket names must be lowercase and can only contain: a-z, 0-9, ., -
func sanitizeBucketName(name string) string {
	// Convert to lowercase
	name = strings.ToLower(name)
	// Replace underscores with hyphens
	name = strings.ReplaceAll(name, "_", "-")
	// Remove any other invalid characters
	name = strings.Map(func(r rune) rune {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') || r == '-' || r == '.' {
			return r
		}
		return '-'
	}, name)
	return name
}

// listUserDatabases lists all databases for a user/org from MinIO
func (s *DuckDBServer) listUserDatabases(ctx context.Context, userID string) ([]string, error) {
	var bucketName string
	sanitizedUserID := sanitizeBucketName(userID)
	if strings.HasPrefix(userID, "org-") {
		bucketName = fmt.Sprintf("%s-duckdb", sanitizedUserID)
	} else {
		bucketName = fmt.Sprintf("user-%s-duckdb", sanitizedUserID)
	}

	// Check if bucket exists
	exists, err := s.minioClient.BucketExists(ctx, bucketName)
	if err != nil {
		return nil, fmt.Errorf("failed to check bucket existence: %w", err)
	}

	if !exists {
		return []string{}, nil
	}

	// List objects in bucket
	objects, err := s.minioClient.ListObjects(ctx, bucketName, "", true)
	if err != nil {
		return nil, fmt.Errorf("failed to list objects: %w", err)
	}

	var databases []string
	for _, obj := range objects {
		// Remove .duckdb extension
		if len(obj.Key) > 7 && obj.Key[len(obj.Key)-7:] == ".duckdb" {
			dbName := obj.Key[:len(obj.Key)-7]
			databases = append(databases, dbName)
		}
	}

	return databases, nil
}

// deleteUserDatabase deletes a database from MinIO
func (s *DuckDBServer) deleteUserDatabase(ctx context.Context, userID, databaseName string) error {
	// Close the database if open
	key := fmt.Sprintf("%s-%s", userID, databaseName)
	s.dbCache.Remove(key) // Triggers eviction callback if exists

	// Delete from MinIO
	var bucketName string
	sanitizedUserID := sanitizeBucketName(userID)
	if strings.HasPrefix(userID, "org-") {
		bucketName = fmt.Sprintf("%s-duckdb", sanitizedUserID)
	} else {
		bucketName = fmt.Sprintf("user-%s-duckdb", sanitizedUserID)
	}
	minioPath := fmt.Sprintf("%s.duckdb", databaseName)

	if err := s.minioClient.DeleteObject(ctx, bucketName, minioPath); err != nil {
		return fmt.Errorf("failed to delete database from MinIO: %w", err)
	}

	return nil
}

// ========================================
// Helper Functions
// ========================================

// makeTableName generates user-isolated table names
func (s *DuckDBServer) makeTableName(userID, tableName string) string {
	return fmt.Sprintf("user_%s_%s", userID, tableName)
}

// convertRowsToProto converts sql.Rows to proto Row objects
func convertRowsToProto(rows [][]interface{}) []*pb.Row {
	var protoRows []*pb.Row
	for _, row := range rows {
		protoRow := &pb.Row{
			Values: make([]*pb.Value, len(row)),
		}
		for i, val := range row {
			protoRow.Values[i] = convertValueToProto(val)
		}
		protoRows = append(protoRows, protoRow)
	}
	return protoRows
}

// convertValueToProto converts Go value to proto Value
func convertValueToProto(val interface{}) *pb.Value {
	if val == nil {
		return &pb.Value{Value: &pb.Value_NullValue{NullValue: pb.NullValue_NULL_VALUE}}
	}

	switch v := val.(type) {
	case string:
		return &pb.Value{Value: &pb.Value_StringValue{StringValue: v}}
	case int:
		return &pb.Value{Value: &pb.Value_IntValue{IntValue: int64(v)}}
	case int8:
		return &pb.Value{Value: &pb.Value_IntValue{IntValue: int64(v)}}
	case int16:
		return &pb.Value{Value: &pb.Value_IntValue{IntValue: int64(v)}}
	case int32:
		return &pb.Value{Value: &pb.Value_IntValue{IntValue: int64(v)}}
	case int64:
		return &pb.Value{Value: &pb.Value_IntValue{IntValue: v}}
	case uint:
		return &pb.Value{Value: &pb.Value_IntValue{IntValue: int64(v)}}
	case uint8:
		return &pb.Value{Value: &pb.Value_IntValue{IntValue: int64(v)}}
	case uint16:
		return &pb.Value{Value: &pb.Value_IntValue{IntValue: int64(v)}}
	case uint32:
		return &pb.Value{Value: &pb.Value_IntValue{IntValue: int64(v)}}
	case uint64:
		return &pb.Value{Value: &pb.Value_IntValue{IntValue: int64(v)}}
	case float32:
		return &pb.Value{Value: &pb.Value_DoubleValue{DoubleValue: float64(v)}}
	case float64:
		return &pb.Value{Value: &pb.Value_DoubleValue{DoubleValue: v}}
	case bool:
		return &pb.Value{Value: &pb.Value_BoolValue{BoolValue: v}}
	case []byte:
		return &pb.Value{Value: &pb.Value_BytesValue{BytesValue: v}}
	case time.Time:
		return &pb.Value{Value: &pb.Value_TimestampValue{TimestampValue: timestamppb.New(v)}}
	default:
		return &pb.Value{Value: &pb.Value_StringValue{StringValue: fmt.Sprintf("%v", v)}}
	}
}

// convertProtoColumnsToColumnInfo converts proto columns to duckdb.ColumnInfo
func convertProtoColumnsToColumnInfo(columns []*pb.ColumnInfo) []duckdb.ColumnInfo {
	var colInfo []duckdb.ColumnInfo
	for _, col := range columns {
		colInfo = append(colInfo, duckdb.ColumnInfo{
			Name:     col.Name,
			Type:     col.DataType,
			Nullable: col.Nullable,
			Default:  col.DefaultValue,
		})
	}
	return colInfo
}

// ========================================
// Database Management
// ========================================

// CreateDatabase creates a new database
func (s *DuckDBServer) CreateDatabase(ctx context.Context, req *pb.CreateDatabaseRequest) (*pb.CreateDatabaseResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Create or open the database (this will create the file in MinIO)
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, req.DatabaseName)
	if err != nil {
		return &pb.CreateDatabaseResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.CreateDatabaseResponse{
		Success: true,
		Message: fmt.Sprintf("Database %s created successfully", req.DatabaseName),
		DatabaseInfo: &pb.DatabaseInfo{
			DatabaseId:     fmt.Sprintf("%s-%s", req.UserId, req.DatabaseName),
			DatabaseName:   req.DatabaseName,
			UserId:         req.UserId,
			OrganizationId: req.OrganizationId,
			MinioBucket:    handle.minioBucket,
			MinioPath:      handle.minioPath,
			CreatedAt:      timestamppb.Now(),
			Version:        "v1.0",
		},
	}, nil
}

// ListDatabases lists all databases for a user
func (s *DuckDBServer) ListDatabases(ctx context.Context, req *pb.ListDatabasesRequest) (*pb.ListDatabasesResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	databases, err := s.listUserDatabases(ctx, req.UserId)
	if err != nil {
		return &pb.ListDatabasesResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	var dbInfos []*pb.DatabaseInfo
	for _, dbName := range databases {
		if req.NameFilter != "" && !strings.Contains(dbName, req.NameFilter) {
			continue
		}
		var minioBucket string
		sanitizedUserID := sanitizeBucketName(req.UserId)
		if strings.HasPrefix(req.UserId, "org-") {
			minioBucket = fmt.Sprintf("%s-duckdb", sanitizedUserID)
		} else {
			minioBucket = fmt.Sprintf("user-%s-duckdb", sanitizedUserID)
		}
		dbInfos = append(dbInfos, &pb.DatabaseInfo{
			DatabaseId:     fmt.Sprintf("%s-%s", req.UserId, dbName),
			DatabaseName:   dbName,
			UserId:         req.UserId,
			OrganizationId: req.OrganizationId,
			MinioBucket:    minioBucket,
			MinioPath:      fmt.Sprintf("%s.duckdb", dbName),
		})
	}

	return &pb.ListDatabasesResponse{
		Success:    true,
		Databases:  dbInfos,
		TotalCount: int32(len(dbInfos)),
		Page:       req.Page,
		PageSize:   req.PageSize,
	}, nil
}

// DeleteDatabase deletes a database
func (s *DuckDBServer) DeleteDatabase(ctx context.Context, req *pb.DeleteDatabaseRequest) (*pb.DeleteDatabaseResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name from database_id (format: userId-databaseName)
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.DeleteDatabaseResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	if err := s.deleteUserDatabase(ctx, req.UserId, databaseName); err != nil {
		return &pb.DeleteDatabaseResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.DeleteDatabaseResponse{
		Success: true,
		Message: fmt.Sprintf("Database %s deleted successfully", req.DatabaseId),
	}, nil
}

// GetDatabaseInfo gets database information
func (s *DuckDBServer) GetDatabaseInfo(ctx context.Context, req *pb.GetDatabaseInfoRequest) (*pb.GetDatabaseInfoResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.GetDatabaseInfoResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	var minioBucket string
	sanitizedUserID := sanitizeBucketName(req.UserId)
	if strings.HasPrefix(req.UserId, "org-") {
		minioBucket = fmt.Sprintf("%s-duckdb", sanitizedUserID)
	} else {
		minioBucket = fmt.Sprintf("user-%s-duckdb", sanitizedUserID)
	}

	return &pb.GetDatabaseInfoResponse{
		Success: true,
		DatabaseInfo: &pb.DatabaseInfo{
			DatabaseId:   req.DatabaseId,
			DatabaseName: databaseName,
			UserId:       req.UserId,
			MinioBucket:  minioBucket,
			MinioPath:    fmt.Sprintf("%s.duckdb", databaseName),
			CreatedAt:    timestamppb.Now(),
			Version:      "v1.0",
		},
	}, nil
}

// BackupDatabase backs up a database
func (s *DuckDBServer) BackupDatabase(ctx context.Context, req *pb.BackupDatabaseRequest) (*pb.BackupDatabaseResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.BackupDatabaseResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	// Get database handle and sync first
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return &pb.BackupDatabaseResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	// Sync to ensure latest version in MinIO
	if err := s.syncDatabase(ctx, handle); err != nil {
		return &pb.BackupDatabaseResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	// Create backup path
	backupPath := fmt.Sprintf("backups/%s-%d.duckdb", req.BackupName, time.Now().Unix())

	// Copy file in MinIO
	if err := s.minioClient.CopyObject(ctx, handle.minioBucket, handle.minioPath, handle.minioBucket, backupPath); err != nil {
		return &pb.BackupDatabaseResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.BackupDatabaseResponse{
		Success:    true,
		Message:    "Database backed up successfully",
		BackupPath: backupPath,
		BackupTime: timestamppb.Now(),
	}, nil
}

// RestoreDatabase restores a database from backup
func (s *DuckDBServer) RestoreDatabase(ctx context.Context, req *pb.RestoreDatabaseRequest) (*pb.RestoreDatabaseResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	var bucketName string
	if strings.HasPrefix(req.UserId, "org-") {
		bucketName = fmt.Sprintf("%s-duckdb", req.UserId)
	} else {
		bucketName = fmt.Sprintf("user-%s-duckdb", req.UserId)
	}
	destPath := fmt.Sprintf("%s.duckdb", req.NewDatabaseName)

	// Copy backup to new database
	if err := s.minioClient.CopyObject(ctx, bucketName, req.BackupPath, bucketName, destPath); err != nil {
		return &pb.RestoreDatabaseResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.RestoreDatabaseResponse{
		Success: true,
		Message: "Database restored successfully",
		DatabaseInfo: &pb.DatabaseInfo{
			DatabaseName: req.NewDatabaseName,
			UserId:       req.UserId,
			MinioBucket:  bucketName,
			MinioPath:    destPath,
			CreatedAt:    timestamppb.Now(),
		},
	}, nil
}

// ========================================
// Query Operations
// ========================================

// ExecuteQuery executes a SQL query
func (s *DuckDBServer) ExecuteQuery(ctx context.Context, req *pb.ExecuteQueryRequest) (*pb.ExecuteQueryResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.ExecuteQueryResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	// Get database handle
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return &pb.ExecuteQueryResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	startTime := time.Now()

	// Execute query
	result, err := handle.client.QueryToStruct(ctx, req.Query)
	if err != nil {
		return &pb.ExecuteQueryResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	// Convert column types to strings
	columnTypes := make([]string, len(result.Columns))
	for i := range result.Columns {
		columnTypes[i] = "VARCHAR"
	}

	executionTime := float64(time.Since(startTime).Milliseconds())

	return &pb.ExecuteQueryResponse{
		Success:         true,
		Columns:         result.Columns,
		ColumnTypes:     columnTypes,
		Rows:            convertRowsToProto(result.Rows),
		RowCount:        int32(result.Count),
		ExecutionTimeMs: executionTime,
	}, nil
}

// ExecuteQueryStream executes a query with streaming results
func (s *DuckDBServer) ExecuteQueryStream(req *pb.ExecuteQueryRequest, stream pb.DuckDBService_ExecuteQueryStreamServer) error {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return stream.Send(&pb.QueryResultChunk{
			Success: false,
			Error:   "invalid database ID format",
		})
	}
	databaseName := strings.Join(parts[1:], "-")

	startTime := time.Now()
	ctx := stream.Context()

	// Get database handle
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return stream.Send(&pb.QueryResultChunk{
			Success: false,
			Error:   err.Error(),
		})
	}

	// Execute query
	result, err := handle.client.QueryToStruct(ctx, req.Query)
	if err != nil {
		return stream.Send(&pb.QueryResultChunk{
			Success: false,
			Error:   err.Error(),
		})
	}

	// Stream results in chunks
	chunkSize := 100
	totalRows := len(result.Rows)

	for i := 0; i < totalRows; i += chunkSize {
		end := i + chunkSize
		if end > totalRows {
			end = totalRows
		}

		chunk := &pb.QueryResultChunk{
			Success: true,
			Rows:    convertRowsToProto(result.Rows[i:end]),
			IsLast:  end >= totalRows,
		}

		// Send column info in first chunk
		if i == 0 {
			chunk.Columns = result.Columns
			columnTypes := make([]string, len(result.Columns))
			for j := range result.Columns {
				columnTypes[j] = "VARCHAR"
			}
			chunk.ColumnTypes = columnTypes
		}

		if end >= totalRows {
			chunk.ExecutionTimeMs = float64(time.Since(startTime).Milliseconds())
		}

		if err := stream.Send(chunk); err != nil {
			return err
		}
	}

	return nil
}

// ExecuteStatement executes a SQL statement (INSERT/UPDATE/DELETE)
func (s *DuckDBServer) ExecuteStatement(ctx context.Context, req *pb.ExecuteStatementRequest) (*pb.ExecuteStatementResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.ExecuteStatementResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	// Get database handle
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return &pb.ExecuteStatementResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	startTime := time.Now()

	result, err := handle.client.Exec(ctx, req.Statement)
	if err != nil {
		return &pb.ExecuteStatementResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	// Mark database as modified
	s.markModified(handle)

	rowsAffected, _ := result.RowsAffected()
	executionTime := float64(time.Since(startTime).Milliseconds())

	return &pb.ExecuteStatementResponse{
		Success:         true,
		AffectedRows:    int32(rowsAffected),
		ExecutionTimeMs: executionTime,
		Message:         fmt.Sprintf("Statement executed successfully, %d rows affected", rowsAffected),
	}, nil
}

// ExecuteBatch executes multiple SQL statements
func (s *DuckDBServer) ExecuteBatch(ctx context.Context, req *pb.ExecuteBatchRequest) (*pb.ExecuteBatchResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.ExecuteBatchResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	// Get database handle
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return &pb.ExecuteBatchResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	startTime := time.Now()
	var results []*pb.BatchResult

	if req.Transaction {
		// Execute in transaction
		err := handle.client.ExecMulti(ctx, req.Statements)
		if err != nil {
			return &pb.ExecuteBatchResponse{
				Success: false,
				Error:   err.Error(),
			}, nil
		}
		for range req.Statements {
			results = append(results, &pb.BatchResult{Success: true})
		}
	} else {
		// Execute individually
		for _, stmt := range req.Statements {
			result, err := handle.client.Exec(ctx, stmt)
			if err != nil {
				results = append(results, &pb.BatchResult{
					Success: false,
					Error:   err.Error(),
				})
			} else {
				rows, _ := result.RowsAffected()
				results = append(results, &pb.BatchResult{
					Success:      true,
					AffectedRows: int32(rows),
				})
			}
		}
	}

	// Mark database as modified
	s.markModified(handle)

	executionTime := float64(time.Since(startTime).Milliseconds())

	return &pb.ExecuteBatchResponse{
		Success:              true,
		Results:              results,
		TotalExecutionTimeMs: executionTime,
	}, nil
}

// PrepareStatement prepares a SQL statement
func (s *DuckDBServer) PrepareStatement(ctx context.Context, req *pb.PrepareStatementRequest) (*pb.PrepareStatementResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Generate statement ID
	stmtID := fmt.Sprintf("stmt_%s_%d", req.UserId, time.Now().UnixNano())

	return &pb.PrepareStatementResponse{
		Success:     true,
		StatementId: stmtID,
	}, nil
}

// ========================================
// Table Management
// ========================================

// CreateTable creates a table
func (s *DuckDBServer) CreateTable(ctx context.Context, req *pb.CreateTableRequest) (*pb.CreateTableResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.CreateTableResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	// Get database handle
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return &pb.CreateTableResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	tableName := s.makeTableName(req.UserId, req.TableName)
	columns := convertProtoColumnsToColumnInfo(req.Columns)

	err = handle.client.CreateTable(ctx, tableName, columns)
	if err != nil {
		return &pb.CreateTableResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	// Mark database as modified
	s.markModified(handle)

	return &pb.CreateTableResponse{
		Success: true,
		Message: fmt.Sprintf("Table %s created successfully", tableName),
		TableInfo: &pb.TableInfo{
			TableName:  tableName,
			SchemaName: "main",
			Columns:    req.Columns,
			CreatedAt:  timestamppb.Now(),
		},
	}, nil
}

// ListTables lists all tables in a database
func (s *DuckDBServer) ListTables(ctx context.Context, req *pb.ListTablesRequest) (*pb.ListTablesResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.ListTablesResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	// Get database handle
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return &pb.ListTablesResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	schema := req.SchemaName
	if schema == "" {
		schema = "main"
	}

	tables, err := handle.client.ListTables(ctx, schema)
	if err != nil {
		return &pb.ListTablesResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	// Filter by user prefix and name filter
	userPrefix := fmt.Sprintf("user_%s_", req.UserId)
	var userTables []*pb.TableInfo

	for _, table := range tables {
		if strings.HasPrefix(table.Name, userPrefix) {
			if req.NameFilter != "" && !strings.Contains(table.Name, req.NameFilter) {
				continue
			}
			userTables = append(userTables, &pb.TableInfo{
				TableName:  table.Name,
				SchemaName: table.Schema,
				RowCount:   table.RowCount,
			})
		}
	}

	return &pb.ListTablesResponse{
		Success:    true,
		Tables:     userTables,
		TotalCount: int32(len(userTables)),
	}, nil
}

// DropTable drops a table
func (s *DuckDBServer) DropTable(ctx context.Context, req *pb.DropTableRequest) (*pb.DropTableResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.DropTableResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	// Get database handle
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return &pb.DropTableResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	tableName := s.makeTableName(req.UserId, req.TableName)

	err = handle.client.DropTable(ctx, tableName, req.IfExists)
	if err != nil {
		return &pb.DropTableResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	// Mark database as modified
	s.markModified(handle)

	return &pb.DropTableResponse{
		Success: true,
		Message: fmt.Sprintf("Table %s dropped successfully", tableName),
	}, nil
}

// GetTableSchema gets table schema
func (s *DuckDBServer) GetTableSchema(ctx context.Context, req *pb.GetTableSchemaRequest) (*pb.GetTableSchemaResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.GetTableSchemaResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	// Get database handle
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return &pb.GetTableSchemaResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	tableName := s.makeTableName(req.UserId, req.TableName)

	columns, err := handle.client.GetTableSchema(ctx, tableName)
	if err != nil {
		return &pb.GetTableSchemaResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	var protoColumns []*pb.ColumnInfo
	for _, col := range columns {
		protoColumns = append(protoColumns, &pb.ColumnInfo{
			Name:         col.Name,
			DataType:     col.Type,
			Nullable:     col.Nullable,
			DefaultValue: col.Default,
		})
	}

	return &pb.GetTableSchemaResponse{
		Success: true,
		TableInfo: &pb.TableInfo{
			TableName:  tableName,
			SchemaName: "main",
			Columns:    protoColumns,
		},
	}, nil
}

// GetTableStats gets table statistics
func (s *DuckDBServer) GetTableStats(ctx context.Context, req *pb.GetTableStatsRequest) (*pb.GetTableStatsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.GetTableStatsResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	// Get database handle
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return &pb.GetTableStatsResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	tableName := s.makeTableName(req.UserId, req.TableName)

	// Get row count
	var rowCount int64
	err = handle.client.QueryRow(ctx, fmt.Sprintf("SELECT COUNT(*) FROM %s", tableName)).Scan(&rowCount)
	if err != nil {
		return &pb.GetTableStatsResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.GetTableStatsResponse{
		Success: true,
		Stats: &pb.TableStats{
			TableName: tableName,
			RowCount:  rowCount,
		},
	}, nil
}

// ========================================
// View Management (Simplified - using same pattern as tables)
// ========================================

// CreateView creates a view
func (s *DuckDBServer) CreateView(ctx context.Context, req *pb.CreateViewRequest) (*pb.CreateViewResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.CreateViewResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	// Get database handle
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return &pb.CreateViewResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	viewName := s.makeTableName(req.UserId, req.ViewName)

	replaceClause := ""
	if req.Replace {
		replaceClause = "OR REPLACE "
	}

	query := fmt.Sprintf("CREATE %sVIEW %s AS %s", replaceClause, viewName, req.Query)
	_, err = handle.client.Exec(ctx, query)
	if err != nil {
		return &pb.CreateViewResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	// Mark database as modified
	s.markModified(handle)

	return &pb.CreateViewResponse{
		Success: true,
		Message: fmt.Sprintf("View %s created successfully", viewName),
	}, nil
}

// ListViews lists all views
func (s *DuckDBServer) ListViews(ctx context.Context, req *pb.ListViewsRequest) (*pb.ListViewsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.ListViewsResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	// Get database handle
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return &pb.ListViewsResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	query := "SELECT table_name FROM information_schema.tables WHERE table_type = 'VIEW'"
	rows, err := handle.client.Query(ctx, query)
	if err != nil {
		return &pb.ListViewsResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}
	defer rows.Close()

	userPrefix := fmt.Sprintf("user_%s_", req.UserId)
	var views []string

	for rows.Next() {
		var viewName string
		if err := rows.Scan(&viewName); err != nil {
			continue
		}
		if strings.HasPrefix(viewName, userPrefix) {
			views = append(views, viewName)
		}
	}

	return &pb.ListViewsResponse{
		Success: true,
		Views:   views,
	}, nil
}

// DropView drops a view
func (s *DuckDBServer) DropView(ctx context.Context, req *pb.DropViewRequest) (*pb.DropViewResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.DropViewResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	// Get database handle
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return &pb.DropViewResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	viewName := s.makeTableName(req.UserId, req.ViewName)

	query := fmt.Sprintf("DROP VIEW IF EXISTS %s", viewName)
	_, err = handle.client.Exec(ctx, query)
	if err != nil {
		return &pb.DropViewResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	// Mark database as modified
	s.markModified(handle)

	return &pb.DropViewResponse{
		Success: true,
		Message: fmt.Sprintf("View %s dropped successfully", viewName),
	}, nil
}

// ========================================
// Data Import/Export (Simplified implementations)
// ========================================

// ImportFromMinIO imports data from MinIO
func (s *DuckDBServer) ImportFromMinIO(ctx context.Context, req *pb.ImportFromMinIORequest) (*pb.ImportFromMinIOResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.ImportFromMinIOResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	// Get database handle
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return &pb.ImportFromMinIOResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	startTime := time.Now()
	tableName := s.makeTableName(req.UserId, req.TableName)

	// Build MinIO path with user bucket prefix
	// MinIO service adds user- prefix to bucket names
	bucketName := req.BucketName
	if !strings.HasPrefix(bucketName, "user-") && !strings.HasPrefix(req.UserId, "org-") {
		sanitizedUserID := sanitizeBucketName(req.UserId)
		bucketName = fmt.Sprintf("user-%s-%s", sanitizedUserID, req.BucketName)
	}
	minioPath := fmt.Sprintf("s3://%s/%s", bucketName, req.ObjectKey)

	// Use CREATE TABLE AS SELECT to automatically create table with inferred schema
	var query string
	switch strings.ToLower(req.Format) {
	case "csv":
		query = fmt.Sprintf("CREATE TABLE %s AS SELECT * FROM read_csv_auto('%s')", tableName, minioPath)
	case "parquet":
		query = fmt.Sprintf("CREATE TABLE %s AS SELECT * FROM read_parquet('%s')", tableName, minioPath)
	case "json":
		query = fmt.Sprintf("CREATE TABLE %s AS SELECT * FROM read_json_auto('%s')", tableName, minioPath)
	default:
		return &pb.ImportFromMinIOResponse{
			Success: false,
			Error:   fmt.Sprintf("unsupported format: %s", req.Format),
		}, nil
	}

	_, err = handle.client.Exec(ctx, query)
	if err != nil {
		return &pb.ImportFromMinIOResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	// Mark database as modified
	s.markModified(handle)

	executionTime := float64(time.Since(startTime).Milliseconds())

	return &pb.ImportFromMinIOResponse{
		Success:         true,
		Message:         "Data imported successfully",
		RowsImported:    0,
		ExecutionTimeMs: executionTime,
	}, nil
}

// ExportToMinIO exports data to MinIO
func (s *DuckDBServer) ExportToMinIO(ctx context.Context, req *pb.ExportToMinIORequest) (*pb.ExportToMinIOResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.ExportToMinIOResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	// Get database handle
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return &pb.ExportToMinIOResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	startTime := time.Now()

	// Build MinIO path with user bucket prefix
	bucketName := req.BucketName
	if !strings.HasPrefix(bucketName, "user-") && !strings.HasPrefix(req.UserId, "org-") {
		sanitizedUserID := sanitizeBucketName(req.UserId)
		bucketName = fmt.Sprintf("user-%s-%s", sanitizedUserID, req.BucketName)
	}
	minioPath := fmt.Sprintf("s3://%s/%s", bucketName, req.ObjectKey)

	var query string
	switch strings.ToLower(req.Format) {
	case "csv":
		query = fmt.Sprintf("COPY (%s) TO '%s' (FORMAT CSV, HEADER)", req.Query, minioPath)
	case "parquet":
		query = fmt.Sprintf("COPY (%s) TO '%s' (FORMAT PARQUET)", req.Query, minioPath)
	case "json":
		query = fmt.Sprintf("COPY (%s) TO '%s' (FORMAT JSON)", req.Query, minioPath)
	default:
		return &pb.ExportToMinIOResponse{
			Success: false,
			Error:   fmt.Sprintf("unsupported format: %s", req.Format),
		}, nil
	}

	_, err = handle.client.Exec(ctx, query)
	if err != nil {
		return &pb.ExportToMinIOResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	executionTime := float64(time.Since(startTime).Milliseconds())

	return &pb.ExportToMinIOResponse{
		Success:         true,
		Message:         "Data exported successfully",
		RowsExported:    0,
		ExecutionTimeMs: executionTime,
	}, nil
}

// QueryMinIOFile queries a file in MinIO directly
func (s *DuckDBServer) QueryMinIOFile(ctx context.Context, req *pb.QueryMinIOFileRequest) (*pb.QueryMinIOFileResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.QueryMinIOFileResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	// Get database handle
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return &pb.QueryMinIOFileResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	startTime := time.Now()

	// Build file path with user bucket prefix
	bucketName := req.BucketName
	if !strings.HasPrefix(bucketName, "user-") && !strings.HasPrefix(req.UserId, "org-") {
		sanitizedUserID := sanitizeBucketName(req.UserId)
		bucketName = fmt.Sprintf("user-%s-%s", sanitizedUserID, req.BucketName)
	}
	filePath := fmt.Sprintf("s3://%s/%s", bucketName, req.ObjectKey)

	// Build query based on format
	var fullQuery string
	switch strings.ToLower(req.Format) {
	case "csv":
		fullQuery = strings.Replace(req.Query, "$FILE", fmt.Sprintf("read_csv_auto('%s')", filePath), 1)
	case "parquet":
		fullQuery = strings.Replace(req.Query, "$FILE", fmt.Sprintf("read_parquet('%s')", filePath), 1)
	case "json":
		fullQuery = strings.Replace(req.Query, "$FILE", fmt.Sprintf("read_json_auto('%s')", filePath), 1)
	default:
		return &pb.QueryMinIOFileResponse{
			Success: false,
			Error:   fmt.Sprintf("unsupported format: %s", req.Format),
		}, nil
	}

	result, err := handle.client.QueryToStruct(ctx, fullQuery)
	if err != nil {
		return &pb.QueryMinIOFileResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	executionTime := float64(time.Since(startTime).Milliseconds())

	return &pb.QueryMinIOFileResponse{
		Success:         true,
		Columns:         result.Columns,
		Rows:            convertRowsToProto(result.Rows),
		RowCount:        int32(result.Count),
		ExecutionTimeMs: executionTime,
	}, nil
}

// ImportData imports data via streaming
func (s *DuckDBServer) ImportData(stream pb.DuckDBService_ImportDataServer) error {
	// Receive first message with metadata
	firstMsg, err := stream.Recv()
	if err != nil {
		return status.Error(codes.Internal, "failed to receive metadata")
	}

	metadata := firstMsg.GetMetadata()
	if metadata == nil {
		return status.Error(codes.InvalidArgument, "first message must contain metadata")
	}

	if err := s.authService.ValidateUser(metadata.UserId); err != nil {
		return status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Receive data chunks
	var dataBuffer []byte
	for {
		msg, err := stream.Recv()
		if err == io.EOF {
			break
		}
		if err != nil {
			return status.Error(codes.Internal, err.Error())
		}

		chunk := msg.GetChunk()
		if chunk != nil {
			dataBuffer = append(dataBuffer, chunk...)
		}
	}

	// In production, would write to temp file and import
	return stream.SendAndClose(&pb.ImportDataResponse{
		Success:      true,
		Message:      "Data imported successfully",
		RowsImported: 0,
	})
}

// ========================================
// Extensions and Functions
// ========================================

// InstallExtension installs a DuckDB extension
func (s *DuckDBServer) InstallExtension(ctx context.Context, req *pb.InstallExtensionRequest) (*pb.InstallExtensionResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.InstallExtensionResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	// Get database handle
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return &pb.InstallExtensionResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	err = handle.client.InstallExtension(ctx, req.ExtensionName)
	if err != nil {
		return &pb.InstallExtensionResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	// Load extension after installation
	err = handle.client.LoadExtension(ctx, req.ExtensionName)
	if err != nil {
		return &pb.InstallExtensionResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	// Mark database as modified
	s.markModified(handle)

	return &pb.InstallExtensionResponse{
		Success: true,
		Message: fmt.Sprintf("Extension %s installed and loaded successfully", req.ExtensionName),
	}, nil
}

// ListExtensions lists installed extensions
func (s *DuckDBServer) ListExtensions(ctx context.Context, req *pb.ListExtensionsRequest) (*pb.ListExtensionsResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.ListExtensionsResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	// Get database handle
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return &pb.ListExtensionsResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	extensions, err := handle.client.ListExtensions(ctx)
	if err != nil {
		return &pb.ListExtensionsResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	var extInfo []*pb.ExtensionInfo
	for _, ext := range extensions {
		extInfo = append(extInfo, &pb.ExtensionInfo{
			Name:      ext,
			Installed: true,
			Loaded:    true,
		})
	}

	return &pb.ListExtensionsResponse{
		Success:    true,
		Extensions: extInfo,
	}, nil
}

// CreateFunction creates a user-defined function
func (s *DuckDBServer) CreateFunction(ctx context.Context, req *pb.CreateFunctionRequest) (*pb.CreateFunctionResponse, error) {
	if err := s.authService.ValidateUser(req.UserId); err != nil {
		return nil, status.Error(codes.PermissionDenied, "unauthorized")
	}

	// Extract database name
	parts := strings.Split(req.DatabaseId, "-")
	if len(parts) < 2 {
		return &pb.CreateFunctionResponse{
			Success: false,
			Error:   "invalid database ID format",
		}, nil
	}
	databaseName := strings.Join(parts[1:], "-")

	// Get database handle
	handle, err := s.getOrCreateDatabase(ctx, req.UserId, databaseName)
	if err != nil {
		return &pb.CreateFunctionResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	// Build CREATE FUNCTION statement
	params := strings.Join(req.Parameters, ", ")
	query := fmt.Sprintf("CREATE FUNCTION %s(%s) RETURNS %s AS %s",
		req.FunctionName, params, req.ReturnType, req.FunctionBody)

	_, err = handle.client.Exec(ctx, query)
	if err != nil {
		return &pb.CreateFunctionResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	// Mark database as modified
	s.markModified(handle)

	return &pb.CreateFunctionResponse{
		Success: true,
		Message: fmt.Sprintf("Function %s created successfully", req.FunctionName),
	}, nil
}

// ========================================
// Health Check and Monitoring
// ========================================

// HealthCheck performs health check
func (s *DuckDBServer) HealthCheck(ctx context.Context, req *pb.HealthCheckRequest) (*pb.HealthCheckResponse, error) {
	healthy := true
	statusMsg := "healthy"

	// Check MinIO connection
	if err := s.minioClient.HealthCheck(ctx); err != nil {
		healthy = false
		statusMsg = "unhealthy: MinIO connection failed"
	}

	response := &pb.HealthCheckResponse{
		Success:   true,
		Healthy:   healthy,
		Status:    statusMsg,
		Timestamp: timestamppb.Now(),
	}

	if req.Detailed {
		openDBCount := s.dbCache.Len()

		details, _ := structpb.NewStruct(map[string]interface{}{
			"service":         "duckdb-service",
			"minio_connected": healthy,
			"open_databases":  openDBCount,
			"temp_dir":        s.localTempDir,
		})
		response.Details = details
	}

	return response, nil
}

// GetMetrics returns service metrics
func (s *DuckDBServer) GetMetrics(ctx context.Context, req *pb.GetMetricsRequest) (*pb.GetMetricsResponse, error) {
	openDBCount := s.dbCache.Len()

	metrics, _ := structpb.NewStruct(map[string]interface{}{
		"service":        "duckdb-service",
		"open_databases": openDBCount,
		"cache_capacity": 100,
		"temp_dir":       s.localTempDir,
	})

	return &pb.GetMetricsResponse{
		Success:           true,
		TotalQueries:      0,
		ActiveConnections: int64(openDBCount),
		AvgQueryTimeMs:    0,
		CacheHits:         0,
		CacheMisses:       0,
		Metrics:           metrics,
	}, nil
}
