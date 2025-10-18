package middleware

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"golang.org/x/sync/singleflight"

	"github.com/isa-cloud/isa_cloud/internal/config"
	"github.com/isa-cloud/isa_cloud/internal/gateway/cache"
	"github.com/isa-cloud/isa_cloud/internal/gateway/circuitbreaker"
	"github.com/isa-cloud/isa_cloud/internal/gateway/clients"
	"github.com/isa-cloud/isa_cloud/internal/gateway/registry"
	"github.com/isa-cloud/isa_cloud/pkg/logger"
)

// AuthContext holds dependencies for authentication middleware
type AuthContext struct {
	tokenCache      cache.Cache
	permissionCache cache.Cache
	authBreaker     *circuitbreaker.CircuitBreaker
	authzBreaker    *circuitbreaker.CircuitBreaker
	sfGroup         singleflight.Group
}

// AuthService response structs
type TokenVerificationResponse struct {
	Valid     bool   `json:"valid"`
	Provider  string `json:"provider"`
	UserID    string `json:"user_id"`
	Email     string `json:"email"`
	ExpiresAt string `json:"expires_at"`
	Error     string `json:"error"`
}

type APIKeyVerificationResponse struct {
	Valid          bool     `json:"valid"`
	KeyID          string   `json:"key_id"`
	OrganizationID string   `json:"organization_id"`
	Name           string   `json:"name"`
	Permissions    []string `json:"permissions"`
	CreatedAt      string   `json:"created_at"`
	LastUsed       string   `json:"last_used"`
	Error          string   `json:"error"`
}

// AuthorizationService response structs
type AccessCheckResponse struct {
	HasAccess          bool   `json:"has_access"`
	UserAccessLevel    string `json:"user_access_level"`
	PermissionSource   string `json:"permission_source"`
	SubscriptionTier   string `json:"subscription_tier"`
	OrganizationPlan   string `json:"organization_plan"`
	Reason             string `json:"reason"`
	ExpiresAt          string `json:"expires_at"`
	Metadata           map[string]interface{} `json:"metadata"`
}

// UnifiedAuthentication provides a unified authentication middleware that:
// 1. Routes external requests through Auth Service (8202)
// 2. Maintains compatibility with service-specific auth (Agent, MCP)
// 3. Handles internal service-to-service communication
// 4. Includes circuit breaker protection and caching
func UnifiedAuthentication(authClient clients.AuthClient, consul *registry.ConsulRegistry, cfg *config.Config, logger *logger.Logger) gin.HandlerFunc {
	// Initialize AuthContext with circuit breakers and caches
	authCtx := &AuthContext{}

	// Initialize token cache if enabled
	if cfg.Security.Auth.Cache.Enabled {
		authCtx.tokenCache = cache.NewMemoryCache()
		logger.Info("Token cache enabled", "ttl", cfg.Security.Auth.Cache.TTL)
	}

	// Initialize permission cache if enabled
	if cfg.Security.Authorization.Cache.Enabled {
		authCtx.permissionCache = cache.NewMemoryCache()
		logger.Info("Permission cache enabled", "ttl", cfg.Security.Authorization.Cache.TTL)
	}

	// Initialize circuit breakers if enabled
	if cfg.Security.Auth.CircuitBreaker.Enabled {
		authCtx.authBreaker = circuitbreaker.NewAuthServiceBreaker(
			uint32(cfg.Security.Auth.CircuitBreaker.Threshold),
			cfg.Security.Auth.CircuitBreaker.Timeout,
			logger,
		)
		logger.Info("Auth service circuit breaker enabled",
			"threshold", cfg.Security.Auth.CircuitBreaker.Threshold,
			"timeout", cfg.Security.Auth.CircuitBreaker.Timeout,
		)
	}

	if cfg.Security.Authorization.CircuitBreaker.Enabled {
		authCtx.authzBreaker = circuitbreaker.NewAuthorizationServiceBreaker(
			uint32(cfg.Security.Authorization.CircuitBreaker.Threshold),
			cfg.Security.Authorization.CircuitBreaker.Timeout,
			logger,
		)
		logger.Info("Authorization service circuit breaker enabled",
			"threshold", cfg.Security.Authorization.CircuitBreaker.Threshold,
			"timeout", cfg.Security.Authorization.CircuitBreaker.Timeout,
		)
	}

	return func(c *gin.Context) {
		// Skip authentication for health checks and public endpoints
		if isPublicEndpoint(c.Request.URL.Path) {
			c.Next()
			return
		}

		// Check for internal service authentication first
		if authenticated := handleInternalServiceAuth(c, consul, logger); authenticated {
			return
		}

		// Handle external authentication via Auth Service
		if authenticated := handleExternalAuth(c, authClient, consul, cfg, authCtx, logger); authenticated {
			return
		}

		// Authentication failed
		c.JSON(http.StatusUnauthorized, gin.H{
			"error": "authentication required",
			"message": "valid JWT token or API key required",
		})
		c.Abort()
	}
}

// isPublicEndpoint checks if the endpoint should bypass authentication
func isPublicEndpoint(path string) bool {
	publicPaths := []string{
		"/health",
		"/ready",
		"/api/v1/gateway/services", // Allow service discovery
	}

	for _, publicPath := range publicPaths {
		if strings.HasPrefix(path, publicPath) {
			return true
		}
	}
	return false
}

// handleInternalServiceAuth handles service-to-service authentication
func handleInternalServiceAuth(c *gin.Context, consul *registry.ConsulRegistry, logger *logger.Logger) bool {
	// Method 1: Explicit internal service header with Consul validation
	serviceName := c.GetHeader("X-Service-Name")
	serviceSecret := c.GetHeader("X-Service-Secret")
	
	if serviceName != "" && serviceSecret != "" && consul != nil {
		// Validate service is registered in Consul
		if isValidInternalService(serviceName, consul, logger) {
			// In production, validate serviceSecret against a shared secret
			// For now, accept any registered service
			logger.Debug("Internal service authenticated",
				"service", serviceName,
				"path", c.Request.URL.Path,
			)
			c.Set("user_id", "service-"+serviceName)
			c.Set("organization_id", "internal")
			c.Set("is_internal", true)
			c.Set("service_name", serviceName)
			c.Next()
			return true
		}
	}

	// Method 2: Development mode - localhost with service user agents
	clientIP := c.ClientIP()
	if isLocalhost(clientIP) {
		userAgent := c.GetHeader("User-Agent")
		if isServiceUserAgent(userAgent) {
			logger.Debug("Local development service authenticated",
				"ip", clientIP,
				"user_agent", userAgent,
				"path", c.Request.URL.Path,
			)
			c.Set("user_id", "local-dev-service")
			c.Set("organization_id", "local")
			c.Set("is_internal", true)
			c.Next()
			return true
		}
	}

	return false
}

// handleExternalAuth handles external user authentication via Auth Service
func handleExternalAuth(c *gin.Context, authClient clients.AuthClient, consul *registry.ConsulRegistry, cfg *config.Config, authCtx *AuthContext, logger *logger.Logger) bool {
	// Try JWT token authentication first
	if authenticated := handleJWTAuth(c, authClient, consul, cfg, authCtx, logger); authenticated {
		return true
	}

	// Try API key authentication
	if authenticated := handleAPIKeyAuth(c, authClient, consul, cfg, authCtx, logger); authenticated {
		return true
	}

	return false
}

// handleJWTAuth validates JWT tokens via Auth Service with caching and circuit breaker
func handleJWTAuth(c *gin.Context, authClient clients.AuthClient, consul *registry.ConsulRegistry, cfg *config.Config, authCtx *AuthContext, logger *logger.Logger) bool {
	authHeader := c.GetHeader("Authorization")
	if authHeader == "" {
		return false
	}

	// Parse Bearer token
	parts := strings.SplitN(authHeader, " ", 2)
	if len(parts) != 2 || parts[0] != "Bearer" {
		return false
	}

	token := parts[1]
	if token == "" {
		return false
	}

	// Check cache first if enabled
	cacheKey := cache.HashToken(token)
	if authCtx.tokenCache != nil {
		if cached, found := authCtx.tokenCache.Get(context.Background(), cacheKey); found {
			tokenResp := cached.(*TokenVerificationResponse)
			logger.Debug("Token cache hit", "user_id", tokenResp.UserID)

			// Set user context from cache
			c.Set("user_id", tokenResp.UserID)
			c.Set("email", tokenResp.Email)
			c.Set("provider", tokenResp.Provider)
			c.Set("is_internal", false)
			c.Set("auth_method", "jwt")

			// Still check permissions (may have changed)
			if !checkResourcePermissions(c, tokenResp.UserID, consul, cfg, authCtx, logger) {
				c.JSON(http.StatusForbidden, gin.H{
					"error":   "insufficient permissions",
					"message": "user does not have permission to access this resource",
				})
				c.Abort()
				return false
			}

			c.Next()
			return true
		}
	}

	// Use singleflight to deduplicate concurrent requests for same token
	result, err, _ := authCtx.sfGroup.Do(cacheKey, func() (interface{}, error) {
		return verifyTokenWithBreaker(token, consul, cfg, authCtx, logger)
	})

	if err != nil {
		logger.Error("Token verification failed", "error", err)
		return false
	}

	tokenResp := result.(*TokenVerificationResponse)
	if !tokenResp.Valid {
		logger.Debug("Token validation failed", "error", tokenResp.Error)
		return false
	}

	// Cache the result if caching is enabled
	if authCtx.tokenCache != nil {
		authCtx.tokenCache.Set(context.Background(), cacheKey, tokenResp, cfg.Security.Auth.Cache.TTL)
		logger.Debug("Token cached", "user_id", tokenResp.UserID, "ttl", cfg.Security.Auth.Cache.TTL)
	}

	// Set user context
	c.Set("user_id", tokenResp.UserID)
	c.Set("email", tokenResp.Email)
	c.Set("provider", tokenResp.Provider)
	c.Set("is_internal", false)
	c.Set("auth_method", "jwt")

	// Check resource-specific permissions
	if !checkResourcePermissions(c, tokenResp.UserID, consul, cfg, authCtx, logger) {
		c.JSON(http.StatusForbidden, gin.H{
			"error":   "insufficient permissions",
			"message": "user does not have permission to access this resource",
		})
		c.Abort()
		return false
	}

	logger.Debug("JWT authentication successful",
		"user_id", tokenResp.UserID,
		"provider", tokenResp.Provider,
	)

	c.Next()
	return true
}

// handleAPIKeyAuth validates API keys via Auth Service with caching and circuit breaker
func handleAPIKeyAuth(c *gin.Context, authClient clients.AuthClient, consul *registry.ConsulRegistry, cfg *config.Config, authCtx *AuthContext, logger *logger.Logger) bool {
	// Check multiple sources for API key
	apiKey := c.GetHeader("X-API-Key")
	if apiKey == "" {
		apiKey = c.Query("api_key")
	}
	if apiKey == "" {
		if cookie, err := c.Cookie("api_key"); err == nil {
			apiKey = cookie
		}
	}

	if apiKey == "" {
		return false
	}

	// Resolve auth service URL using Consul or fallback
	authServiceURL := resolveAuthServiceURL(consul, cfg, logger)
	verifyAPIKeyURL := fmt.Sprintf("%s/api/v1/auth/verify-api-key", authServiceURL)

	// Call Auth Service to verify API key
	ctx, cancel := context.WithTimeout(context.Background(), cfg.Security.Auth.Timeout)
	defer cancel()

	payload := map[string]interface{}{
		"api_key": apiKey,
	}

	response, err := makeAuthServiceRequest(ctx, verifyAPIKeyURL, payload, logger)
	if err != nil {
		logger.Error("Auth service API key verification failed", "error", err, "url", verifyAPIKeyURL)
		return false
	}

	var keyResp APIKeyVerificationResponse
	if err := json.Unmarshal(response, &keyResp); err != nil {
		logger.Error("Failed to parse API key verification response", "error", err)
		return false
	}

	if !keyResp.Valid {
		logger.Debug("API key validation failed", "error", keyResp.Error)
		return false
	}

	// Set user context
	c.Set("user_id", "api-key-"+keyResp.KeyID)
	c.Set("organization_id", keyResp.OrganizationID)
	c.Set("api_key_name", keyResp.Name)
	c.Set("permissions", keyResp.Permissions)
	c.Set("is_internal", false)
	c.Set("auth_method", "api_key")

	logger.Debug("API key authentication successful",
		"key_id", keyResp.KeyID,
		"organization_id", keyResp.OrganizationID,
		"name", keyResp.Name,
	)

	c.Next()
	return true
}

// Helper functions

// resolveAuthServiceURL resolves the authentication service URL using Consul or fallback
func resolveAuthServiceURL(consul *registry.ConsulRegistry, cfg *config.Config, logger *logger.Logger) string {
	// Try Consul service discovery if enabled
	if cfg.Security.Auth.UseConsul && consul != nil {
		instance, err := consul.GetHealthyInstance(cfg.Security.Auth.ConsulService)
		if err == nil {
			url := fmt.Sprintf("http://%s:%d", instance.Host, instance.Port)
			logger.Debug("Resolved auth service via Consul",
				"consul_service", cfg.Security.Auth.ConsulService,
				"url", url,
			)
			return url
		}
		logger.Warn("Failed to resolve auth service via Consul, using fallback",
			"consul_service", cfg.Security.Auth.ConsulService,
			"error", err,
		)
	}

	// Fallback to configured service URL
	logger.Debug("Using fallback auth service URL", "url", cfg.Security.Auth.ServiceURL)
	return cfg.Security.Auth.ServiceURL
}

// resolveAuthorizationServiceURL resolves the authorization service URL using Consul or fallback
func resolveAuthorizationServiceURL(consul *registry.ConsulRegistry, cfg *config.Config, logger *logger.Logger) string {
	// Try Consul service discovery if enabled
	if cfg.Security.Authorization.UseConsul && consul != nil {
		instance, err := consul.GetHealthyInstance(cfg.Security.Authorization.ConsulService)
		if err == nil {
			url := fmt.Sprintf("http://%s:%d", instance.Host, instance.Port)
			logger.Debug("Resolved authorization service via Consul",
				"consul_service", cfg.Security.Authorization.ConsulService,
				"url", url,
			)
			return url
		}
		logger.Warn("Failed to resolve authorization service via Consul, using fallback",
			"consul_service", cfg.Security.Authorization.ConsulService,
			"error", err,
		)
	}

	// Fallback to configured service URL
	logger.Debug("Using fallback authorization service URL", "url", cfg.Security.Authorization.ServiceURL)
	return cfg.Security.Authorization.ServiceURL
}

func isValidInternalService(serviceName string, consul *registry.ConsulRegistry, logger *logger.Logger) bool {
	if consul == nil {
		return false
	}

	services, err := consul.ListServices()
	if err != nil {
		logger.Error("Failed to list Consul services", "error", err)
		return false
	}

	_, exists := services[serviceName]
	return exists
}

func isLocalhost(ip string) bool {
	return ip == "127.0.0.1" || ip == "::1" || strings.HasPrefix(ip, "localhost")
}

func isServiceUserAgent(userAgent string) bool {
	serviceUserAgents := []string{
		"python-httpx",
		"axios",
		"node-fetch",
		"go-resty",
		"curl",
	}

	userAgent = strings.ToLower(userAgent)
	for _, serviceUA := range serviceUserAgents {
		if strings.Contains(userAgent, serviceUA) {
			return true
		}
	}
	return false
}

func makeAuthServiceRequest(ctx context.Context, url string, payload map[string]interface{}, logger *logger.Logger) ([]byte, error) {
	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal payload: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", url, strings.NewReader(string(payloadBytes)))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{
		Timeout: 10 * time.Second, // Increased timeout
	}

	logger.Debug("Calling auth/authorization service", "url", url)

	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	responseBody := make([]byte, 0, resp.ContentLength)
	buffer := make([]byte, 1024)
	for {
		n, err := resp.Body.Read(buffer)
		if n > 0 {
			responseBody = append(responseBody, buffer[:n]...)
		}
		if err != nil {
			break
		}
	}

	if resp.StatusCode != http.StatusOK {
		logger.Error("Auth service returned non-OK status",
			"status_code", resp.StatusCode,
			"response", string(responseBody),
			"url", url,
		)
		return nil, fmt.Errorf("auth service returned status %d: %s", resp.StatusCode, string(responseBody))
	}

	logger.Debug("Auth service request successful", "url", url, "response_size", len(responseBody))
	return responseBody, nil
}

// checkResourcePermissions validates user permissions for specific resources via Authorization Service with caching
func checkResourcePermissions(c *gin.Context, userID string, consul *registry.ConsulRegistry, cfg *config.Config, authCtx *AuthContext, logger *logger.Logger) bool {
	// Determine resource type and name from the request path
	resourceType, resourceName, requiredLevel := getResourceInfoFromPath(c.Request.URL.Path)

	// Skip permission check for public resources or if resource type is not recognized
	if resourceType == "" || requiredLevel == "" {
		return true
	}

	// Resolve authorization service URL using Consul or fallback
	authzServiceURL := resolveAuthorizationServiceURL(consul, cfg, logger)
	checkAccessURL := fmt.Sprintf("%s/api/v1/authorization/check-access", authzServiceURL)

	// Call Authorization Service to check access
	ctx, cancel := context.WithTimeout(context.Background(), cfg.Security.Authorization.Timeout)
	defer cancel()

	payload := map[string]interface{}{
		"user_id": userID,
		"resource_type": resourceType,
		"resource_name": resourceName,
		"required_access_level": requiredLevel,
	}

	response, err := makeAuthServiceRequest(ctx, checkAccessURL, payload, logger)
	if err != nil {
		logger.Error("Authorization service request failed", "error", err, "user_id", userID, "url", checkAccessURL)
		// Apply fail policy from config
		if cfg.Security.Authorization.FailPolicy == "fail_closed" {
			logger.Warn("Fail-closed policy: denying access due to authorization service failure")
			return false
		}
		// Fail-open: allow access when service is unavailable
		logger.Warn("Fail-open policy: allowing access despite authorization service failure")
		return true
	}

	var accessResp AccessCheckResponse
	if err := json.Unmarshal(response, &accessResp); err != nil {
		logger.Error("Failed to parse access check response", "error", err)
		return true
	}

	if !accessResp.HasAccess {
		logger.Debug("Access denied by authorization service",
			"user_id", userID,
			"resource_type", resourceType,
			"resource_name", resourceName,
			"reason", accessResp.Reason,
		)
		return false
	}

	// Store permission info in context for downstream services
	c.Set("access_level", accessResp.UserAccessLevel)
	c.Set("permission_source", accessResp.PermissionSource)
	c.Set("subscription_tier", accessResp.SubscriptionTier)

	logger.Debug("Access granted by authorization service",
		"user_id", userID,
		"resource_type", resourceType,
		"access_level", accessResp.UserAccessLevel,
		"permission_source", accessResp.PermissionSource,
	)

	return true
}

// getResourceInfoFromPath extracts resource information from the request path
func getResourceInfoFromPath(path string) (resourceType, resourceName, requiredLevel string) {
	// Define resource mappings based on API paths using Authorization Service's expected types
	if strings.HasPrefix(path, "/api/v1/blockchain/") {
		return "api_endpoint", "blockchain_" + extractBlockchainResource(path), "read_only"
	}
	
	if strings.HasPrefix(path, "/api/v1/agents/") {
		return "api_endpoint", "agent_chat", getAgentAccessLevel(path)
	}
	
	if strings.HasPrefix(path, "/api/v1/mcp/") {
		return "mcp_tool", extractMCPResource(path), getMCPAccessLevel(path)
	}
	
	if strings.HasPrefix(path, "/api/v1/gateway/") {
		return "api_endpoint", "gateway_management", "read_only"
	}

	// Unknown resource, skip permission check
	return "", "", ""
}

// Helper functions to extract resource details from specific API paths

func extractBlockchainResource(path string) string {
	if strings.Contains(path, "/balance/") {
		return "balance_check"
	}
	if strings.Contains(path, "/transaction") {
		return "transaction"
	}
	if strings.Contains(path, "/status") {
		return "status"
	}
	return "blockchain_general"
}

func getAgentAccessLevel(path string) string {
	if strings.Contains(path, "/api/chat") {
		return "read_write" // Chat requires read_write
	}
	return "read_only"
}

func extractMCPResource(path string) string {
	if strings.Contains(path, "/search") {
		return "search"
	}
	if strings.Contains(path, "/tools/call") {
		return "tool_execution"
	}
	if strings.Contains(path, "/prompts/get") {
		return "prompt_access"
	}
	return "mcp_general"
}

func getMCPAccessLevel(path string) string {
	if strings.Contains(path, "/tools/call") {
		return "read_write" // Tool execution requires read_write
	}
	return "read_only"
}

// verifyTokenWithBreaker verifies a token with circuit breaker protection
func verifyTokenWithBreaker(token string, consul *registry.ConsulRegistry, cfg *config.Config, authCtx *AuthContext, logger *logger.Logger) (*TokenVerificationResponse, error) {
	verifyFunc := func() (interface{}, error) {
		authServiceURL := resolveAuthServiceURL(consul, cfg, logger)
		verifyTokenURL := fmt.Sprintf("%s/api/v1/auth/verify-token", authServiceURL)

		ctx, cancel := context.WithTimeout(context.Background(), cfg.Security.Auth.Timeout)
		defer cancel()

		payload := map[string]interface{}{
			"token": token,
		}

		response, err := makeAuthServiceRequest(ctx, verifyTokenURL, payload, logger)
		if err != nil {
			return nil, err
		}

		var tokenResp TokenVerificationResponse
		if err := json.Unmarshal(response, &tokenResp); err != nil {
			return nil, fmt.Errorf("failed to parse token verification response: %w", err)
		}

		return &tokenResp, nil
	}

	// Use circuit breaker if enabled
	if authCtx.authBreaker != nil {
		result, err := authCtx.authBreaker.Execute(context.Background(), verifyFunc)
		if err != nil {
			if circuitbreaker.IsCircuitBreakerError(err) {
				return nil, circuitbreaker.WrapError(err, "auth_service")
			}
			return nil, err
		}
		return result.(*TokenVerificationResponse), nil
	}

	// No circuit breaker, call directly
	result, err := verifyFunc()
	if err != nil {
		return nil, err
	}
	return result.(*TokenVerificationResponse), nil
}