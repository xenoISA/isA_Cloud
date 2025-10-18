// Package server implements authentication
// 文件名: cmd/supabase-service/server/auth.go
package server

import (
	"context"
	"fmt"

	"github.com/isa-cloud/isa_cloud/api/proto"
	"github.com/isa-cloud/isa_cloud/pkg/storage"
)

// AuthService 认证服务
type AuthService struct {
	config *storage.StorageConfig
}

// NewAuthService 创建认证服务
func NewAuthService(cfg *storage.StorageConfig) *AuthService {
	return &AuthService{config: cfg}
}

// AuthenticateRequest 认证请求
// 从 RequestMetadata 中提取用户信息
func (a *AuthService) AuthenticateRequest(ctx context.Context, metadata *proto.RequestMetadata) (string, error) {
	if metadata == nil {
		return "", fmt.Errorf("metadata is required")
	}

	// 方式 1: 从 metadata 中直接获取 user_id (简化认证)
	userID := metadata.UserId
	if userID != "" {
		return userID, nil
	}

	// 方式 2: 从 access_token 中解析 (JWT 认证)
	if metadata.AccessToken != "" {
		// TODO: 实现 JWT 验证和解析
		// 这里需要：
		// 1. 验证 JWT 签名
		// 2. 检查过期时间
		// 3. 提取 user_id
		//
		// 示例:
		// claims, err := validateJWT(metadata.AccessToken, a.config.JWT.Secret)
		// if err != nil {
		//     return "", fmt.Errorf("invalid token: %w", err)
		// }
		// return claims.UserID, nil

		// 临时实现：假设 token 就是 user_id (仅用于开发测试)
		return metadata.AccessToken, nil
	}

	// 方式 3: 从 gRPC metadata 中获取
	// md, ok := grpcMetadata.FromIncomingContext(ctx)
	// if ok {
	//     if values := md.Get("authorization"); len(values) > 0 {
	//         token := values[0]
	//         // 验证和解析 token
	//     }
	// }

	return "", fmt.Errorf("authentication required: user_id or access_token must be provided")
}

// ValidateUser 验证用户权限
func (a *AuthService) ValidateUser(userID string) error {
	if userID == "" {
		return fmt.Errorf("user_id is required")
	}

	// TODO: 实现更多验证逻辑
	// - 检查用户是否存在
	// - 检查用户是否激活
	// - 检查用户权限
	// - 检查组织权限等

	return nil
}

// ValidatePermission 验证用户是否有特定权限
func (a *AuthService) ValidatePermission(userID string, permission string) error {
	if err := a.ValidateUser(userID); err != nil {
		return err
	}

	// TODO: 实现权限检查
	// - 查询用户角色
	// - 检查角色是否有该权限
	// - 支持细粒度权限控制 (如 table:read, table:write)

	return nil
}

// ExtractOrganizationID 提取组织 ID
func (a *AuthService) ExtractOrganizationID(metadata *proto.RequestMetadata) string {
	if metadata != nil {
		return metadata.OrganizationId
	}
	return ""
}
