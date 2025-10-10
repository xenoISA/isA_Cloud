package clients

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/isa-cloud/isa_cloud/internal/config"
	"github.com/isa-cloud/isa_cloud/pkg/logger"
)

// SupabaseClient handles Supabase operations
type SupabaseClient struct {
	config     *config.Config
	logger     *logger.Logger
	httpClient *http.Client
	baseURL    string
	apiKey     string
	stats      *SupabaseStats
}

// SupabaseStats holds Supabase-specific statistics
type SupabaseStats struct {
	TotalRequests    int64         `json:"total_requests"`
	TotalErrors      int64         `json:"total_errors"`
	AvgResponseTime  time.Duration `json:"avg_response_time"`
	LastRequest      time.Time     `json:"last_request"`
	DatabaseCalls    int64         `json:"database_calls"`
	AuthCalls        int64         `json:"auth_calls"`
	StorageCalls     int64         `json:"storage_calls"`
	RealtimeCalls    int64         `json:"realtime_calls"`
}

// SupabaseRequest represents a Supabase API request
type SupabaseRequest struct {
	Service   string                 `json:"service"`   // database, auth, storage, realtime
	Method    string                 `json:"method"`    // GET, POST, PUT, DELETE, PATCH
	Endpoint  string                 `json:"endpoint"`  // API endpoint
	Data      map[string]interface{} `json:"data"`      // Request body
	Query     map[string]interface{} `json:"query"`     // Query parameters
	Headers   map[string]string      `json:"headers"`   // Additional headers
	Schema    string                 `json:"schema"`    // Database schema (for database operations)
}

// NewSupabaseClient creates a new Supabase client
func NewSupabaseClient(cfg *config.Config, logger *logger.Logger) (*SupabaseClient, error) {
	if cfg.Infrastructure.Supabase.URL == "" {
		return nil, fmt.Errorf("supabase URL not configured")
	}
	
	if cfg.Infrastructure.Supabase.AnonKey == "" {
		return nil, fmt.Errorf("supabase anon key not configured")
	}
	
	client := &SupabaseClient{
		config:  cfg,
		logger:  logger,
		baseURL: cfg.Infrastructure.Supabase.URL,
		apiKey:  cfg.Infrastructure.Supabase.AnonKey,
		httpClient: &http.Client{
			Timeout: time.Duration(cfg.Infrastructure.Supabase.Timeout) * time.Second,
		},
		stats: &SupabaseStats{},
	}
	
	// Test connection
	if err := client.Ping(); err != nil {
		return nil, fmt.Errorf("failed to ping supabase: %w", err)
	}
	
	logger.Info("Supabase client initialized", "url", cfg.Infrastructure.Supabase.URL)
	return client, nil
}

// Close closes the Supabase client
func (c *SupabaseClient) Close() error {
	c.logger.Info("Closing Supabase client")
	// HTTP client doesn't need explicit closing
	return nil
}

// Ping checks if Supabase is accessible
func (c *SupabaseClient) Ping() error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	
	req, err := http.NewRequestWithContext(ctx, "GET", c.baseURL+"/rest/v1/", nil)
	if err != nil {
		return fmt.Errorf("failed to create ping request: %w", err)
	}
	
	req.Header.Set("apikey", c.apiKey)
	req.Header.Set("Authorization", "Bearer "+c.apiKey)
	
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("ping request failed: %w", err)
	}
	defer resp.Body.Close()
	
	if resp.StatusCode >= 400 {
		return fmt.Errorf("supabase ping failed with status: %d", resp.StatusCode)
	}
	
	return nil
}

// Execute executes a Supabase operation
func (c *SupabaseClient) Execute(ctx context.Context, operation string, params map[string]interface{}) (interface{}, error) {
	start := time.Now()
	defer func() {
		c.updateStats(time.Since(start))
	}()
	
	switch operation {
	case "database":
		return c.executeDatabaseOperation(ctx, params)
	case "auth":
		return c.executeAuthOperation(ctx, params)
	case "storage":
		return c.executeStorageOperation(ctx, params)
	case "realtime":
		return c.executeRealtimeOperation(ctx, params)
	case "rpc":
		return c.executeRPCOperation(ctx, params)
	default:
		return nil, fmt.Errorf("unsupported supabase operation: %s", operation)
	}
}

// executeDatabaseOperation executes database operations via REST API
func (c *SupabaseClient) executeDatabaseOperation(ctx context.Context, params map[string]interface{}) (interface{}, error) {
	c.stats.DatabaseCalls++
	
	table, ok := params["table"].(string)
	if !ok {
		return nil, fmt.Errorf("table parameter is required for database operations")
	}
	
	method, ok := params["method"].(string)
	if !ok {
		method = "GET"
	}
	
	// Build endpoint
	endpoint := fmt.Sprintf("/rest/v1/%s", table)
	
	// Add query parameters
	if query, ok := params["query"].(map[string]interface{}); ok {
		endpoint += c.buildQueryString(query)
	}
	
	// Prepare request
	var requestBody io.Reader
	if data, ok := params["data"]; ok && (method == "POST" || method == "PUT" || method == "PATCH") {
		jsonData, err := json.Marshal(data)
		if err != nil {
			return nil, fmt.Errorf("failed to marshal request data: %w", err)
		}
		requestBody = bytes.NewReader(jsonData)
	}
	
	req, err := http.NewRequestWithContext(ctx, method, c.baseURL+endpoint, requestBody)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	
	// Set headers
	req.Header.Set("apikey", c.apiKey)
	req.Header.Set("Authorization", "Bearer "+c.apiKey)
	req.Header.Set("Content-Type", "application/json")
	
	// Add custom headers
	if headers, ok := params["headers"].(map[string]string); ok {
		for key, value := range headers {
			req.Header.Set(key, value)
		}
	}
	
	// Add schema header if specified
	if schema, ok := params["schema"].(string); ok {
		req.Header.Set("Accept-Profile", schema)
		req.Header.Set("Content-Profile", schema)
	}
	
	// Execute request
	resp, err := c.httpClient.Do(req)
	if err != nil {
		c.stats.TotalErrors++
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()
	
	// Read response
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response: %w", err)
	}
	
	// Handle error responses
	if resp.StatusCode >= 400 {
		c.stats.TotalErrors++
		return nil, fmt.Errorf("supabase error %d: %s", resp.StatusCode, string(body))
	}
	
	// Parse JSON response
	var result interface{}
	if len(body) > 0 {
		if err := json.Unmarshal(body, &result); err != nil {
			return nil, fmt.Errorf("failed to parse response: %w", err)
		}
	}
	
	return map[string]interface{}{
		"data":        result,
		"status_code": resp.StatusCode,
		"headers":     resp.Header,
	}, nil
}

// executeAuthOperation executes authentication operations
func (c *SupabaseClient) executeAuthOperation(ctx context.Context, params map[string]interface{}) (interface{}, error) {
	c.stats.AuthCalls++
	
	authType, ok := params["type"].(string)
	if !ok {
		return nil, fmt.Errorf("type parameter is required for auth operations")
	}
	
	var endpoint string
	var method string = "POST"
	
	switch authType {
	case "signup":
		endpoint = "/auth/v1/signup"
	case "login":
		endpoint = "/auth/v1/token?grant_type=password"
	case "logout":
		endpoint = "/auth/v1/logout"
	case "refresh":
		endpoint = "/auth/v1/token?grant_type=refresh_token"
	case "verify":
		endpoint = "/auth/v1/verify"
	case "recover":
		endpoint = "/auth/v1/recover"
	case "user":
		endpoint = "/auth/v1/user"
		method = "GET"
	default:
		return nil, fmt.Errorf("unsupported auth type: %s", authType)
	}
	
	// Prepare request body
	var requestBody io.Reader
	if data, ok := params["data"]; ok {
		jsonData, err := json.Marshal(data)
		if err != nil {
			return nil, fmt.Errorf("failed to marshal auth data: %w", err)
		}
		requestBody = bytes.NewReader(jsonData)
	}
	
	req, err := http.NewRequestWithContext(ctx, method, c.baseURL+endpoint, requestBody)
	if err != nil {
		return nil, fmt.Errorf("failed to create auth request: %w", err)
	}
	
	// Set headers
	req.Header.Set("apikey", c.apiKey)
	req.Header.Set("Content-Type", "application/json")
	
	// Add authorization header if token provided
	if token, ok := params["token"].(string); ok {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	
	// Execute request
	resp, err := c.httpClient.Do(req)
	if err != nil {
		c.stats.TotalErrors++
		return nil, fmt.Errorf("auth request failed: %w", err)
	}
	defer resp.Body.Close()
	
	// Read response
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read auth response: %w", err)
	}
	
	// Handle error responses
	if resp.StatusCode >= 400 {
		c.stats.TotalErrors++
		return nil, fmt.Errorf("auth error %d: %s", resp.StatusCode, string(body))
	}
	
	// Parse JSON response
	var result interface{}
	if len(body) > 0 {
		if err := json.Unmarshal(body, &result); err != nil {
			return nil, fmt.Errorf("failed to parse auth response: %w", err)
		}
	}
	
	return result, nil
}

// executeStorageOperation executes storage operations
func (c *SupabaseClient) executeStorageOperation(ctx context.Context, params map[string]interface{}) (interface{}, error) {
	c.stats.StorageCalls++
	
	bucket, ok := params["bucket"].(string)
	if !ok {
		return nil, fmt.Errorf("bucket parameter is required for storage operations")
	}
	
	operation, ok := params["operation"].(string)
	if !ok {
		return nil, fmt.Errorf("operation parameter is required for storage operations")
	}
	
	var endpoint string
	var method string
	
	switch operation {
	case "upload":
		method = "POST"
		filepath, ok := params["path"].(string)
		if !ok {
			return nil, fmt.Errorf("path parameter is required for upload")
		}
		endpoint = fmt.Sprintf("/storage/v1/object/%s/%s", bucket, filepath)
	case "download":
		method = "GET"
		filepath, ok := params["path"].(string)
		if !ok {
			return nil, fmt.Errorf("path parameter is required for download")
		}
		endpoint = fmt.Sprintf("/storage/v1/object/%s/%s", bucket, filepath)
	case "delete":
		method = "DELETE"
		filepath, ok := params["path"].(string)
		if !ok {
			return nil, fmt.Errorf("path parameter is required for delete")
		}
		endpoint = fmt.Sprintf("/storage/v1/object/%s/%s", bucket, filepath)
	case "list":
		method = "POST"
		endpoint = fmt.Sprintf("/storage/v1/object/list/%s", bucket)
	default:
		return nil, fmt.Errorf("unsupported storage operation: %s", operation)
	}
	
	// Create request
	var requestBody io.Reader
	if data, ok := params["data"]; ok {
		if operation == "upload" {
			// Handle file upload
			if fileData, ok := data.([]byte); ok {
				requestBody = bytes.NewReader(fileData)
			} else {
				return nil, fmt.Errorf("invalid file data for upload")
			}
		} else {
			// Handle JSON data
			jsonData, err := json.Marshal(data)
			if err != nil {
				return nil, fmt.Errorf("failed to marshal storage data: %w", err)
			}
			requestBody = bytes.NewReader(jsonData)
		}
	}
	
	req, err := http.NewRequestWithContext(ctx, method, c.baseURL+endpoint, requestBody)
	if err != nil {
		return nil, fmt.Errorf("failed to create storage request: %w", err)
	}
	
	// Set headers
	req.Header.Set("apikey", c.apiKey)
	req.Header.Set("Authorization", "Bearer "+c.apiKey)
	
	if operation != "upload" {
		req.Header.Set("Content-Type", "application/json")
	}
	
	// Execute request
	resp, err := c.httpClient.Do(req)
	if err != nil {
		c.stats.TotalErrors++
		return nil, fmt.Errorf("storage request failed: %w", err)
	}
	defer resp.Body.Close()
	
	// Read response
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read storage response: %w", err)
	}
	
	// Handle error responses
	if resp.StatusCode >= 400 {
		c.stats.TotalErrors++
		return nil, fmt.Errorf("storage error %d: %s", resp.StatusCode, string(body))
	}
	
	// For download operations, return the raw data
	if operation == "download" {
		return map[string]interface{}{
			"data":         body,
			"content_type": resp.Header.Get("Content-Type"),
			"size":         len(body),
		}, nil
	}
	
	// Parse JSON response for other operations
	var result interface{}
	if len(body) > 0 {
		if err := json.Unmarshal(body, &result); err != nil {
			return nil, fmt.Errorf("failed to parse storage response: %w", err)
		}
	}
	
	return result, nil
}

// executeRealtimeOperation executes realtime operations
func (c *SupabaseClient) executeRealtimeOperation(ctx context.Context, params map[string]interface{}) (interface{}, error) {
	c.stats.RealtimeCalls++
	
	// Realtime operations typically require WebSocket connections
	// For now, return a placeholder implementation
	return map[string]interface{}{
		"message": "Realtime operations require WebSocket implementation",
		"status":  "not_implemented",
	}, nil
}

// executeRPCOperation executes RPC (stored procedure) operations
func (c *SupabaseClient) executeRPCOperation(ctx context.Context, params map[string]interface{}) (interface{}, error) {
	functionName, ok := params["function"].(string)
	if !ok {
		return nil, fmt.Errorf("function parameter is required for RPC operations")
	}
	
	endpoint := fmt.Sprintf("/rest/v1/rpc/%s", functionName)
	
	// Prepare request body
	var requestBody io.Reader
	if data, ok := params["params"]; ok {
		jsonData, err := json.Marshal(data)
		if err != nil {
			return nil, fmt.Errorf("failed to marshal RPC params: %w", err)
		}
		requestBody = bytes.NewReader(jsonData)
	}
	
	req, err := http.NewRequestWithContext(ctx, "POST", c.baseURL+endpoint, requestBody)
	if err != nil {
		return nil, fmt.Errorf("failed to create RPC request: %w", err)
	}
	
	// Set headers
	req.Header.Set("apikey", c.apiKey)
	req.Header.Set("Authorization", "Bearer "+c.apiKey)
	req.Header.Set("Content-Type", "application/json")
	
	// Execute request
	resp, err := c.httpClient.Do(req)
	if err != nil {
		c.stats.TotalErrors++
		return nil, fmt.Errorf("RPC request failed: %w", err)
	}
	defer resp.Body.Close()
	
	// Read response
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read RPC response: %w", err)
	}
	
	// Handle error responses
	if resp.StatusCode >= 400 {
		c.stats.TotalErrors++
		return nil, fmt.Errorf("RPC error %d: %s", resp.StatusCode, string(body))
	}
	
	// Parse JSON response
	var result interface{}
	if len(body) > 0 {
		if err := json.Unmarshal(body, &result); err != nil {
			return nil, fmt.Errorf("failed to parse RPC response: %w", err)
		}
	}
	
	return result, nil
}

// buildQueryString builds URL query string from parameters
func (c *SupabaseClient) buildQueryString(query map[string]interface{}) string {
	if len(query) == 0 {
		return ""
	}
	
	var parts []string
	for key, value := range query {
		parts = append(parts, fmt.Sprintf("%s=%v", key, value))
	}
	
	return "?" + fmt.Sprintf("%v", parts[0])
	// Note: This is a simplified implementation
	// In production, you'd want proper URL encoding
}

// GetConnectionStats returns connection statistics
func (c *SupabaseClient) GetConnectionStats() map[string]interface{} {
	return map[string]interface{}{
		"base_url":        c.baseURL,
		"timeout":         c.httpClient.Timeout.String(),
		"total_requests":  c.stats.TotalRequests,
		"total_errors":    c.stats.TotalErrors,
		"database_calls":  c.stats.DatabaseCalls,
		"auth_calls":      c.stats.AuthCalls,
		"storage_calls":   c.stats.StorageCalls,
		"realtime_calls":  c.stats.RealtimeCalls,
		"avg_response_time": c.stats.AvgResponseTime.String(),
		"last_request":    c.stats.LastRequest,
	}
}

// updateStats updates internal statistics
func (c *SupabaseClient) updateStats(duration time.Duration) {
	c.stats.TotalRequests++
	c.stats.LastRequest = time.Now()
	
	// Simple moving average for response time
	if c.stats.AvgResponseTime == 0 {
		c.stats.AvgResponseTime = duration
	} else {
		c.stats.AvgResponseTime = (c.stats.AvgResponseTime + duration) / 2
	}
}