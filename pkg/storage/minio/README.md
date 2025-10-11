# MinIO SDK Client

## 文件名：`minio/client.go`

MinIO SDK Client 为 isA Cloud 平台提供统一的对象存储访问接口。这是一个通用的对象存储服务，为所有后端服务提供文件存储能力。

## 主要功能

- **桶管理**：创建、列出、删除桶
- **对象操作**：上传、下载、删除、列出对象
- **流式传输**：支持大文件的流式上传和下载
- **预签名 URL**：生成临时访问链接
- **批量操作**：批量删除对象
- **多租户隔离**：支持用户和组织级别的隔离

## 快速开始

### 1. 安装依赖

```bash
go get github.com/minio/minio-go/v7
```

### 2. 创建客户端

```go
package main

import (
    "context"
    "log"
    
    "github.com/isa-cloud/isa_cloud/pkg/storage/minio"
)

func main() {
    // 配置 MinIO 客户端
    cfg := &minio.Config{
        Endpoint:  "localhost:9000",
        AccessKey: "minioadmin",
        SecretKey: "minioadmin",
        UseSSL:    false,
        Region:    "us-east-1",
    }
    
    // 创建客户端
    client, err := minio.NewClient(cfg)
    if err != nil {
        log.Fatal(err)
    }
    defer client.Close()
    
    // 使用客户端...
}
```

## 使用示例

### 桶操作

#### 创建桶

```go
ctx := context.Background()

// 创建桶
err := client.MakeBucket(ctx, "my-bucket", "us-east-1")
if err != nil {
    log.Printf("Failed to create bucket: %v", err)
}
```

#### 列出所有桶

```go
buckets, err := client.ListBuckets(ctx)
if err != nil {
    log.Fatal(err)
}

for _, bucket := range buckets {
    fmt.Printf("Bucket: %s, Created: %s\n", 
        bucket.Name, 
        bucket.CreationDate.Format(time.RFC3339))
}
```

#### 删除桶

```go
// 删除空桶
err := client.RemoveBucket(ctx, "my-bucket")

// 强制删除桶（包括所有对象）
deletedCount, err := client.RemoveBucketForce(ctx, "my-bucket")
fmt.Printf("Deleted %d objects\n", deletedCount)
```

### 对象操作

#### 上传文件

```go
// 从文件上传
file, err := os.Open("document.pdf")
if err != nil {
    log.Fatal(err)
}
defer file.Close()

info, _ := file.Stat()

objInfo, err := client.PutObject(ctx, "my-bucket", "docs/document.pdf", 
    file, info.Size(), minio.PutOptions{
        ContentType: "application/pdf",
        Metadata: map[string]string{
            "x-user-id": "user123",
            "x-org-id":  "org456",
        },
    })

fmt.Printf("Uploaded: %s, Size: %d bytes, ETag: %s\n", 
    objInfo.Key, objInfo.Size, objInfo.ETag)
```

#### 从字符串/字节上传

```go
import "bytes"

data := []byte("Hello, MinIO!")
reader := bytes.NewReader(data)

objInfo, err := client.PutObject(ctx, "my-bucket", "hello.txt",
    reader, int64(len(data)), minio.PutOptions{
        ContentType: "text/plain",
    })
```

#### 下载文件

```go
// 下载对象
object, err := client.GetObject(ctx, "my-bucket", "docs/document.pdf", minio.GetOptions{})
if err != nil {
    log.Fatal(err)
}
defer object.Close()

// 保存到文件
outFile, err := os.Create("downloaded.pdf")
if err != nil {
    log.Fatal(err)
}
defer outFile.Close()

_, err = io.Copy(outFile, object)
if err != nil {
    log.Fatal(err)
}
```

#### 范围下载（断点续传）

```go
// 下载文件的一部分（从第1000字节开始，读取5000字节）
object, err := client.GetObject(ctx, "my-bucket", "largefile.dat", 
    minio.GetOptions{
        Offset: 1000,
        Length: 5000,
    })
```

#### 获取对象信息

```go
info, err := client.StatObject(ctx, "my-bucket", "docs/document.pdf", 
    minio.StatOptions{})

fmt.Printf("Key: %s\n", info.Key)
fmt.Printf("Size: %d bytes\n", info.Size)
fmt.Printf("ETag: %s\n", info.ETag)
fmt.Printf("Content-Type: %s\n", info.ContentType)
fmt.Printf("Last Modified: %s\n", info.LastModified)
fmt.Printf("Metadata: %+v\n", info.Metadata)
```

#### 列出对象

```go
// 列出桶中的所有对象
objects, err := client.ListObjects(ctx, "my-bucket", minio.ListOptions{
    Prefix:    "docs/",      // 只列出 docs/ 前缀的对象
    Recursive: true,         // 递归列出子文件夹
    MaxKeys:   100,          // 最多返回100个对象
})

for _, obj := range objects {
    fmt.Printf("Object: %s, Size: %d bytes\n", obj.Key, obj.Size)
}
```

#### 删除对象

```go
// 删除单个对象
err := client.RemoveObject(ctx, "my-bucket", "docs/old-doc.pdf")

// 批量删除对象
keys := []string{
    "docs/file1.txt",
    "docs/file2.txt",
    "docs/file3.txt",
}
deleted, errors := client.RemoveObjects(ctx, "my-bucket", keys)

fmt.Printf("Deleted %d objects\n", len(deleted))
if len(errors) > 0 {
    for _, err := range errors {
        log.Printf("Error: %v", err)
    }
}
```

#### 复制对象

```go
// 复制对象到同一个或不同的桶
err := client.CopyObject(ctx, 
    "source-bucket", "path/to/source.txt",
    "dest-bucket", "path/to/dest.txt",
    minio.CopyOptions{
        Metadata: map[string]string{
            "x-copied": "true",
        },
    })
```

### 预签名 URL

#### 生成下载链接

```go
// 生成1小时有效的下载链接
url, err := client.PresignedGetURL(ctx, "my-bucket", "docs/report.pdf", 
    1*time.Hour)

fmt.Println("Download URL:", url)
// 客户端可以使用此 URL 直接下载文件（无需认证）
```

#### 生成上传链接

```go
// 生成1小时有效的上传链接
url, err := client.PresignedPutURL(ctx, "my-bucket", "uploads/file.txt", 
    1*time.Hour)

fmt.Println("Upload URL:", url)
// 客户端可以使用此 URL 通过 HTTP PUT 直接上传文件
```

### 健康检查

```go
err := client.HealthCheck(ctx)
if err != nil {
    log.Printf("MinIO health check failed: %v", err)
} else {
    log.Println("MinIO is healthy")
}
```

## 配置选项

```go
cfg := &minio.Config{
    Endpoint:        "localhost:9000",      // MinIO 端点
    AccessKey:       "minioadmin",          // 访问密钥
    SecretKey:       "minioadmin",          // 私钥
    UseSSL:          false,                 // 是否使用 SSL/TLS
    Region:          "us-east-1",           // 区域
    BucketLookup:    minio.BucketLookupAuto, // 桶查找方式
    ConnectTimeout:  30 * time.Second,      // 连接超时
    RequestTimeout:  5 * time.Minute,       // 请求超时
    MaxRetries:      3,                     // 最大重试次数
}
```

## 用户隔离实践

为了实现多租户隔离，建议使用以下命名规范：

```go
// 按用户隔离
bucketName := fmt.Sprintf("user-%s", userID)

// 按组织隔离
bucketName := fmt.Sprintf("org-%s", organizationID)

// 混合隔离（组织/用户）
objectKey := fmt.Sprintf("%s/%s/data.json", organizationID, userID)
```

示例：

```go
func uploadUserFile(client *minio.Client, userID, fileName string, data io.Reader, size int64) error {
    ctx := context.Background()
    
    // 用户专属桶
    bucketName := fmt.Sprintf("user-%s", userID)
    
    // 确保桶存在
    exists, err := client.BucketExists(ctx, bucketName)
    if err != nil {
        return err
    }
    if !exists {
        if err := client.MakeBucket(ctx, bucketName, ""); err != nil {
            return err
        }
    }
    
    // 上传文件
    _, err = client.PutObject(ctx, bucketName, fileName, data, size,
        minio.PutOptions{
            Metadata: map[string]string{
                "x-user-id": userID,
                "x-upload-time": time.Now().Format(time.RFC3339),
            },
        })
    
    return err
}
```

## 性能优化

### 分片上传大文件

```go
opts := minio.PutOptions{
    PartSize:   64 * 1024 * 1024, // 64MB 每片
    NumThreads: 4,                 // 4个并发线程
}

objInfo, err := client.PutObject(ctx, "my-bucket", "large-file.zip",
    file, fileSize, opts)
```

### 连接池配置

```go
cfg := &minio.Config{
    // ... 其他配置
    MaxOpenConns: 100,             // 最大打开连接数
    MaxIdleConns: 50,              // 最大空闲连接数
    ConnMaxLife:  30 * time.Minute, // 连接最大生命周期
}
```

## 错误处理

```go
import "github.com/minio/minio-go/v7"

objInfo, err := client.PutObject(ctx, "my-bucket", "file.txt", reader, size, opts)
if err != nil {
    // 检查特定错误类型
    switch err := err.(type) {
    case minio.ErrorResponse:
        if err.Code == "NoSuchBucket" {
            log.Println("Bucket does not exist")
        } else if err.Code == "AccessDenied" {
            log.Println("Access denied")
        }
    default:
        log.Printf("Unknown error: %v", err)
    }
    return err
}
```

## 集成到 gRPC 服务

参考 `cmd/minio-service/` 目录中的 gRPC 服务实现示例。

## 相关文档

- [MinIO Go Client API Reference](https://min.io/docs/minio/linux/developers/go/API.html)
- [MinIO 官方文档](https://min.io/docs)
- isA Cloud 项目架构文档



