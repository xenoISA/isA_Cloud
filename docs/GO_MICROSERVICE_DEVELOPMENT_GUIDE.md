# Go Microservice Development Guide

> isA Cloud Platform - Go 微服务开发规范与标准指南
> Version: 1.0.0 | Last Updated: 2024-11

---

## 目录

1. [架构概述](#1-架构概述)
2. [项目结构标准](#2-项目结构标准)
3. [Proto 定义规范](#3-proto-定义规范)
4. [数据模型层](#4-数据模型层)
5. [Repository 层](#5-repository-层)
6. [Service 层](#6-service-层)
7. [gRPC Handler 层](#7-grpc-handler-层)
8. [依赖注入](#8-依赖注入)
9. [服务间同步通信](#9-服务间同步通信)
10. [异步事件机制](#10-异步事件机制)
11. [错误处理](#11-错误处理)
12. [配置管理](#12-配置管理)
13. [测试规范](#13-测试规范)
14. [服务注册与发现](#14-服务注册与发现)
15. [完整示例](#15-完整示例)

---

## 1. 架构概述

### 1.1 整体架构

采用 **Clean Architecture** (洁净架构) + **Hexagonal Architecture** (六边形架构) 的混合模式：

```
┌─────────────────────────────────────────────────────────────────┐
│                         External World                          │
│  (gRPC Clients, HTTP Gateway, Event Bus, Other Services)        │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                      Transport Layer                             │
│                   (gRPC Handlers / HTTP)                         │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                      Service Layer                               │
│              (Business Logic / Use Cases)                        │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                     Repository Layer                             │
│                  (Data Access Abstraction)                       │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                   Infrastructure Layer                           │
│        (PostgreSQL, Redis, NATS, External Services)              │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 核心原则

1. **依赖规则 (Dependency Rule)**: 依赖只能从外向内，内层不知道外层的存在
2. **接口隔离 (Interface Segregation)**: 层与层之间通过接口通信
3. **单一职责 (Single Responsibility)**: 每个模块只做一件事
4. **可测试性 (Testability)**: 所有层可以独立测试

### 1.3 技术栈

| 组件 | 技术选型 |
|------|----------|
| RPC 框架 | gRPC + Protocol Buffers |
| 数据库 | PostgreSQL (via pgx/v5) |
| 缓存 | Redis |
| 消息队列 | NATS JetStream |
| 服务发现 | Consul |
| 配置管理 | Environment Variables + Config Files |
| 日志 | Structured Logging (slog) |
| 依赖注入 | 构造函数注入 (Constructor Injection) |

---

## 2. 项目结构标准

### 2.1 完整目录结构

```
isA_Cloud/
├── api/
│   └── proto/
│       ├── common/                    # 通用 proto 定义
│       │   └── common.proto
│       ├── account/                   # Account 服务 proto
│       │   ├── account.proto          # 源文件
│       │   ├── account.pb.go          # 生成的消息定义
│       │   └── account_grpc.pb.go     # 生成的 gRPC 代码
│       └── {service_name}/            # 其他服务 proto
│
├── cmd/
│   └── {service_name}/
│       └── main.go                    # 服务入口点
│
├── internal/
│   ├── config/                        # 全局配置
│   │   └── config.go
│   ├── eventbus/                      # 事件总线客户端
│   │   ├── client.go
│   │   └── types.go
│   └── {service_name}/                # 服务内部实现
│       ├── domain/                    # 领域模型
│       │   ├── entity.go              # 实体定义
│       │   ├── value_object.go        # 值对象
│       │   └── errors.go              # 领域错误
│       ├── repository/                # 数据访问层
│       │   ├── interface.go           # Repository 接口
│       │   └── postgres.go            # PostgreSQL 实现
│       ├── service/                   # 业务逻辑层
│       │   ├── interface.go           # Service 接口
│       │   └── service.go             # Service 实现
│       ├── handler/                   # gRPC 处理器
│       │   └── grpc_handler.go
│       ├── event/                     # 事件定义与处理
│       │   ├── events.go              # 事件类型定义
│       │   ├── publisher.go           # 事件发布
│       │   └── subscriber.go          # 事件订阅处理
│       └── client/                    # 其他服务客户端
│           └── notification_client.go
│
├── pkg/                               # 可复用的公共包
│   ├── grpc/                          # gRPC 工具
│   │   └── interceptors.go
│   ├── infrastructure/                # 基础设施适配器
│   │   ├── database/
│   │   │   └── postgres/
│   │   │       └── client.go
│   │   ├── cache/
│   │   │   └── redis/
│   │   │       └── client.go
│   │   └── messaging/
│   │       └── nats/
│   │           └── client.go
│   ├── logger/                        # 日志工具
│   │   └── logger.go
│   └── errors/                        # 错误处理工具
│       └── errors.go
│
├── deployments/                       # 部署配置
│   ├── dockerfiles/
│   │   └── Dockerfile.{service_name}
│   └── kubernetes/
│       └── {service_name}/
│
├── scripts/                           # 脚本工具
│   └── generate_proto.sh
│
├── go.mod
├── go.sum
└── Makefile
```

### 2.2 服务内部结构详解

每个微服务应遵循以下内部结构：

```
internal/account/
├── domain/                 # 领域层 (最内层)
│   ├── entity.go           # 核心实体：Account, User
│   ├── value_object.go     # 值对象：Email, SubscriptionStatus
│   ├── errors.go           # 领域错误定义
│   └── repository.go       # Repository 接口定义 (可选，也可放在 repository/ 下)
│
├── repository/             # 数据访问层
│   ├── interface.go        # Repository 接口
│   ├── postgres.go         # PostgreSQL 实现
│   ├── redis_cache.go      # 缓存实现 (可选)
│   └── repository_test.go  # Repository 测试
│
├── service/                # 业务逻辑层
│   ├── interface.go        # Service 接口
│   ├── service.go          # Service 实现
│   ├── dto.go              # 数据传输对象 (输入/输出)
│   └── service_test.go     # Service 测试
│
├── handler/                # 传输层 (gRPC Handler)
│   ├── grpc_handler.go     # gRPC 服务实现
│   ├── converter.go        # Proto <-> Domain 转换器
│   └── handler_test.go     # Handler 测试
│
├── event/                  # 事件层
│   ├── events.go           # 事件类型常量
│   ├── publisher.go        # 事件发布器
│   ├── subscriber.go       # 事件订阅处理器
│   └── handlers.go         # 具体事件处理函数
│
└── client/                 # 外部服务客户端
    ├── notification.go     # Notification 服务客户端
    └── auth.go             # Auth 服务客户端
```

---

## 3. Proto 定义规范

### 3.1 文件结构

```
api/proto/{service_name}/
├── {service_name}.proto           # 主服务定义
├── {service_name}.pb.go           # 生成文件 (不手动编辑)
└── {service_name}_grpc.pb.go      # 生成文件 (不手动编辑)
```

### 3.2 Proto 文件规范

```protobuf
// api/proto/account/account.proto
syntax = "proto3";

package account;

option go_package = "github.com/isa-cloud/isa_cloud/api/proto/account";

import "google/protobuf/timestamp.proto";
import "google/protobuf/struct.proto";
import "common/common.proto";

// ============================================
// Service Definition
// ============================================

service AccountService {
  // Account Lifecycle
  rpc EnsureAccount(EnsureAccountRequest) returns (EnsureAccountResponse);
  rpc GetAccount(GetAccountRequest) returns (GetAccountResponse);
  rpc UpdateAccount(UpdateAccountRequest) returns (UpdateAccountResponse);
  rpc DeleteAccount(DeleteAccountRequest) returns (DeleteAccountResponse);

  // Account Query
  rpc ListAccounts(ListAccountsRequest) returns (ListAccountsResponse);
  rpc SearchAccounts(SearchAccountsRequest) returns (SearchAccountsResponse);

  // Account Status
  rpc ChangeAccountStatus(ChangeAccountStatusRequest) returns (ChangeAccountStatusResponse);

  // Health Check
  rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
}

// ============================================
// Common Enums
// ============================================

enum SubscriptionStatus {
  SUBSCRIPTION_STATUS_UNSPECIFIED = 0;
  SUBSCRIPTION_STATUS_FREE = 1;
  SUBSCRIPTION_STATUS_BASIC = 2;
  SUBSCRIPTION_STATUS_PREMIUM = 3;
  SUBSCRIPTION_STATUS_ENTERPRISE = 4;
}

// ============================================
// Request/Response Messages
// ============================================

message EnsureAccountRequest {
  string user_id = 1;
  string email = 2;
  string name = 3;
  SubscriptionStatus subscription_plan = 4;
}

message EnsureAccountResponse {
  common.ResponseMetadata metadata = 1;
  AccountProfile account = 2;
  bool was_created = 3;
}

message GetAccountRequest {
  string user_id = 1;
}

message GetAccountResponse {
  common.ResponseMetadata metadata = 1;
  AccountProfile account = 2;
}

// ... 其他请求响应定义

// ============================================
// Domain Messages
// ============================================

message AccountProfile {
  string user_id = 1;
  string email = 2;
  string name = 3;
  SubscriptionStatus subscription_status = 4;
  bool is_active = 5;
  google.protobuf.Struct preferences = 6;
  google.protobuf.Timestamp created_at = 7;
  google.protobuf.Timestamp updated_at = 8;
}

message AccountSummary {
  string user_id = 1;
  string email = 2;
  string name = 3;
  SubscriptionStatus subscription_status = 4;
  bool is_active = 5;
  google.protobuf.Timestamp created_at = 6;
}
```

### 3.3 通用 Proto 定义

```protobuf
// api/proto/common/common.proto
syntax = "proto3";

package common;

option go_package = "github.com/isa-cloud/isa_cloud/api/proto/common";

import "google/protobuf/timestamp.proto";

// ============================================
// Common Response Metadata
// ============================================

message ResponseMetadata {
  bool success = 1;
  string message = 2;
  string error_code = 3;
  google.protobuf.Timestamp timestamp = 4;
  string trace_id = 5;
}

// ============================================
// Pagination
// ============================================

message PaginationRequest {
  int32 page = 1;
  int32 page_size = 2;
  string sort_by = 3;
  bool sort_desc = 4;
}

message PaginationResponse {
  int32 page = 1;
  int32 page_size = 2;
  int64 total_count = 3;
  int32 total_pages = 4;
  bool has_next = 5;
  bool has_previous = 6;
}

// ============================================
// Health Check
// ============================================

message HealthCheckRequest {
  bool detailed = 1;
}

message HealthCheckResponse {
  bool healthy = 1;
  string status = 2;
  string version = 3;
  map<string, string> details = 4;
}
```

### 3.4 Proto 生成命令

```makefile
# Makefile

PROTO_DIR := api/proto
GO_OUT := .
GRPC_OUT := .

.PHONY: proto
proto:
	@echo "Generating proto files..."
	protoc --proto_path=$(PROTO_DIR) \
		--go_out=$(GO_OUT) --go_opt=paths=source_relative \
		--go-grpc_out=$(GRPC_OUT) --go-grpc_opt=paths=source_relative \
		$(PROTO_DIR)/common/common.proto \
		$(PROTO_DIR)/account/account.proto
	@echo "Proto generation complete"

.PHONY: proto-account
proto-account:
	protoc --proto_path=$(PROTO_DIR) \
		--go_out=$(GO_OUT) --go_opt=paths=source_relative \
		--go-grpc_out=$(GRPC_OUT) --go-grpc_opt=paths=source_relative \
		$(PROTO_DIR)/account/account.proto
```

---

## 4. 数据模型层

### 4.1 领域实体 (Domain Entity)

```go
// internal/account/domain/entity.go
package domain

import (
	"time"
)

// Account 账户实体 - 领域核心对象
type Account struct {
	UserID             string
	Email              Email              // 值对象
	Name               string
	SubscriptionStatus SubscriptionStatus // 值对象 (Enum)
	IsActive           bool
	Preferences        Preferences        // 值对象
	CreatedAt          time.Time
	UpdatedAt          time.Time
}

// NewAccount 创建新账户 (工厂方法)
func NewAccount(userID, email, name string, subscriptionPlan SubscriptionStatus) (*Account, error) {
	emailVO, err := NewEmail(email)
	if err != nil {
		return nil, err
	}

	now := time.Now().UTC()
	return &Account{
		UserID:             userID,
		Email:              emailVO,
		Name:               name,
		SubscriptionStatus: subscriptionPlan,
		IsActive:           true,
		Preferences:        DefaultPreferences(),
		CreatedAt:          now,
		UpdatedAt:          now,
	}, nil
}

// Activate 激活账户
func (a *Account) Activate() {
	a.IsActive = true
	a.UpdatedAt = time.Now().UTC()
}

// Deactivate 停用账户
func (a *Account) Deactivate() {
	a.IsActive = false
	a.UpdatedAt = time.Now().UTC()
}

// UpdateProfile 更新资料
func (a *Account) UpdateProfile(name string, email *Email) error {
	if name != "" {
		a.Name = name
	}
	if email != nil {
		a.Email = *email
	}
	a.UpdatedAt = time.Now().UTC()
	return nil
}

// UpgradePlan 升级订阅计划
func (a *Account) UpgradePlan(newPlan SubscriptionStatus) error {
	if newPlan <= a.SubscriptionStatus {
		return ErrInvalidPlanUpgrade
	}
	a.SubscriptionStatus = newPlan
	a.UpdatedAt = time.Now().UTC()
	return nil
}
```

### 4.2 值对象 (Value Objects)

```go
// internal/account/domain/value_object.go
package domain

import (
	"fmt"
	"regexp"
	"strings"
)

// ============================================
// Email 值对象
// ============================================

type Email string

var emailRegex = regexp.MustCompile(`^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`)

func NewEmail(email string) (Email, error) {
	normalized := strings.ToLower(strings.TrimSpace(email))
	if !emailRegex.MatchString(normalized) {
		return "", ErrInvalidEmail
	}
	return Email(normalized), nil
}

func (e Email) String() string {
	return string(e)
}

func (e Email) Domain() string {
	parts := strings.Split(string(e), "@")
	if len(parts) == 2 {
		return parts[1]
	}
	return ""
}

// ============================================
// SubscriptionStatus 枚举值对象
// ============================================

type SubscriptionStatus int

const (
	SubscriptionStatusUnspecified SubscriptionStatus = iota
	SubscriptionStatusFree
	SubscriptionStatusBasic
	SubscriptionStatusPremium
	SubscriptionStatusEnterprise
)

func (s SubscriptionStatus) String() string {
	switch s {
	case SubscriptionStatusFree:
		return "free"
	case SubscriptionStatusBasic:
		return "basic"
	case SubscriptionStatusPremium:
		return "premium"
	case SubscriptionStatusEnterprise:
		return "enterprise"
	default:
		return "unspecified"
	}
}

func ParseSubscriptionStatus(s string) SubscriptionStatus {
	switch strings.ToLower(s) {
	case "free":
		return SubscriptionStatusFree
	case "basic":
		return SubscriptionStatusBasic
	case "premium":
		return SubscriptionStatusPremium
	case "enterprise":
		return SubscriptionStatusEnterprise
	default:
		return SubscriptionStatusUnspecified
	}
}

// ============================================
// Preferences 值对象
// ============================================

type Preferences struct {
	Timezone          string `json:"timezone"`
	Language          string `json:"language"`
	Theme             string `json:"theme"`
	NotificationEmail bool   `json:"notification_email"`
	NotificationPush  bool   `json:"notification_push"`
}

func DefaultPreferences() Preferences {
	return Preferences{
		Timezone:          "UTC",
		Language:          "en",
		Theme:             "system",
		NotificationEmail: true,
		NotificationPush:  true,
	}
}

func (p Preferences) ToMap() map[string]interface{} {
	return map[string]interface{}{
		"timezone":           p.Timezone,
		"language":           p.Language,
		"theme":              p.Theme,
		"notification_email": p.NotificationEmail,
		"notification_push":  p.NotificationPush,
	}
}
```

### 4.3 领域错误

```go
// internal/account/domain/errors.go
package domain

import "errors"

// 领域层错误定义
var (
	// 验证错误
	ErrInvalidEmail        = errors.New("invalid email format")
	ErrInvalidUserID       = errors.New("user_id is required")
	ErrInvalidName         = errors.New("name is required")
	ErrInvalidPlanUpgrade  = errors.New("cannot downgrade subscription plan")

	// 业务规则错误
	ErrAccountNotFound     = errors.New("account not found")
	ErrAccountAlreadyExists = errors.New("account already exists")
	ErrAccountInactive     = errors.New("account is inactive")
	ErrAccountDeleted      = errors.New("account has been deleted")

	// 权限错误
	ErrUnauthorized        = errors.New("unauthorized access")
	ErrForbidden           = errors.New("forbidden operation")
)

// DomainError 领域错误包装
type DomainError struct {
	Code    string
	Message string
	Err     error
}

func (e *DomainError) Error() string {
	if e.Err != nil {
		return fmt.Sprintf("%s: %s - %v", e.Code, e.Message, e.Err)
	}
	return fmt.Sprintf("%s: %s", e.Code, e.Message)
}

func (e *DomainError) Unwrap() error {
	return e.Err
}

// NewDomainError 创建领域错误
func NewDomainError(code, message string, err error) *DomainError {
	return &DomainError{
		Code:    code,
		Message: message,
		Err:     err,
	}
}
```

---

## 5. Repository 层

### 5.1 Repository 接口定义

```go
// internal/account/repository/interface.go
package repository

import (
	"context"

	"github.com/isa-cloud/isa_cloud/internal/account/domain"
)

// AccountRepository 账户数据访问接口
// 接口定义在 repository 包中，实现也在同一包中
type AccountRepository interface {
	// CRUD Operations
	Create(ctx context.Context, account *domain.Account) error
	GetByID(ctx context.Context, userID string) (*domain.Account, error)
	GetByEmail(ctx context.Context, email string) (*domain.Account, error)
	Update(ctx context.Context, account *domain.Account) error
	Delete(ctx context.Context, userID string) error

	// Query Operations
	List(ctx context.Context, params ListParams) ([]*domain.Account, error)
	Search(ctx context.Context, query string, limit int) ([]*domain.Account, error)
	Count(ctx context.Context, filter CountFilter) (int64, error)

	// Existence Check
	Exists(ctx context.Context, userID string) (bool, error)
	ExistsByEmail(ctx context.Context, email string) (bool, error)
}

// ListParams 列表查询参数
type ListParams struct {
	Offset             int
	Limit              int
	IsActive           *bool
	SubscriptionStatus *domain.SubscriptionStatus
	SortBy             string
	SortDesc           bool
}

// CountFilter 计数过滤器
type CountFilter struct {
	IsActive           *bool
	SubscriptionStatus *domain.SubscriptionStatus
}
```

### 5.2 PostgreSQL Repository 实现

```go
// internal/account/repository/postgres.go
package repository

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/isa-cloud/isa_cloud/internal/account/domain"
)

// PostgresAccountRepository PostgreSQL 实现
type PostgresAccountRepository struct {
	pool      *pgxpool.Pool
	tableName string
}

// NewPostgresAccountRepository 创建 PostgreSQL Repository
func NewPostgresAccountRepository(pool *pgxpool.Pool) *PostgresAccountRepository {
	return &PostgresAccountRepository{
		pool:      pool,
		tableName: "accounts",
	}
}

// Compile-time interface implementation check
var _ AccountRepository = (*PostgresAccountRepository)(nil)

// ============================================
// CRUD Operations
// ============================================

func (r *PostgresAccountRepository) Create(ctx context.Context, account *domain.Account) error {
	query := `
		INSERT INTO accounts (
			user_id, email, name, subscription_status,
			is_active, preferences, created_at, updated_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
	`

	prefsJSON, err := json.Marshal(account.Preferences)
	if err != nil {
		return fmt.Errorf("failed to marshal preferences: %w", err)
	}

	_, err = r.pool.Exec(ctx, query,
		account.UserID,
		account.Email.String(),
		account.Name,
		account.SubscriptionStatus.String(),
		account.IsActive,
		prefsJSON,
		account.CreatedAt,
		account.UpdatedAt,
	)

	if err != nil {
		if strings.Contains(err.Error(), "duplicate key") {
			return domain.ErrAccountAlreadyExists
		}
		return fmt.Errorf("failed to create account: %w", err)
	}

	return nil
}

func (r *PostgresAccountRepository) GetByID(ctx context.Context, userID string) (*domain.Account, error) {
	query := `
		SELECT user_id, email, name, subscription_status,
		       is_active, preferences, created_at, updated_at
		FROM accounts
		WHERE user_id = $1 AND deleted_at IS NULL
	`

	return r.scanAccount(r.pool.QueryRow(ctx, query, userID))
}

func (r *PostgresAccountRepository) GetByEmail(ctx context.Context, email string) (*domain.Account, error) {
	query := `
		SELECT user_id, email, name, subscription_status,
		       is_active, preferences, created_at, updated_at
		FROM accounts
		WHERE email = $1 AND deleted_at IS NULL
	`

	return r.scanAccount(r.pool.QueryRow(ctx, query, strings.ToLower(email)))
}

func (r *PostgresAccountRepository) Update(ctx context.Context, account *domain.Account) error {
	query := `
		UPDATE accounts SET
			email = $2,
			name = $3,
			subscription_status = $4,
			is_active = $5,
			preferences = $6,
			updated_at = $7
		WHERE user_id = $1 AND deleted_at IS NULL
	`

	prefsJSON, err := json.Marshal(account.Preferences)
	if err != nil {
		return fmt.Errorf("failed to marshal preferences: %w", err)
	}

	result, err := r.pool.Exec(ctx, query,
		account.UserID,
		account.Email.String(),
		account.Name,
		account.SubscriptionStatus.String(),
		account.IsActive,
		prefsJSON,
		time.Now().UTC(),
	)

	if err != nil {
		return fmt.Errorf("failed to update account: %w", err)
	}

	if result.RowsAffected() == 0 {
		return domain.ErrAccountNotFound
	}

	return nil
}

func (r *PostgresAccountRepository) Delete(ctx context.Context, userID string) error {
	// Soft delete
	query := `
		UPDATE accounts SET
			deleted_at = $2,
			is_active = false
		WHERE user_id = $1 AND deleted_at IS NULL
	`

	result, err := r.pool.Exec(ctx, query, userID, time.Now().UTC())
	if err != nil {
		return fmt.Errorf("failed to delete account: %w", err)
	}

	if result.RowsAffected() == 0 {
		return domain.ErrAccountNotFound
	}

	return nil
}

// ============================================
// Query Operations
// ============================================

func (r *PostgresAccountRepository) List(ctx context.Context, params ListParams) ([]*domain.Account, error) {
	var conditions []string
	var args []interface{}
	argIndex := 1

	conditions = append(conditions, "deleted_at IS NULL")

	if params.IsActive != nil {
		conditions = append(conditions, fmt.Sprintf("is_active = $%d", argIndex))
		args = append(args, *params.IsActive)
		argIndex++
	}

	if params.SubscriptionStatus != nil {
		conditions = append(conditions, fmt.Sprintf("subscription_status = $%d", argIndex))
		args = append(args, params.SubscriptionStatus.String())
		argIndex++
	}

	whereClause := strings.Join(conditions, " AND ")

	// Sort
	orderBy := "created_at"
	if params.SortBy != "" {
		orderBy = params.SortBy
	}
	orderDir := "ASC"
	if params.SortDesc {
		orderDir = "DESC"
	}

	query := fmt.Sprintf(`
		SELECT user_id, email, name, subscription_status,
		       is_active, preferences, created_at, updated_at
		FROM accounts
		WHERE %s
		ORDER BY %s %s
		LIMIT $%d OFFSET $%d
	`, whereClause, orderBy, orderDir, argIndex, argIndex+1)

	args = append(args, params.Limit, params.Offset)

	rows, err := r.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to list accounts: %w", err)
	}
	defer rows.Close()

	return r.scanAccounts(rows)
}

func (r *PostgresAccountRepository) Search(ctx context.Context, query string, limit int) ([]*domain.Account, error) {
	sql := `
		SELECT user_id, email, name, subscription_status,
		       is_active, preferences, created_at, updated_at
		FROM accounts
		WHERE deleted_at IS NULL
		  AND (name ILIKE $1 OR email ILIKE $1)
		ORDER BY name
		LIMIT $2
	`

	searchPattern := "%" + query + "%"
	rows, err := r.pool.Query(ctx, sql, searchPattern, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to search accounts: %w", err)
	}
	defer rows.Close()

	return r.scanAccounts(rows)
}

func (r *PostgresAccountRepository) Count(ctx context.Context, filter CountFilter) (int64, error) {
	var conditions []string
	var args []interface{}
	argIndex := 1

	conditions = append(conditions, "deleted_at IS NULL")

	if filter.IsActive != nil {
		conditions = append(conditions, fmt.Sprintf("is_active = $%d", argIndex))
		args = append(args, *filter.IsActive)
		argIndex++
	}

	if filter.SubscriptionStatus != nil {
		conditions = append(conditions, fmt.Sprintf("subscription_status = $%d", argIndex))
		args = append(args, filter.SubscriptionStatus.String())
		argIndex++
	}

	whereClause := strings.Join(conditions, " AND ")
	query := fmt.Sprintf("SELECT COUNT(*) FROM accounts WHERE %s", whereClause)

	var count int64
	err := r.pool.QueryRow(ctx, query, args...).Scan(&count)
	if err != nil {
		return 0, fmt.Errorf("failed to count accounts: %w", err)
	}

	return count, nil
}

// ============================================
// Existence Check
// ============================================

func (r *PostgresAccountRepository) Exists(ctx context.Context, userID string) (bool, error) {
	query := "SELECT EXISTS(SELECT 1 FROM accounts WHERE user_id = $1 AND deleted_at IS NULL)"
	var exists bool
	err := r.pool.QueryRow(ctx, query, userID).Scan(&exists)
	return exists, err
}

func (r *PostgresAccountRepository) ExistsByEmail(ctx context.Context, email string) (bool, error) {
	query := "SELECT EXISTS(SELECT 1 FROM accounts WHERE email = $1 AND deleted_at IS NULL)"
	var exists bool
	err := r.pool.QueryRow(ctx, query, strings.ToLower(email)).Scan(&exists)
	return exists, err
}

// ============================================
// Helper Methods
// ============================================

func (r *PostgresAccountRepository) scanAccount(row pgx.Row) (*domain.Account, error) {
	var (
		userID             string
		email              string
		name               string
		subscriptionStatus string
		isActive           bool
		prefsJSON          []byte
		createdAt          time.Time
		updatedAt          time.Time
	)

	err := row.Scan(
		&userID, &email, &name, &subscriptionStatus,
		&isActive, &prefsJSON, &createdAt, &updatedAt,
	)

	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, domain.ErrAccountNotFound
		}
		return nil, fmt.Errorf("failed to scan account: %w", err)
	}

	var prefs domain.Preferences
	if len(prefsJSON) > 0 {
		if err := json.Unmarshal(prefsJSON, &prefs); err != nil {
			prefs = domain.DefaultPreferences()
		}
	}

	emailVO, _ := domain.NewEmail(email)

	return &domain.Account{
		UserID:             userID,
		Email:              emailVO,
		Name:               name,
		SubscriptionStatus: domain.ParseSubscriptionStatus(subscriptionStatus),
		IsActive:           isActive,
		Preferences:        prefs,
		CreatedAt:          createdAt,
		UpdatedAt:          updatedAt,
	}, nil
}

func (r *PostgresAccountRepository) scanAccounts(rows pgx.Rows) ([]*domain.Account, error) {
	var accounts []*domain.Account

	for rows.Next() {
		var (
			userID             string
			email              string
			name               string
			subscriptionStatus string
			isActive           bool
			prefsJSON          []byte
			createdAt          time.Time
			updatedAt          time.Time
		)

		err := rows.Scan(
			&userID, &email, &name, &subscriptionStatus,
			&isActive, &prefsJSON, &createdAt, &updatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan account row: %w", err)
		}

		var prefs domain.Preferences
		if len(prefsJSON) > 0 {
			json.Unmarshal(prefsJSON, &prefs)
		}

		emailVO, _ := domain.NewEmail(email)

		accounts = append(accounts, &domain.Account{
			UserID:             userID,
			Email:              emailVO,
			Name:               name,
			SubscriptionStatus: domain.ParseSubscriptionStatus(subscriptionStatus),
			IsActive:           isActive,
			Preferences:        prefs,
			CreatedAt:          createdAt,
			UpdatedAt:          updatedAt,
		})
	}

	return accounts, nil
}
```

---

## 6. Service 层

### 6.1 Service 接口定义

```go
// internal/account/service/interface.go
package service

import (
	"context"

	"github.com/isa-cloud/isa_cloud/internal/account/domain"
)

// AccountService 账户服务接口
type AccountService interface {
	// Account Lifecycle
	EnsureAccount(ctx context.Context, req EnsureAccountRequest) (*AccountResponse, bool, error)
	GetAccount(ctx context.Context, userID string) (*AccountResponse, error)
	UpdateAccount(ctx context.Context, userID string, req UpdateAccountRequest) (*AccountResponse, error)
	DeleteAccount(ctx context.Context, userID string, reason string) error

	// Account Query
	ListAccounts(ctx context.Context, req ListAccountsRequest) (*ListAccountsResponse, error)
	SearchAccounts(ctx context.Context, query string, limit int) ([]*AccountSummary, error)

	// Account Status
	ActivateAccount(ctx context.Context, userID string, reason string) error
	DeactivateAccount(ctx context.Context, userID string, reason string) error

	// Stats
	GetStats(ctx context.Context) (*AccountStats, error)
}
```

### 6.2 DTO 定义

```go
// internal/account/service/dto.go
package service

import (
	"time"

	"github.com/isa-cloud/isa_cloud/internal/account/domain"
)

// ============================================
// Request DTOs
// ============================================

type EnsureAccountRequest struct {
	UserID           string
	Email            string
	Name             string
	SubscriptionPlan domain.SubscriptionStatus
}

type UpdateAccountRequest struct {
	Name        *string
	Email       *string
	Preferences *domain.Preferences
}

type ListAccountsRequest struct {
	Page               int
	PageSize           int
	IsActive           *bool
	SubscriptionStatus *domain.SubscriptionStatus
	SortBy             string
	SortDesc           bool
}

// ============================================
// Response DTOs
// ============================================

type AccountResponse struct {
	UserID             string
	Email              string
	Name               string
	SubscriptionStatus domain.SubscriptionStatus
	IsActive           bool
	Preferences        domain.Preferences
	CreatedAt          time.Time
	UpdatedAt          time.Time
}

type AccountSummary struct {
	UserID             string
	Email              string
	Name               string
	SubscriptionStatus domain.SubscriptionStatus
	IsActive           bool
	CreatedAt          time.Time
}

type ListAccountsResponse struct {
	Accounts   []*AccountSummary
	TotalCount int64
	Page       int
	PageSize   int
	HasNext    bool
}

type AccountStats struct {
	TotalAccounts    int64
	ActiveAccounts   int64
	InactiveAccounts int64
	BySubscription   map[string]int64
}

// ============================================
// Conversion Helpers
// ============================================

func AccountToResponse(account *domain.Account) *AccountResponse {
	return &AccountResponse{
		UserID:             account.UserID,
		Email:              account.Email.String(),
		Name:               account.Name,
		SubscriptionStatus: account.SubscriptionStatus,
		IsActive:           account.IsActive,
		Preferences:        account.Preferences,
		CreatedAt:          account.CreatedAt,
		UpdatedAt:          account.UpdatedAt,
	}
}

func AccountToSummary(account *domain.Account) *AccountSummary {
	return &AccountSummary{
		UserID:             account.UserID,
		Email:              account.Email.String(),
		Name:               account.Name,
		SubscriptionStatus: account.SubscriptionStatus,
		IsActive:           account.IsActive,
		CreatedAt:          account.CreatedAt,
	}
}
```

### 6.3 Service 实现

```go
// internal/account/service/service.go
package service

import (
	"context"
	"errors"
	"log/slog"

	"github.com/isa-cloud/isa_cloud/internal/account/domain"
	"github.com/isa-cloud/isa_cloud/internal/account/event"
	"github.com/isa-cloud/isa_cloud/internal/account/repository"
	"github.com/isa-cloud/isa_cloud/internal/eventbus"
)

// AccountServiceImpl 账户服务实现
type AccountServiceImpl struct {
	repo      repository.AccountRepository
	eventBus  *eventbus.EventBusClient
	publisher *event.AccountEventPublisher
	logger    *slog.Logger
}

// NewAccountService 创建账户服务
// 依赖通过构造函数注入
func NewAccountService(
	repo repository.AccountRepository,
	eventBus *eventbus.EventBusClient,
	logger *slog.Logger,
) *AccountServiceImpl {
	return &AccountServiceImpl{
		repo:      repo,
		eventBus:  eventBus,
		publisher: event.NewAccountEventPublisher(eventBus),
		logger:    logger.With("service", "account"),
	}
}

// Compile-time interface implementation check
var _ AccountService = (*AccountServiceImpl)(nil)

// ============================================
// Account Lifecycle
// ============================================

func (s *AccountServiceImpl) EnsureAccount(ctx context.Context, req EnsureAccountRequest) (*AccountResponse, bool, error) {
	// 验证请求
	if err := s.validateEnsureRequest(req); err != nil {
		return nil, false, err
	}

	// 检查是否已存在
	existing, err := s.repo.GetByID(ctx, req.UserID)
	if err == nil && existing != nil {
		// 账户已存在，返回现有账户
		return AccountToResponse(existing), false, nil
	}
	if err != nil && !errors.Is(err, domain.ErrAccountNotFound) {
		return nil, false, err
	}

	// 创建新账户
	account, err := domain.NewAccount(
		req.UserID,
		req.Email,
		req.Name,
		req.SubscriptionPlan,
	)
	if err != nil {
		return nil, false, err
	}

	if err := s.repo.Create(ctx, account); err != nil {
		return nil, false, err
	}

	// 发布账户创建事件
	if err := s.publisher.PublishAccountCreated(ctx, account); err != nil {
		s.logger.Warn("failed to publish account created event",
			"user_id", account.UserID,
			"error", err,
		)
	}

	s.logger.Info("account created",
		"user_id", account.UserID,
		"email", account.Email.String(),
	)

	return AccountToResponse(account), true, nil
}

func (s *AccountServiceImpl) GetAccount(ctx context.Context, userID string) (*AccountResponse, error) {
	if userID == "" {
		return nil, domain.ErrInvalidUserID
	}

	account, err := s.repo.GetByID(ctx, userID)
	if err != nil {
		return nil, err
	}

	return AccountToResponse(account), nil
}

func (s *AccountServiceImpl) UpdateAccount(ctx context.Context, userID string, req UpdateAccountRequest) (*AccountResponse, error) {
	account, err := s.repo.GetByID(ctx, userID)
	if err != nil {
		return nil, err
	}

	// 更新字段
	var updatedEmail *domain.Email
	if req.Email != nil {
		email, err := domain.NewEmail(*req.Email)
		if err != nil {
			return nil, err
		}
		updatedEmail = &email
	}

	name := ""
	if req.Name != nil {
		name = *req.Name
	}

	if err := account.UpdateProfile(name, updatedEmail); err != nil {
		return nil, err
	}

	if req.Preferences != nil {
		account.Preferences = *req.Preferences
	}

	if err := s.repo.Update(ctx, account); err != nil {
		return nil, err
	}

	// 发布账户更新事件
	if err := s.publisher.PublishAccountUpdated(ctx, account); err != nil {
		s.logger.Warn("failed to publish account updated event",
			"user_id", account.UserID,
			"error", err,
		)
	}

	s.logger.Info("account updated", "user_id", account.UserID)

	return AccountToResponse(account), nil
}

func (s *AccountServiceImpl) DeleteAccount(ctx context.Context, userID string, reason string) error {
	account, err := s.repo.GetByID(ctx, userID)
	if err != nil {
		return err
	}

	if err := s.repo.Delete(ctx, userID); err != nil {
		return err
	}

	// 发布账户删除事件
	if err := s.publisher.PublishAccountDeleted(ctx, account, reason); err != nil {
		s.logger.Warn("failed to publish account deleted event",
			"user_id", userID,
			"error", err,
		)
	}

	s.logger.Info("account deleted",
		"user_id", userID,
		"reason", reason,
	)

	return nil
}

// ============================================
// Account Query
// ============================================

func (s *AccountServiceImpl) ListAccounts(ctx context.Context, req ListAccountsRequest) (*ListAccountsResponse, error) {
	// 设置默认值
	if req.Page < 1 {
		req.Page = 1
	}
	if req.PageSize < 1 {
		req.PageSize = 20
	}
	if req.PageSize > 100 {
		req.PageSize = 100
	}

	params := repository.ListParams{
		Offset:             (req.Page - 1) * req.PageSize,
		Limit:              req.PageSize + 1, // 多查一条判断 HasNext
		IsActive:           req.IsActive,
		SubscriptionStatus: req.SubscriptionStatus,
		SortBy:             req.SortBy,
		SortDesc:           req.SortDesc,
	}

	accounts, err := s.repo.List(ctx, params)
	if err != nil {
		return nil, err
	}

	hasNext := len(accounts) > req.PageSize
	if hasNext {
		accounts = accounts[:req.PageSize]
	}

	totalCount, err := s.repo.Count(ctx, repository.CountFilter{
		IsActive:           req.IsActive,
		SubscriptionStatus: req.SubscriptionStatus,
	})
	if err != nil {
		s.logger.Warn("failed to get total count", "error", err)
		totalCount = int64(len(accounts))
	}

	summaries := make([]*AccountSummary, len(accounts))
	for i, acc := range accounts {
		summaries[i] = AccountToSummary(acc)
	}

	return &ListAccountsResponse{
		Accounts:   summaries,
		TotalCount: totalCount,
		Page:       req.Page,
		PageSize:   req.PageSize,
		HasNext:    hasNext,
	}, nil
}

func (s *AccountServiceImpl) SearchAccounts(ctx context.Context, query string, limit int) ([]*AccountSummary, error) {
	if limit < 1 {
		limit = 10
	}
	if limit > 50 {
		limit = 50
	}

	accounts, err := s.repo.Search(ctx, query, limit)
	if err != nil {
		return nil, err
	}

	summaries := make([]*AccountSummary, len(accounts))
	for i, acc := range accounts {
		summaries[i] = AccountToSummary(acc)
	}

	return summaries, nil
}

// ============================================
// Account Status
// ============================================

func (s *AccountServiceImpl) ActivateAccount(ctx context.Context, userID string, reason string) error {
	account, err := s.repo.GetByID(ctx, userID)
	if err != nil {
		return err
	}

	account.Activate()

	if err := s.repo.Update(ctx, account); err != nil {
		return err
	}

	// 发布状态变更事件
	if err := s.publisher.PublishAccountStatusChanged(ctx, account, true, reason); err != nil {
		s.logger.Warn("failed to publish status changed event",
			"user_id", userID,
			"error", err,
		)
	}

	s.logger.Info("account activated",
		"user_id", userID,
		"reason", reason,
	)

	return nil
}

func (s *AccountServiceImpl) DeactivateAccount(ctx context.Context, userID string, reason string) error {
	account, err := s.repo.GetByID(ctx, userID)
	if err != nil {
		return err
	}

	account.Deactivate()

	if err := s.repo.Update(ctx, account); err != nil {
		return err
	}

	// 发布状态变更事件
	if err := s.publisher.PublishAccountStatusChanged(ctx, account, false, reason); err != nil {
		s.logger.Warn("failed to publish status changed event",
			"user_id", userID,
			"error", err,
		)
	}

	s.logger.Info("account deactivated",
		"user_id", userID,
		"reason", reason,
	)

	return nil
}

// ============================================
// Stats
// ============================================

func (s *AccountServiceImpl) GetStats(ctx context.Context) (*AccountStats, error) {
	total, err := s.repo.Count(ctx, repository.CountFilter{})
	if err != nil {
		return nil, err
	}

	active := true
	activeCount, err := s.repo.Count(ctx, repository.CountFilter{IsActive: &active})
	if err != nil {
		return nil, err
	}

	return &AccountStats{
		TotalAccounts:    total,
		ActiveAccounts:   activeCount,
		InactiveAccounts: total - activeCount,
		BySubscription:   make(map[string]int64), // TODO: 实现按订阅统计
	}, nil
}

// ============================================
// Validation Helpers
// ============================================

func (s *AccountServiceImpl) validateEnsureRequest(req EnsureAccountRequest) error {
	if req.UserID == "" {
		return domain.ErrInvalidUserID
	}
	if req.Email == "" {
		return domain.ErrInvalidEmail
	}
	if req.Name == "" {
		return domain.ErrInvalidName
	}
	return nil
}
```

---

## 7. gRPC Handler 层

### 7.1 gRPC Handler 实现

```go
// internal/account/handler/grpc_handler.go
package handler

import (
	"context"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/isa-cloud/isa_cloud/api/proto/account"
	commonpb "github.com/isa-cloud/isa_cloud/api/proto/common"
	"github.com/isa-cloud/isa_cloud/internal/account/domain"
	"github.com/isa-cloud/isa_cloud/internal/account/service"
)

// AccountGRPCHandler gRPC 服务处理器
type AccountGRPCHandler struct {
	pb.UnimplementedAccountServiceServer
	svc service.AccountService
}

// NewAccountGRPCHandler 创建 gRPC Handler
func NewAccountGRPCHandler(svc service.AccountService) *AccountGRPCHandler {
	return &AccountGRPCHandler{
		svc: svc,
	}
}

// ============================================
// Account Lifecycle
// ============================================

func (h *AccountGRPCHandler) EnsureAccount(ctx context.Context, req *pb.EnsureAccountRequest) (*pb.EnsureAccountResponse, error) {
	serviceReq := service.EnsureAccountRequest{
		UserID:           req.UserId,
		Email:            req.Email,
		Name:             req.Name,
		SubscriptionPlan: protoToSubscriptionStatus(req.SubscriptionPlan),
	}

	account, wasCreated, err := h.svc.EnsureAccount(ctx, serviceReq)
	if err != nil {
		return nil, h.handleError(err)
	}

	return &pb.EnsureAccountResponse{
		Metadata:   h.successMetadata(),
		Account:    accountToProto(account),
		WasCreated: wasCreated,
	}, nil
}

func (h *AccountGRPCHandler) GetAccount(ctx context.Context, req *pb.GetAccountRequest) (*pb.GetAccountResponse, error) {
	account, err := h.svc.GetAccount(ctx, req.UserId)
	if err != nil {
		return nil, h.handleError(err)
	}

	return &pb.GetAccountResponse{
		Metadata: h.successMetadata(),
		Account:  accountToProto(account),
	}, nil
}

func (h *AccountGRPCHandler) UpdateAccount(ctx context.Context, req *pb.UpdateAccountRequest) (*pb.UpdateAccountResponse, error) {
	serviceReq := service.UpdateAccountRequest{}

	if req.Name != nil {
		serviceReq.Name = &req.Name.Value
	}
	if req.Email != nil {
		serviceReq.Email = &req.Email.Value
	}
	if req.Preferences != nil {
		prefs := protoToPreferences(req.Preferences)
		serviceReq.Preferences = &prefs
	}

	account, err := h.svc.UpdateAccount(ctx, req.UserId, serviceReq)
	if err != nil {
		return nil, h.handleError(err)
	}

	return &pb.UpdateAccountResponse{
		Metadata: h.successMetadata(),
		Account:  accountToProto(account),
	}, nil
}

func (h *AccountGRPCHandler) DeleteAccount(ctx context.Context, req *pb.DeleteAccountRequest) (*pb.DeleteAccountResponse, error) {
	err := h.svc.DeleteAccount(ctx, req.UserId, req.Reason)
	if err != nil {
		return nil, h.handleError(err)
	}

	return &pb.DeleteAccountResponse{
		Metadata: h.successMetadata(),
		Success:  true,
	}, nil
}

// ============================================
// Account Query
// ============================================

func (h *AccountGRPCHandler) ListAccounts(ctx context.Context, req *pb.ListAccountsRequest) (*pb.ListAccountsResponse, error) {
	serviceReq := service.ListAccountsRequest{
		Page:     int(req.Page),
		PageSize: int(req.PageSize),
	}

	if req.IsActive != nil {
		isActive := req.IsActive.Value
		serviceReq.IsActive = &isActive
	}

	if req.SubscriptionStatus != pb.SubscriptionStatus_SUBSCRIPTION_STATUS_UNSPECIFIED {
		status := protoToSubscriptionStatus(req.SubscriptionStatus)
		serviceReq.SubscriptionStatus = &status
	}

	result, err := h.svc.ListAccounts(ctx, serviceReq)
	if err != nil {
		return nil, h.handleError(err)
	}

	accounts := make([]*pb.AccountSummary, len(result.Accounts))
	for i, acc := range result.Accounts {
		accounts[i] = accountSummaryToProto(acc)
	}

	return &pb.ListAccountsResponse{
		Metadata: h.successMetadata(),
		Accounts: accounts,
		Pagination: &commonpb.PaginationResponse{
			Page:       int32(result.Page),
			PageSize:   int32(result.PageSize),
			TotalCount: result.TotalCount,
			HasNext:    result.HasNext,
		},
	}, nil
}

func (h *AccountGRPCHandler) SearchAccounts(ctx context.Context, req *pb.SearchAccountsRequest) (*pb.SearchAccountsResponse, error) {
	accounts, err := h.svc.SearchAccounts(ctx, req.Query, int(req.Limit))
	if err != nil {
		return nil, h.handleError(err)
	}

	results := make([]*pb.AccountSummary, len(accounts))
	for i, acc := range accounts {
		results[i] = accountSummaryToProto(acc)
	}

	return &pb.SearchAccountsResponse{
		Metadata: h.successMetadata(),
		Accounts: results,
	}, nil
}

// ============================================
// Account Status
// ============================================

func (h *AccountGRPCHandler) ChangeAccountStatus(ctx context.Context, req *pb.ChangeAccountStatusRequest) (*pb.ChangeAccountStatusResponse, error) {
	var err error
	if req.IsActive {
		err = h.svc.ActivateAccount(ctx, req.UserId, req.Reason)
	} else {
		err = h.svc.DeactivateAccount(ctx, req.UserId, req.Reason)
	}

	if err != nil {
		return nil, h.handleError(err)
	}

	return &pb.ChangeAccountStatusResponse{
		Metadata: h.successMetadata(),
		Success:  true,
	}, nil
}

// ============================================
// Health Check
// ============================================

func (h *AccountGRPCHandler) HealthCheck(ctx context.Context, req *pb.HealthCheckRequest) (*pb.HealthCheckResponse, error) {
	stats, err := h.svc.GetStats(ctx)
	if err != nil {
		return &pb.HealthCheckResponse{
			Healthy: false,
			Status:  "unhealthy",
		}, nil
	}

	return &pb.HealthCheckResponse{
		Healthy: true,
		Status:  "healthy",
		Details: map[string]string{
			"total_accounts":  fmt.Sprintf("%d", stats.TotalAccounts),
			"active_accounts": fmt.Sprintf("%d", stats.ActiveAccounts),
		},
	}, nil
}

// ============================================
// Error Handling
// ============================================

func (h *AccountGRPCHandler) handleError(err error) error {
	switch {
	case errors.Is(err, domain.ErrAccountNotFound):
		return status.Error(codes.NotFound, err.Error())
	case errors.Is(err, domain.ErrAccountAlreadyExists):
		return status.Error(codes.AlreadyExists, err.Error())
	case errors.Is(err, domain.ErrInvalidEmail),
		errors.Is(err, domain.ErrInvalidUserID),
		errors.Is(err, domain.ErrInvalidName):
		return status.Error(codes.InvalidArgument, err.Error())
	case errors.Is(err, domain.ErrUnauthorized):
		return status.Error(codes.Unauthenticated, err.Error())
	case errors.Is(err, domain.ErrForbidden):
		return status.Error(codes.PermissionDenied, err.Error())
	default:
		return status.Error(codes.Internal, "internal server error")
	}
}

func (h *AccountGRPCHandler) successMetadata() *commonpb.ResponseMetadata {
	return &commonpb.ResponseMetadata{
		Success:   true,
		Timestamp: timestamppb.Now(),
	}
}
```

### 7.2 Proto 转换器

```go
// internal/account/handler/converter.go
package handler

import (
	"google.golang.org/protobuf/types/known/structpb"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/isa-cloud/isa_cloud/api/proto/account"
	"github.com/isa-cloud/isa_cloud/internal/account/domain"
	"github.com/isa-cloud/isa_cloud/internal/account/service"
)

// ============================================
// Domain -> Proto Converters
// ============================================

func accountToProto(acc *service.AccountResponse) *pb.AccountProfile {
	prefs, _ := structpb.NewStruct(acc.Preferences.ToMap())

	return &pb.AccountProfile{
		UserId:             acc.UserID,
		Email:              acc.Email,
		Name:               acc.Name,
		SubscriptionStatus: subscriptionStatusToProto(acc.SubscriptionStatus),
		IsActive:           acc.IsActive,
		Preferences:        prefs,
		CreatedAt:          timestamppb.New(acc.CreatedAt),
		UpdatedAt:          timestamppb.New(acc.UpdatedAt),
	}
}

func accountSummaryToProto(acc *service.AccountSummary) *pb.AccountSummary {
	return &pb.AccountSummary{
		UserId:             acc.UserID,
		Email:              acc.Email,
		Name:               acc.Name,
		SubscriptionStatus: subscriptionStatusToProto(acc.SubscriptionStatus),
		IsActive:           acc.IsActive,
		CreatedAt:          timestamppb.New(acc.CreatedAt),
	}
}

func subscriptionStatusToProto(status domain.SubscriptionStatus) pb.SubscriptionStatus {
	switch status {
	case domain.SubscriptionStatusFree:
		return pb.SubscriptionStatus_SUBSCRIPTION_STATUS_FREE
	case domain.SubscriptionStatusBasic:
		return pb.SubscriptionStatus_SUBSCRIPTION_STATUS_BASIC
	case domain.SubscriptionStatusPremium:
		return pb.SubscriptionStatus_SUBSCRIPTION_STATUS_PREMIUM
	case domain.SubscriptionStatusEnterprise:
		return pb.SubscriptionStatus_SUBSCRIPTION_STATUS_ENTERPRISE
	default:
		return pb.SubscriptionStatus_SUBSCRIPTION_STATUS_UNSPECIFIED
	}
}

// ============================================
// Proto -> Domain Converters
// ============================================

func protoToSubscriptionStatus(status pb.SubscriptionStatus) domain.SubscriptionStatus {
	switch status {
	case pb.SubscriptionStatus_SUBSCRIPTION_STATUS_FREE:
		return domain.SubscriptionStatusFree
	case pb.SubscriptionStatus_SUBSCRIPTION_STATUS_BASIC:
		return domain.SubscriptionStatusBasic
	case pb.SubscriptionStatus_SUBSCRIPTION_STATUS_PREMIUM:
		return domain.SubscriptionStatusPremium
	case pb.SubscriptionStatus_SUBSCRIPTION_STATUS_ENTERPRISE:
		return domain.SubscriptionStatusEnterprise
	default:
		return domain.SubscriptionStatusUnspecified
	}
}

func protoToPreferences(prefs *structpb.Struct) domain.Preferences {
	if prefs == nil {
		return domain.DefaultPreferences()
	}

	result := domain.DefaultPreferences()
	fields := prefs.GetFields()

	if v, ok := fields["timezone"]; ok {
		result.Timezone = v.GetStringValue()
	}
	if v, ok := fields["language"]; ok {
		result.Language = v.GetStringValue()
	}
	if v, ok := fields["theme"]; ok {
		result.Theme = v.GetStringValue()
	}
	if v, ok := fields["notification_email"]; ok {
		result.NotificationEmail = v.GetBoolValue()
	}
	if v, ok := fields["notification_push"]; ok {
		result.NotificationPush = v.GetBoolValue()
	}

	return result
}
```

---

## 8. 依赖注入

### 8.1 构造函数注入模式

我们使用简单的构造函数注入，不需要额外的 DI 框架：

```go
// cmd/account-service/main.go
package main

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"os"
	"os/signal"
	"syscall"

	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"

	pb "github.com/isa-cloud/isa_cloud/api/proto/account"
	"github.com/isa-cloud/isa_cloud/internal/account/handler"
	"github.com/isa-cloud/isa_cloud/internal/account/repository"
	"github.com/isa-cloud/isa_cloud/internal/account/service"
	"github.com/isa-cloud/isa_cloud/internal/eventbus"
	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/database/postgres"
)

const serviceName = "account-service"

func main() {
	// 初始化 Logger
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))

	ctx := context.Background()

	// ============================================
	// 1. 初始化基础设施 (最外层)
	// ============================================

	// PostgreSQL
	pgConfig := &postgres.Config{
		Host:     getEnv("POSTGRES_HOST", "localhost"),
		Port:     getEnvInt("POSTGRES_PORT", 5432),
		Database: getEnv("POSTGRES_DB", "isa_cloud"),
		User:     getEnv("POSTGRES_USER", "postgres"),
		Password: getEnv("POSTGRES_PASSWORD", "postgres"),
	}
	pgClient, err := postgres.NewClient(ctx, pgConfig)
	if err != nil {
		logger.Error("failed to connect to postgres", "error", err)
		os.Exit(1)
	}
	defer pgClient.Close()

	// EventBus (NATS)
	eventBus, err := eventbus.NewEventBusClient(&eventbus.Config{
		NATSUrl:  getEnv("NATS_URL", "nats://localhost:4222"),
		ClientID: serviceName,
	})
	if err != nil {
		logger.Error("failed to connect to NATS", "error", err)
		os.Exit(1)
	}
	defer eventBus.Close()

	// ============================================
	// 2. 依赖注入 (从内到外构建)
	// ============================================

	// Repository Layer
	accountRepo := repository.NewPostgresAccountRepository(pgClient.GetPool())

	// Service Layer
	accountService := service.NewAccountService(
		accountRepo,
		eventBus,
		logger,
	)

	// Handler Layer (gRPC)
	accountHandler := handler.NewAccountGRPCHandler(accountService)

	// ============================================
	// 3. 启动 gRPC 服务器
	// ============================================

	grpcServer := grpc.NewServer(
		grpc.MaxRecvMsgSize(50*1024*1024),
		grpc.MaxSendMsgSize(50*1024*1024),
	)

	pb.RegisterAccountServiceServer(grpcServer, accountHandler)

	// Health Check
	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus(serviceName, grpc_health_v1.HealthCheckResponse_SERVING)

	// Reflection
	reflection.Register(grpcServer)

	// Listen
	port := getEnvInt("GRPC_PORT", 50051)
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", port))
	if err != nil {
		logger.Error("failed to listen", "port", port, "error", err)
		os.Exit(1)
	}

	logger.Info("starting gRPC server", "port", port, "service", serviceName)

	// Graceful shutdown
	go gracefulShutdown(grpcServer, logger)

	if err := grpcServer.Serve(lis); err != nil {
		logger.Error("failed to serve", "error", err)
		os.Exit(1)
	}
}

func gracefulShutdown(server *grpc.Server, logger *slog.Logger) {
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh

	logger.Info("shutting down gracefully...")
	server.GracefulStop()
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func getEnvInt(key string, defaultValue int) int {
	if value := os.Getenv(key); value != "" {
		var intValue int
		fmt.Sscanf(value, "%d", &intValue)
		if intValue > 0 {
			return intValue
		}
	}
	return defaultValue
}
```

### 8.2 依赖关系图

```
main.go
    │
    ├── Infrastructure Layer (基础设施)
    │   ├── postgres.Client
    │   ├── eventbus.EventBusClient
    │   └── slog.Logger
    │
    ├── Repository Layer (数据访问)
    │   └── repository.PostgresAccountRepository
    │       └── depends on: postgres.Client
    │
    ├── Service Layer (业务逻辑)
    │   └── service.AccountServiceImpl
    │       ├── depends on: repository.AccountRepository (interface)
    │       ├── depends on: eventbus.EventBusClient
    │       └── depends on: slog.Logger
    │
    └── Handler Layer (传输层)
        └── handler.AccountGRPCHandler
            └── depends on: service.AccountService (interface)
```

---

## 9. 服务间同步通信

### 9.1 gRPC 客户端封装

```go
// internal/account/client/auth_client.go
package client

import (
	"context"
	"fmt"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	authpb "github.com/isa-cloud/isa_cloud/api/proto/auth"
)

// AuthClient Auth 服务客户端
type AuthClient struct {
	conn   *grpc.ClientConn
	client authpb.AuthServiceClient
}

// AuthClientConfig 客户端配置
type AuthClientConfig struct {
	Address     string
	Timeout     time.Duration
	MaxRetries  int
}

// NewAuthClient 创建 Auth 服务客户端
func NewAuthClient(cfg AuthClientConfig) (*AuthClient, error) {
	if cfg.Timeout == 0 {
		cfg.Timeout = 10 * time.Second
	}

	conn, err := grpc.Dial(
		cfg.Address,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithDefaultCallOptions(
			grpc.MaxCallRecvMsgSize(10*1024*1024),
		),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to auth service: %w", err)
	}

	return &AuthClient{
		conn:   conn,
		client: authpb.NewAuthServiceClient(conn),
	}, nil
}

// Close 关闭连接
func (c *AuthClient) Close() error {
	return c.conn.Close()
}

// VerifyToken 验证 Token
func (c *AuthClient) VerifyToken(ctx context.Context, token string) (*authpb.VerifyTokenResponse, error) {
	return c.client.VerifyToken(ctx, &authpb.VerifyTokenRequest{
		Token: token,
	})
}

// GetUserInfo 获取用户信息
func (c *AuthClient) GetUserInfo(ctx context.Context, token string) (*authpb.GetUserInfoResponse, error) {
	return c.client.GetUserInfo(ctx, &authpb.GetUserInfoRequest{
		Token: token,
	})
}
```

### 9.2 使用服务发现

```go
// pkg/grpc/resolver.go
package grpc

import (
	"fmt"

	consulapi "github.com/hashicorp/consul/api"
	"google.golang.org/grpc"
	"google.golang.org/grpc/resolver"
)

// ConsulResolver Consul 服务发现解析器
type ConsulResolver struct {
	consulClient *consulapi.Client
}

// NewConsulDialer 创建 Consul 感知的 gRPC Dialer
func NewConsulDialer(consulAddr string) (*ConsulResolver, error) {
	config := consulapi.DefaultConfig()
	config.Address = consulAddr

	client, err := consulapi.NewClient(config)
	if err != nil {
		return nil, err
	}

	return &ConsulResolver{consulClient: client}, nil
}

// DialService 通过服务名连接
func (r *ConsulResolver) DialService(serviceName string, opts ...grpc.DialOption) (*grpc.ClientConn, error) {
	// 从 Consul 获取服务地址
	services, _, err := r.consulClient.Health().Service(serviceName, "", true, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to get service from consul: %w", err)
	}

	if len(services) == 0 {
		return nil, fmt.Errorf("no healthy instances of %s found", serviceName)
	}

	// 使用第一个健康实例 (生产环境应该用负载均衡)
	svc := services[0]
	addr := fmt.Sprintf("%s:%d", svc.Service.Address, svc.Service.Port)

	return grpc.Dial(addr, opts...)
}
```

---

## 10. 异步事件机制

### 10.1 事件类型定义

```go
// internal/account/event/events.go
package event

// 账户服务事件类型
const (
	// 账户生命周期事件
	EventAccountCreated       = "account.created"
	EventAccountUpdated       = "account.updated"
	EventAccountDeleted       = "account.deleted"
	EventAccountStatusChanged = "account.status_changed"

	// 订阅相关事件
	EventSubscriptionUpgraded   = "account.subscription.upgraded"
	EventSubscriptionDowngraded = "account.subscription.downgraded"
)

// 事件源标识
const SourceAccountService = "account_service"
```

### 10.2 事件发布器

```go
// internal/account/event/publisher.go
package event

import (
	"context"
	"time"

	"github.com/isa-cloud/isa_cloud/internal/account/domain"
	"github.com/isa-cloud/isa_cloud/internal/eventbus"
)

// AccountEventPublisher 账户事件发布器
type AccountEventPublisher struct {
	eventBus *eventbus.EventBusClient
}

// NewAccountEventPublisher 创建事件发布器
func NewAccountEventPublisher(eventBus *eventbus.EventBusClient) *AccountEventPublisher {
	return &AccountEventPublisher{
		eventBus: eventBus,
	}
}

// PublishAccountCreated 发布账户创建事件
func (p *AccountEventPublisher) PublishAccountCreated(ctx context.Context, account *domain.Account) error {
	if p.eventBus == nil {
		return nil
	}

	event := eventbus.Event{
		Type:      EventAccountCreated,
		Source:   SourceAccountService,
		Subject:  account.UserID,
		Timestamp: time.Now().UTC(),
		Data: map[string]interface{}{
			"user_id":             account.UserID,
			"email":               account.Email.String(),
			"name":                account.Name,
			"subscription_status": account.SubscriptionStatus.String(),
			"is_active":           account.IsActive,
			"created_at":          account.CreatedAt.Format(time.RFC3339),
		},
		Metadata: map[string]string{
			"event_version": "1.0",
		},
	}

	return p.eventBus.PublishEvent(ctx, event)
}

// PublishAccountUpdated 发布账户更新事件
func (p *AccountEventPublisher) PublishAccountUpdated(ctx context.Context, account *domain.Account) error {
	if p.eventBus == nil {
		return nil
	}

	event := eventbus.Event{
		Type:      EventAccountUpdated,
		Source:   SourceAccountService,
		Subject:  account.UserID,
		Timestamp: time.Now().UTC(),
		Data: map[string]interface{}{
			"user_id":    account.UserID,
			"email":      account.Email.String(),
			"name":       account.Name,
			"updated_at": account.UpdatedAt.Format(time.RFC3339),
		},
	}

	return p.eventBus.PublishEvent(ctx, event)
}

// PublishAccountDeleted 发布账户删除事件
func (p *AccountEventPublisher) PublishAccountDeleted(ctx context.Context, account *domain.Account, reason string) error {
	if p.eventBus == nil {
		return nil
	}

	event := eventbus.Event{
		Type:      EventAccountDeleted,
		Source:   SourceAccountService,
		Subject:  account.UserID,
		Timestamp: time.Now().UTC(),
		Data: map[string]interface{}{
			"user_id": account.UserID,
			"email":   account.Email.String(),
			"reason":  reason,
		},
	}

	return p.eventBus.PublishEvent(ctx, event)
}

// PublishAccountStatusChanged 发布状态变更事件
func (p *AccountEventPublisher) PublishAccountStatusChanged(ctx context.Context, account *domain.Account, isActive bool, reason string) error {
	if p.eventBus == nil {
		return nil
	}

	event := eventbus.Event{
		Type:      EventAccountStatusChanged,
		Source:   SourceAccountService,
		Subject:  account.UserID,
		Timestamp: time.Now().UTC(),
		Data: map[string]interface{}{
			"user_id":   account.UserID,
			"email":     account.Email.String(),
			"is_active": isActive,
			"reason":    reason,
		},
	}

	return p.eventBus.PublishEvent(ctx, event)
}
```

### 10.3 事件订阅处理

```go
// internal/account/event/subscriber.go
package event

import (
	"context"
	"log/slog"

	"github.com/isa-cloud/isa_cloud/internal/account/service"
	"github.com/isa-cloud/isa_cloud/internal/eventbus"
)

// AccountEventSubscriber 账户事件订阅器
type AccountEventSubscriber struct {
	eventBus *eventbus.EventBusClient
	svc      service.AccountService
	logger   *slog.Logger
}

// NewAccountEventSubscriber 创建事件订阅器
func NewAccountEventSubscriber(
	eventBus *eventbus.EventBusClient,
	svc service.AccountService,
	logger *slog.Logger,
) *AccountEventSubscriber {
	return &AccountEventSubscriber{
		eventBus: eventBus,
		svc:      svc,
		logger:   logger.With("component", "event_subscriber"),
	}
}

// Start 启动事件订阅
func (s *AccountEventSubscriber) Start(ctx context.Context) error {
	// 订阅用户登录事件 (来自 Auth 服务)
	go s.subscribeToUserLogin(ctx)

	// 订阅支付完成事件 (来自 Payment 服务)
	go s.subscribeToPaymentCompleted(ctx)

	return nil
}

func (s *AccountEventSubscriber) subscribeToUserLogin(ctx context.Context) {
	pattern := "auth_service.user.logged_in"

	err := s.eventBus.SubscribeToEvents(ctx, pattern, func(ctx context.Context, event eventbus.Event) error {
		s.logger.Info("received user login event",
			"event_id", event.ID,
			"user_id", event.Data["user_id"],
		)

		// 处理用户登录事件，例如更新最后登录时间
		userID, ok := event.Data["user_id"].(string)
		if !ok {
			s.logger.Warn("invalid user_id in event", "event_id", event.ID)
			return nil
		}

		// 业务处理逻辑
		_ = userID // TODO: 实现最后登录时间更新

		return nil
	})

	if err != nil {
		s.logger.Error("failed to subscribe to user login events", "error", err)
	}
}

func (s *AccountEventSubscriber) subscribeToPaymentCompleted(ctx context.Context) {
	pattern := "payment_service.payment.completed"

	err := s.eventBus.SubscribeToEvents(ctx, pattern, func(ctx context.Context, event eventbus.Event) error {
		s.logger.Info("received payment completed event",
			"event_id", event.ID,
			"user_id", event.Data["user_id"],
		)

		// 处理支付完成事件，可能需要升级订阅
		// TODO: 实现订阅升级逻辑

		return nil
	})

	if err != nil {
		s.logger.Error("failed to subscribe to payment events", "error", err)
	}
}
```

### 10.4 事件流程图

```
┌─────────────────┐                      ┌─────────────────┐
│  Account        │                      │  NATS           │
│  Service        │                      │  JetStream      │
└────────┬────────┘                      └────────┬────────┘
         │                                        │
         │  PublishEvent(account.created)         │
         │ ─────────────────────────────────────► │
         │                                        │
         │                                        │ ───┐
         │                                        │    │ Store in
         │                                        │    │ EVENTS stream
         │                                        │ ◄──┘
         │                                        │
┌────────┴────────┐                      ┌────────┴────────┐
│  Notification   │ ◄──────────────────  │  Consumer:      │
│  Service        │  SubscribeToEvents   │  notification-  │
└─────────────────┘  (account.>)         │  account.*      │
                                         └─────────────────┘

┌─────────────────┐                      ┌─────────────────┐
│  Audit          │ ◄──────────────────  │  Consumer:      │
│  Service        │  SubscribeToEvents   │  audit-         │
└─────────────────┘  (*.>)               │  all            │
                                         └─────────────────┘
```

---

## 11. 错误处理

### 11.1 错误转换

```go
// pkg/errors/grpc_errors.go
package errors

import (
	"errors"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// ErrorCode 错误码定义
type ErrorCode string

const (
	ErrCodeNotFound        ErrorCode = "NOT_FOUND"
	ErrCodeAlreadyExists   ErrorCode = "ALREADY_EXISTS"
	ErrCodeInvalidArgument ErrorCode = "INVALID_ARGUMENT"
	ErrCodeUnauthorized    ErrorCode = "UNAUTHORIZED"
	ErrCodeForbidden       ErrorCode = "FORBIDDEN"
	ErrCodeInternal        ErrorCode = "INTERNAL"
	ErrCodeUnavailable     ErrorCode = "UNAVAILABLE"
)

// ServiceError 服务错误
type ServiceError struct {
	Code    ErrorCode
	Message string
	Err     error
}

func (e *ServiceError) Error() string {
	if e.Err != nil {
		return e.Message + ": " + e.Err.Error()
	}
	return e.Message
}

func (e *ServiceError) Unwrap() error {
	return e.Err
}

// ToGRPCError 转换为 gRPC 错误
func (e *ServiceError) ToGRPCError() error {
	var code codes.Code
	switch e.Code {
	case ErrCodeNotFound:
		code = codes.NotFound
	case ErrCodeAlreadyExists:
		code = codes.AlreadyExists
	case ErrCodeInvalidArgument:
		code = codes.InvalidArgument
	case ErrCodeUnauthorized:
		code = codes.Unauthenticated
	case ErrCodeForbidden:
		code = codes.PermissionDenied
	case ErrCodeUnavailable:
		code = codes.Unavailable
	default:
		code = codes.Internal
	}
	return status.Error(code, e.Message)
}

// New 创建新错误
func New(code ErrorCode, message string) *ServiceError {
	return &ServiceError{Code: code, Message: message}
}

// Wrap 包装错误
func Wrap(code ErrorCode, message string, err error) *ServiceError {
	return &ServiceError{Code: code, Message: message, Err: err}
}

// IsNotFound 检查是否是 NotFound 错误
func IsNotFound(err error) bool {
	var svcErr *ServiceError
	if errors.As(err, &svcErr) {
		return svcErr.Code == ErrCodeNotFound
	}
	return false
}
```

---

## 12. 配置管理

### 12.1 配置结构

```go
// internal/config/config.go
package config

import (
	"os"
	"strconv"
	"time"
)

// Config 全局配置
type Config struct {
	Service    ServiceConfig
	GRPC       GRPCConfig
	Postgres   PostgresConfig
	Redis      RedisConfig
	NATS       NATSConfig
	Consul     ConsulConfig
	Logging    LoggingConfig
}

type ServiceConfig struct {
	Name        string
	Version     string
	Environment string // development, staging, production
}

type GRPCConfig struct {
	Port           int
	MaxRecvMsgSize int
	MaxSendMsgSize int
}

type PostgresConfig struct {
	Host            string
	Port            int
	Database        string
	User            string
	Password        string
	SSLMode         string
	MaxConns        int
	MinConns        int
	MaxConnLifetime time.Duration
}

type RedisConfig struct {
	Address  string
	Password string
	DB       int
}

type NATSConfig struct {
	URL      string
	Username string
	Password string
}

type ConsulConfig struct {
	Enabled bool
	Address string
}

type LoggingConfig struct {
	Level  string // debug, info, warn, error
	Format string // json, text
}

// Load 从环境变量加载配置
func Load() *Config {
	return &Config{
		Service: ServiceConfig{
			Name:        getEnv("SERVICE_NAME", "unknown-service"),
			Version:     getEnv("SERVICE_VERSION", "0.0.0"),
			Environment: getEnv("ENVIRONMENT", "development"),
		},
		GRPC: GRPCConfig{
			Port:           getEnvInt("GRPC_PORT", 50051),
			MaxRecvMsgSize: getEnvInt("GRPC_MAX_RECV_MSG_SIZE", 50*1024*1024),
			MaxSendMsgSize: getEnvInt("GRPC_MAX_SEND_MSG_SIZE", 50*1024*1024),
		},
		Postgres: PostgresConfig{
			Host:            getEnv("POSTGRES_HOST", "localhost"),
			Port:            getEnvInt("POSTGRES_PORT", 5432),
			Database:        getEnv("POSTGRES_DB", "isa_cloud"),
			User:            getEnv("POSTGRES_USER", "postgres"),
			Password:        getEnv("POSTGRES_PASSWORD", ""),
			SSLMode:         getEnv("POSTGRES_SSL_MODE", "disable"),
			MaxConns:        getEnvInt("POSTGRES_MAX_CONNS", 25),
			MinConns:        getEnvInt("POSTGRES_MIN_CONNS", 5),
			MaxConnLifetime: getEnvDuration("POSTGRES_MAX_CONN_LIFETIME", time.Hour),
		},
		Redis: RedisConfig{
			Address:  getEnv("REDIS_ADDRESS", "localhost:6379"),
			Password: getEnv("REDIS_PASSWORD", ""),
			DB:       getEnvInt("REDIS_DB", 0),
		},
		NATS: NATSConfig{
			URL:      getEnv("NATS_URL", "nats://localhost:4222"),
			Username: getEnv("NATS_USERNAME", ""),
			Password: getEnv("NATS_PASSWORD", ""),
		},
		Consul: ConsulConfig{
			Enabled: getEnvBool("CONSUL_ENABLED", false),
			Address: getEnv("CONSUL_ADDRESS", "localhost:8500"),
		},
		Logging: LoggingConfig{
			Level:  getEnv("LOG_LEVEL", "info"),
			Format: getEnv("LOG_FORMAT", "json"),
		},
	}
}

// Helper functions
func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func getEnvInt(key string, defaultValue int) int {
	if value := os.Getenv(key); value != "" {
		if i, err := strconv.Atoi(value); err == nil {
			return i
		}
	}
	return defaultValue
}

func getEnvBool(key string, defaultValue bool) bool {
	if value := os.Getenv(key); value != "" {
		if b, err := strconv.ParseBool(value); err == nil {
			return b
		}
	}
	return defaultValue
}

func getEnvDuration(key string, defaultValue time.Duration) time.Duration {
	if value := os.Getenv(key); value != "" {
		if d, err := time.ParseDuration(value); err == nil {
			return d
		}
	}
	return defaultValue
}
```

---

## 13. 测试规范

### 13.1 测试目录结构

```
internal/account/
├── repository/
│   ├── postgres.go
│   └── postgres_test.go     # Repository 单元测试
├── service/
│   ├── service.go
│   └── service_test.go      # Service 单元测试 (使用 Mock Repository)
└── handler/
    ├── grpc_handler.go
    └── handler_test.go      # Handler 单元测试 (使用 Mock Service)

tests/
├── integration/
│   └── account_test.go      # 集成测试
└── e2e/
    └── account_e2e_test.go  # 端到端测试
```

### 13.2 Mock 接口

```go
// internal/account/repository/mock_repository.go
package repository

import (
	"context"

	"github.com/stretchr/testify/mock"

	"github.com/isa-cloud/isa_cloud/internal/account/domain"
)

// MockAccountRepository Mock Repository
type MockAccountRepository struct {
	mock.Mock
}

func (m *MockAccountRepository) Create(ctx context.Context, account *domain.Account) error {
	args := m.Called(ctx, account)
	return args.Error(0)
}

func (m *MockAccountRepository) GetByID(ctx context.Context, userID string) (*domain.Account, error) {
	args := m.Called(ctx, userID)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*domain.Account), args.Error(1)
}

// ... 其他方法实现
```

### 13.3 Service 测试示例

```go
// internal/account/service/service_test.go
package service

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"

	"github.com/isa-cloud/isa_cloud/internal/account/domain"
	"github.com/isa-cloud/isa_cloud/internal/account/repository"
)

func TestAccountService_EnsureAccount_NewAccount(t *testing.T) {
	// Arrange
	mockRepo := new(repository.MockAccountRepository)
	svc := NewAccountService(mockRepo, nil, nil)

	req := EnsureAccountRequest{
		UserID: "usr_123",
		Email:  "test@example.com",
		Name:   "Test User",
		SubscriptionPlan: domain.SubscriptionStatusFree,
	}

	// Mock: 账户不存在
	mockRepo.On("GetByID", mock.Anything, "usr_123").
		Return(nil, domain.ErrAccountNotFound)

	// Mock: 创建成功
	mockRepo.On("Create", mock.Anything, mock.AnythingOfType("*domain.Account")).
		Return(nil)

	// Act
	account, wasCreated, err := svc.EnsureAccount(context.Background(), req)

	// Assert
	assert.NoError(t, err)
	assert.True(t, wasCreated)
	assert.Equal(t, "usr_123", account.UserID)
	assert.Equal(t, "test@example.com", account.Email)

	mockRepo.AssertExpectations(t)
}

func TestAccountService_EnsureAccount_ExistingAccount(t *testing.T) {
	// Arrange
	mockRepo := new(repository.MockAccountRepository)
	svc := NewAccountService(mockRepo, nil, nil)

	existingAccount := &domain.Account{
		UserID: "usr_123",
		Email:  domain.Email("existing@example.com"),
		Name:   "Existing User",
	}

	// Mock: 账户已存在
	mockRepo.On("GetByID", mock.Anything, "usr_123").
		Return(existingAccount, nil)

	req := EnsureAccountRequest{
		UserID: "usr_123",
		Email:  "test@example.com",
		Name:   "Test User",
	}

	// Act
	account, wasCreated, err := svc.EnsureAccount(context.Background(), req)

	// Assert
	assert.NoError(t, err)
	assert.False(t, wasCreated)
	assert.Equal(t, "existing@example.com", account.Email)

	mockRepo.AssertExpectations(t)
}
```

---

## 14. 服务注册与发现

### 14.1 Consul 注册

```go
// pkg/consul/registrar.go
package consul

import (
	"fmt"
	"os"

	consulapi "github.com/hashicorp/consul/api"
)

// ServiceRegistrar 服务注册器
type ServiceRegistrar struct {
	client    *consulapi.Client
	serviceID string
}

// RegistrationConfig 注册配置
type RegistrationConfig struct {
	ServiceName string
	Port        int
	Tags        []string
	HealthCheck string // gRPC health check endpoint
}

// NewServiceRegistrar 创建服务注册器
func NewServiceRegistrar(consulAddr string) (*ServiceRegistrar, error) {
	config := consulapi.DefaultConfig()
	config.Address = consulAddr

	client, err := consulapi.NewClient(config)
	if err != nil {
		return nil, fmt.Errorf("failed to create consul client: %w", err)
	}

	return &ServiceRegistrar{client: client}, nil
}

// Register 注册服务
func (r *ServiceRegistrar) Register(cfg RegistrationConfig) error {
	hostname, _ := os.Hostname()
	r.serviceID = fmt.Sprintf("%s-%s", cfg.ServiceName, hostname)

	registration := &consulapi.AgentServiceRegistration{
		ID:      r.serviceID,
		Name:    cfg.ServiceName,
		Port:    cfg.Port,
		Address: hostname,
		Tags:    cfg.Tags,
		Check: &consulapi.AgentServiceCheck{
			GRPC:                           fmt.Sprintf("%s:%d", hostname, cfg.Port),
			Interval:                       "10s",
			Timeout:                        "5s",
			DeregisterCriticalServiceAfter: "30s",
		},
	}

	return r.client.Agent().ServiceRegister(registration)
}

// Deregister 注销服务
func (r *ServiceRegistrar) Deregister() error {
	if r.serviceID != "" {
		return r.client.Agent().ServiceDeregister(r.serviceID)
	}
	return nil
}
```

---

## 15. 完整示例

### 15.1 开发新服务的完整流程

#### Step 1: 定义 Proto

```bash
# 1. 创建 proto 文件
mkdir -p api/proto/account
touch api/proto/account/account.proto

# 2. 编写 proto 定义 (参考第3节)

# 3. 生成 Go 代码
make proto-account
```

#### Step 2: 创建目录结构

```bash
mkdir -p internal/account/{domain,repository,service,handler,event,client}
mkdir -p cmd/account-service
```

#### Step 3: 实现各层

```
1. domain/entity.go       - 定义领域实体
2. domain/value_object.go - 定义值对象
3. domain/errors.go       - 定义领域错误
4. repository/interface.go - 定义 Repository 接口
5. repository/postgres.go  - 实现 PostgreSQL Repository
6. service/interface.go    - 定义 Service 接口
7. service/dto.go          - 定义输入/输出 DTO
8. service/service.go      - 实现 Service
9. handler/grpc_handler.go - 实现 gRPC Handler
10. handler/converter.go   - Proto <-> Domain 转换
11. event/publisher.go     - 事件发布器
12. cmd/account-service/main.go - 服务入口
```

#### Step 4: 编写测试

```bash
# 运行单元测试
go test ./internal/account/...

# 运行集成测试
go test ./tests/integration/...
```

#### Step 5: 构建和部署

```bash
# 构建
go build -o bin/account-service ./cmd/account-service

# Docker 构建
docker build -f deployments/dockerfiles/Dockerfile.account-service -t account-service:latest .

# 运行
./bin/account-service
```

### 15.2 Checklist

在开发新微服务时，请检查以下项目：

- [ ] Proto 定义完整且符合规范
- [ ] 领域模型正确封装业务规则
- [ ] Repository 接口抽象数据访问
- [ ] Service 层包含完整业务逻辑
- [ ] gRPC Handler 正确处理请求/响应转换
- [ ] 错误处理统一且符合 gRPC 规范
- [ ] 事件发布覆盖所有状态变更
- [ ] 单元测试覆盖核心逻辑
- [ ] 配置通过环境变量管理
- [ ] 健康检查端点可用
- [ ] 服务注册到 Consul (如果启用)
- [ ] Dockerfile 和部署配置完整

---

## 参考资源

- [Go Microservice with Clean Architecture](https://medium.com/@jfeng45/go-microservice-with-clean-architecture-a08fa916a5db)
- [Structuring Go gRPC microservices](https://medium.com/@nate510/structuring-go-grpc-microservices-dd176fdf28d0)
- [gRPC, Dependency Injection with Uber Fx, and Hexagonal Architecture in Go](https://dev.to/tylerasa/grpc-dependency-injection-with-uber-fx-and-hexagonal-architecture-in-go-3p0l)
- [Building Production Grade Microservices with Go and gRPC](https://dev.to/nikl/building-production-grade-microservices-with-go-and-grpc-a-step-by-step-developer-guide-with-example-2839)
- [GitHub: GO-microservice-clean-architecture](https://github.com/athun-me/GO-microservice-clean-architecture)
- [Three Dots Labs: Clean Architecture in Go](https://threedots.tech/post/introducing-clean-architecture/)
- [gRPC Microservices in Go (Book)](https://www.oreilly.com/library/view/grpc-microservices-in/9781633439207/)
