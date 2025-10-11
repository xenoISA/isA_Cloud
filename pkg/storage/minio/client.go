// Package minio provides a unified MinIO client wrapper for the isA Cloud platform
// 为 isA Cloud 平台提供统一的 MinIO 对象存储客户端封装
//
// 示例用法:
//
//	cfg := &minio.Config{
//	    Endpoint:  "localhost:9000",
//	    AccessKey: "minioadmin",
//	    SecretKey: "minioadmin",
//	    UseSSL:    false,
//	}
//	client, err := minio.NewClient(cfg)
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer client.Close()
//
//	// 上传文件
//	err = client.PutObject(ctx, "my-bucket", "file.txt", reader, size, PutOptions{})
package minio

import (
	"context"
	"fmt"
	"io"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

// Client MinIO 客户端封装
// 提供线程安全的对象存储操作
type Client struct {
	client *minio.Client
	config *Config
}

// Config MinIO 客户端配置
type Config struct {
	Endpoint       string        // MinIO 端点，如 "localhost:9000"
	AccessKey      string        // 访问密钥
	SecretKey      string        // 私钥
	UseSSL         bool          // 是否使用 SSL/TLS
	Region         string        // 区域，默认 "us-east-1"
	BucketLookup   BucketLookup  // 桶查找方式
	ConnectTimeout time.Duration // 连接超时
	RequestTimeout time.Duration // 请求超时
	MaxRetries     int           // 最大重试次数
}

// BucketLookup 桶查找方式
type BucketLookup int

const (
	// BucketLookupAuto 自动检测
	BucketLookupAuto BucketLookup = iota
	// BucketLookupDNS DNS查找（虚拟主机风格）
	BucketLookupDNS
	// BucketLookupPath 路径风格
	BucketLookupPath
)

// NewClient 创建新的 MinIO 客户端
//
// 参数:
//
//	cfg: MinIO 配置
//
// 返回:
//
//	*Client: MinIO 客户端实例
//	error: 错误信息
//
// 示例:
//
//	cfg := &Config{
//	    Endpoint:  "localhost:9000",
//	    AccessKey: "minioadmin",
//	    SecretKey: "minioadmin",
//	}
//	client, err := NewClient(cfg)
func NewClient(cfg *Config) (*Client, error) {
	if cfg == nil {
		return nil, fmt.Errorf("config cannot be nil")
	}

	// 设置默认值
	if cfg.Region == "" {
		cfg.Region = "us-east-1"
	}
	if cfg.ConnectTimeout == 0 {
		cfg.ConnectTimeout = 30 * time.Second
	}
	if cfg.RequestTimeout == 0 {
		cfg.RequestTimeout = 5 * time.Minute
	}
	if cfg.MaxRetries == 0 {
		cfg.MaxRetries = 3
	}

	// 创建MinIO客户端
	opts := &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.AccessKey, cfg.SecretKey, ""),
		Secure: cfg.UseSSL,
		Region: cfg.Region,
	}

	// 设置桶查找方式
	switch cfg.BucketLookup {
	case BucketLookupDNS:
		opts.BucketLookup = minio.BucketLookupDNS
	case BucketLookupPath:
		opts.BucketLookup = minio.BucketLookupPath
	default:
		opts.BucketLookup = minio.BucketLookupAuto
	}

	minioClient, err := minio.New(cfg.Endpoint, opts)
	if err != nil {
		return nil, fmt.Errorf("failed to create MinIO client: %w", err)
	}

	return &Client{
		client: minioClient,
		config: cfg,
	}, nil
}

// Close 关闭客户端连接
func (c *Client) Close() error {
	// MinIO Go 客户端不需要显式关闭
	return nil
}

// ============================================
// 桶操作 (Bucket Operations)
// ============================================

// BucketInfo 桶信息
type BucketInfo struct {
	Name         string
	CreationDate time.Time
}

// MakeBucket 创建桶
//
// 参数:
//
//	ctx: 上下文
//	bucketName: 桶名称
//	location: 区域（可选）
//
// 示例:
//
//	err := client.MakeBucket(ctx, "my-bucket", "us-east-1")
func (c *Client) MakeBucket(ctx context.Context, bucketName, location string) error {
	if location == "" {
		location = c.config.Region
	}

	opts := minio.MakeBucketOptions{
		Region:        location,
		ObjectLocking: false,
	}

	err := c.client.MakeBucket(ctx, bucketName, opts)
	if err != nil {
		// 检查桶是否已存在
		exists, errExists := c.client.BucketExists(ctx, bucketName)
		if errExists == nil && exists {
			return fmt.Errorf("bucket already exists: %s", bucketName)
		}
		return fmt.Errorf("failed to create bucket: %w", err)
	}

	return nil
}

// ListBuckets 列出所有桶
//
// 返回:
//
//	[]BucketInfo: 桶信息列表
//	error: 错误信息
//
// 示例:
//
//	buckets, err := client.ListBuckets(ctx)
//	for _, bucket := range buckets {
//	    fmt.Printf("Bucket: %s, Created: %s\n", bucket.Name, bucket.CreationDate)
//	}
func (c *Client) ListBuckets(ctx context.Context) ([]BucketInfo, error) {
	buckets, err := c.client.ListBuckets(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to list buckets: %w", err)
	}

	result := make([]BucketInfo, len(buckets))
	for i, bucket := range buckets {
		result[i] = BucketInfo{
			Name:         bucket.Name,
			CreationDate: bucket.CreationDate,
		}
	}

	return result, nil
}

// BucketExists 检查桶是否存在
func (c *Client) BucketExists(ctx context.Context, bucketName string) (bool, error) {
	exists, err := c.client.BucketExists(ctx, bucketName)
	if err != nil {
		return false, fmt.Errorf("failed to check bucket existence: %w", err)
	}
	return exists, nil
}

// RemoveBucket 删除桶（桶必须为空）
func (c *Client) RemoveBucket(ctx context.Context, bucketName string) error {
	err := c.client.RemoveBucket(ctx, bucketName)
	if err != nil {
		return fmt.Errorf("failed to remove bucket: %w", err)
	}
	return nil
}

// RemoveBucketForce 强制删除桶（包括所有对象）
//
// 示例:
//
//	err := client.RemoveBucketForce(ctx, "my-bucket")
func (c *Client) RemoveBucketForce(ctx context.Context, bucketName string) (int, error) {
	// 列出所有对象
	objectsCh := c.client.ListObjects(ctx, bucketName, minio.ListObjectsOptions{
		Recursive: true,
	})

	// 删除所有对象
	deletedCount := 0
	for object := range objectsCh {
		if object.Err != nil {
			return deletedCount, fmt.Errorf("failed to list objects: %w", object.Err)
		}

		err := c.client.RemoveObject(ctx, bucketName, object.Key, minio.RemoveObjectOptions{})
		if err != nil {
			return deletedCount, fmt.Errorf("failed to remove object %s: %w", object.Key, err)
		}
		deletedCount++
	}

	// 删除桶
	err := c.RemoveBucket(ctx, bucketName)
	if err != nil {
		return deletedCount, err
	}

	return deletedCount, nil
}

// ============================================
// 对象操作 (Object Operations)
// ============================================

// ObjectInfo 对象信息
type ObjectInfo struct {
	Key          string
	Size         int64
	ETag         string
	ContentType  string
	LastModified time.Time
	Metadata     map[string]string
	StorageClass string
	VersionID    string
}

// PutOptions 上传选项
type PutOptions struct {
	ContentType     string            // MIME 类型
	Metadata        map[string]string // 自定义元数据
	StorageClass    string            // 存储类型
	UserTags        map[string]string // 用户标签
	PartSize        uint64            // 分片大小（字节）
	NumThreads      uint              // 并发线程数
	DisableChecksum bool              // 禁用校验和
}

// PutObject 上传对象
//
// 参数:
//
//	ctx: 上下文
//	bucketName: 桶名称
//	objectKey: 对象键（路径）
//	reader: 数据读取器
//	objectSize: 对象大小（-1 表示未知大小）
//	opts: 上传选项
//
// 返回:
//
//	ObjectInfo: 上传后的对象信息
//	error: 错误信息
//
// 示例:
//
//	file, _ := os.Open("file.txt")
//	defer file.Close()
//	info, _ := file.Stat()
//
//	objInfo, err := client.PutObject(ctx, "my-bucket", "path/to/file.txt",
//	    file, info.Size(), PutOptions{ContentType: "text/plain"})
func (c *Client) PutObject(ctx context.Context, bucketName, objectKey string, reader io.Reader, objectSize int64, opts PutOptions) (ObjectInfo, error) {
	putOpts := minio.PutObjectOptions{
		ContentType:  opts.ContentType,
		UserMetadata: opts.Metadata,
		UserTags:     opts.UserTags,
		StorageClass: opts.StorageClass,
		PartSize:     opts.PartSize,
		NumThreads:   opts.NumThreads,
	}

	info, err := c.client.PutObject(ctx, bucketName, objectKey, reader, objectSize, putOpts)
	if err != nil {
		return ObjectInfo{}, fmt.Errorf("failed to put object: %w", err)
	}

	return ObjectInfo{
		Key:       info.Key,
		Size:      info.Size,
		ETag:      info.ETag,
		VersionID: info.VersionID,
	}, nil
}

// GetObject 下载对象
//
// 返回:
//
//	io.ReadCloser: 对象数据流（使用后需要关闭）
//	error: 错误信息
//
// 示例:
//
//	object, err := client.GetObject(ctx, "my-bucket", "path/to/file.txt", GetOptions{})
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer object.Close()
//
//	data, _ := io.ReadAll(object)
//	fmt.Println(string(data))
func (c *Client) GetObject(ctx context.Context, bucketName, objectKey string, opts GetOptions) (io.ReadCloser, error) {
	getOpts := minio.GetObjectOptions{}

	if opts.VersionID != "" {
		getOpts.VersionID = opts.VersionID
	}

	if opts.PartNumber > 0 {
		getOpts.PartNumber = opts.PartNumber
	}

	// 设置范围
	if opts.Offset > 0 || opts.Length > 0 {
		if opts.Length > 0 {
			err := getOpts.SetRange(opts.Offset, opts.Offset+opts.Length-1)
			if err != nil {
				return nil, fmt.Errorf("failed to set range: %w", err)
			}
		}
	}

	object, err := c.client.GetObject(ctx, bucketName, objectKey, getOpts)
	if err != nil {
		return nil, fmt.Errorf("failed to get object: %w", err)
	}

	return object, nil
}

// GetOptions 下载选项
type GetOptions struct {
	VersionID  string // 版本ID
	Offset     int64  // 字节偏移量
	Length     int64  // 读取长度
	PartNumber int    // 分片编号
}

// StatObject 获取对象信息（不下载内容）
//
// 示例:
//
//	info, err := client.StatObject(ctx, "my-bucket", "path/to/file.txt", StatOptions{})
//	fmt.Printf("Size: %d, ETag: %s\n", info.Size, info.ETag)
func (c *Client) StatObject(ctx context.Context, bucketName, objectKey string, opts StatOptions) (ObjectInfo, error) {
	statOpts := minio.StatObjectOptions{}

	if opts.VersionID != "" {
		statOpts.VersionID = opts.VersionID
	}

	info, err := c.client.StatObject(ctx, bucketName, objectKey, statOpts)
	if err != nil {
		return ObjectInfo{}, fmt.Errorf("failed to stat object: %w", err)
	}

	return ObjectInfo{
		Key:          info.Key,
		Size:         info.Size,
		ETag:         info.ETag,
		ContentType:  info.ContentType,
		LastModified: info.LastModified,
		Metadata:     info.UserMetadata,
		StorageClass: info.StorageClass,
		VersionID:    info.VersionID,
	}, nil
}

// StatOptions 获取对象信息选项
type StatOptions struct {
	VersionID string
}

// RemoveObject 删除对象
func (c *Client) RemoveObject(ctx context.Context, bucketName, objectKey string) error {
	opts := minio.RemoveObjectOptions{}
	err := c.client.RemoveObject(ctx, bucketName, objectKey, opts)
	if err != nil {
		return fmt.Errorf("failed to remove object: %w", err)
	}
	return nil
}

// RemoveObjects 批量删除对象
//
// 示例:
//
//	keys := []string{"file1.txt", "file2.txt", "file3.txt"}
//	deleted, errors := client.RemoveObjects(ctx, "my-bucket", keys)
func (c *Client) RemoveObjects(ctx context.Context, bucketName string, objectKeys []string) ([]string, []error) {
	objectsCh := make(chan minio.ObjectInfo)

	go func() {
		defer close(objectsCh)
		for _, key := range objectKeys {
			objectsCh <- minio.ObjectInfo{Key: key}
		}
	}()

	opts := minio.RemoveObjectsOptions{}
	errorsCh := c.client.RemoveObjects(ctx, bucketName, objectsCh, opts)

	var deleted []string
	var errors []error

	for err := range errorsCh {
		if err.Err != nil {
			errors = append(errors, fmt.Errorf("failed to remove %s: %w", err.ObjectName, err.Err))
		} else {
			deleted = append(deleted, err.ObjectName)
		}
	}

	return deleted, errors
}

// ListObjects 列出对象
//
// 示例:
//
//	objects, err := client.ListObjects(ctx, "my-bucket", ListOptions{
//	    Prefix:    "folder/",
//	    Recursive: true,
//	})
func (c *Client) ListObjects(ctx context.Context, bucketName string, opts ListOptions) ([]ObjectInfo, error) {
	listOpts := minio.ListObjectsOptions{
		Prefix:    opts.Prefix,
		Recursive: opts.Recursive,
		MaxKeys:   opts.MaxKeys,
	}

	var objects []ObjectInfo
	for object := range c.client.ListObjects(ctx, bucketName, listOpts) {
		if object.Err != nil {
			return nil, fmt.Errorf("failed to list objects: %w", object.Err)
		}

		objects = append(objects, ObjectInfo{
			Key:          object.Key,
			Size:         object.Size,
			ETag:         object.ETag,
			LastModified: object.LastModified,
			StorageClass: object.StorageClass,
		})
	}

	return objects, nil
}

// ListOptions 列出对象选项
type ListOptions struct {
	Prefix    string // 前缀过滤
	Recursive bool   // 是否递归列出
	MaxKeys   int    // 最大返回数量
}

// CopyObject 复制对象
//
// 示例:
//
//	err := client.CopyObject(ctx, "source-bucket", "source.txt",
//	    "dest-bucket", "dest.txt", CopyOptions{})
func (c *Client) CopyObject(ctx context.Context, srcBucket, srcKey, destBucket, destKey string, opts CopyOptions) error {
	srcOpts := minio.CopySrcOptions{
		Bucket: srcBucket,
		Object: srcKey,
	}

	destOpts := minio.CopyDestOptions{
		Bucket:       destBucket,
		Object:       destKey,
		UserMetadata: opts.Metadata,
	}

	_, err := c.client.CopyObject(ctx, destOpts, srcOpts)
	if err != nil {
		return fmt.Errorf("failed to copy object: %w", err)
	}

	return nil
}

// CopyOptions 复制选项
type CopyOptions struct {
	Metadata map[string]string
}

// ============================================
// 预签名 URL (Presigned URLs)
// ============================================

// PresignedGetURL 生成预签名下载 URL
//
// 参数:
//
//	ctx: 上下文
//	bucketName: 桶名称
//	objectKey: 对象键
//	expiry: URL 过期时间
//
// 返回:
//
//	string: 预签名 URL
//	error: 错误信息
//
// 示例:
//
//	url, err := client.PresignedGetURL(ctx, "my-bucket", "file.txt", 1*time.Hour)
//	fmt.Println("Download URL:", url)
func (c *Client) PresignedGetURL(ctx context.Context, bucketName, objectKey string, expiry time.Duration) (string, error) {
	url, err := c.client.PresignedGetObject(ctx, bucketName, objectKey, expiry, nil)
	if err != nil {
		return "", fmt.Errorf("failed to generate presigned GET URL: %w", err)
	}
	return url.String(), nil
}

// PresignedPutURL 生成预签名上传 URL
//
// 示例:
//
//	url, err := client.PresignedPutURL(ctx, "my-bucket", "file.txt", 1*time.Hour)
//	// 客户端可以使用此 URL 直接上传文件
func (c *Client) PresignedPutURL(ctx context.Context, bucketName, objectKey string, expiry time.Duration) (string, error) {
	url, err := c.client.PresignedPutObject(ctx, bucketName, objectKey, expiry)
	if err != nil {
		return "", fmt.Errorf("failed to generate presigned PUT URL: %w", err)
	}
	return url.String(), nil
}

// ============================================
// 工具方法 (Utility Methods)
// ============================================

// HealthCheck 健康检查
func (c *Client) HealthCheck(ctx context.Context) error {
	_, err := c.ListBuckets(ctx)
	if err != nil {
		return fmt.Errorf("health check failed: %w", err)
	}
	return nil
}

// GetConfig 获取客户端配置
func (c *Client) GetConfig() *Config {
	return c.config
}


