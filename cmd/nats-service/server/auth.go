// Package server implements authentication
// 文件名: cmd/nats-service/server/auth.go
package server

import (
	"fmt"

	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/event"
)

// AuthService 认证服务
type AuthService struct {
	config *event.EventConfig
}

// NewAuthService 创建认证服务
func NewAuthService(cfg *event.EventConfig) *AuthService {
	return &AuthService{config: cfg}
}

// ValidateUser 验证用户权限
func (a *AuthService) ValidateUser(userID string) error {
	if userID == "" {
		return fmt.Errorf("user_id is required")
	}
	return nil
}


