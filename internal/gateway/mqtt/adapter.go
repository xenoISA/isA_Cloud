package mqtt

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
	"github.com/isa-cloud/isa_cloud/internal/config"
	"github.com/isa-cloud/isa_cloud/pkg/logger"
)

// Adapter handles MQTT protocol adaptation for IoT devices and notifications
type Adapter struct {
	config       *config.MQTTConfig
	logger       *logger.Logger
	client       mqtt.Client
	handlers     map[string]MessageHandler
	mu           sync.RWMutex
	httpClient   *http.Client
	deviceConfig *config.DeviceManagementConfig
	isConnected  bool
}

// MessageHandler processes MQTT messages
type MessageHandler func(topic string, payload []byte) error

// DeviceMessage represents a message from/to IoT device
type DeviceMessage struct {
	DeviceID    string                 `json:"device_id"`
	MessageType string                 `json:"message_type"`
	Timestamp   time.Time              `json:"timestamp"`
	Data        map[string]interface{} `json:"data"`
}

// NewAdapter creates a new MQTT adapter
func NewAdapter(cfg *config.MQTTConfig, deviceCfg *config.DeviceManagementConfig, logger *logger.Logger) *Adapter {
	adapter := &Adapter{
		config:       cfg,
		deviceConfig: deviceCfg,
		logger:       logger,
		handlers:     make(map[string]MessageHandler),
		httpClient:   &http.Client{Timeout: 30 * time.Second},
		isConnected:  false,
	}

	// Setup default handlers
	adapter.setupDefaultHandlers()

	return adapter
}

// Connect establishes connection to MQTT broker
func (a *Adapter) Connect() error {
	if !a.config.Enabled {
		a.logger.Info("MQTT adapter disabled in configuration")
		return nil
	}

	opts := mqtt.NewClientOptions()
	opts.AddBroker(a.config.BrokerURL)
	
	// Generate unique client ID using timestamp and random number
	// This ensures no conflicts even with multiple instances
	clientID := fmt.Sprintf("gw_%d", time.Now().UnixNano()%1000000)
	opts.SetClientID(clientID)
	a.logger.Debug("Using MQTT client ID", "client_id", clientID)

	if a.config.Username != "" {
		opts.SetUsername(a.config.Username)
		opts.SetPassword(a.config.Password)
	}

	// Set keep alive with defaults if not configured
	keepAlive := a.config.KeepAlive
	if keepAlive == 0 {
		keepAlive = 60 * time.Second
	}
	opts.SetKeepAlive(keepAlive)
	
	// Set ping timeout with defaults if not configured
	pingTimeout := a.config.PingTimeout
	if pingTimeout == 0 {
		pingTimeout = 10 * time.Second
	}
	opts.SetPingTimeout(pingTimeout)
	opts.SetCleanSession(a.config.CleanSession)
	opts.SetAutoReconnect(a.config.AutoReconnect)

	// Set connection handlers
	opts.SetOnConnectHandler(a.onConnect)
	opts.SetConnectionLostHandler(a.onConnectionLost)
	opts.SetReconnectingHandler(a.onReconnecting)

	// Create and connect client
	a.client = mqtt.NewClient(opts)

	// Log connection attempt details
	a.logger.Debug("Attempting MQTT connection",
		"broker", a.config.BrokerURL,
		"client_id", clientID,
		"clean_session", a.config.CleanSession,
		"auto_reconnect", a.config.AutoReconnect,
		"keep_alive", keepAlive,
		"ping_timeout", pingTimeout,
	)

	token := a.client.Connect()
	if token.Wait() && token.Error() != nil {
		// Additional debug info for connection failure
		a.logger.Error("MQTT connection failed",
			"error", token.Error(),
			"client_id", clientID,
			"broker", a.config.BrokerURL,
		)
		return fmt.Errorf("failed to connect to MQTT broker: %v", token.Error())
	}

	a.logger.Info("Connected to MQTT broker", "broker", a.config.BrokerURL)
	return nil
}

// Disconnect closes the MQTT connection
func (a *Adapter) Disconnect() {
	if a.client != nil && a.client.IsConnected() {
		a.client.Disconnect(250)
		a.logger.Info("Disconnected from MQTT broker")
	}
	a.isConnected = false
}

// Subscribe to MQTT topics
func (a *Adapter) Subscribe(topic string, handler MessageHandler) error {
	a.mu.Lock()
	a.handlers[topic] = handler
	a.mu.Unlock()

	token := a.client.Subscribe(topic, a.config.QoS, func(client mqtt.Client, msg mqtt.Message) {
		a.handleMessage(msg.Topic(), msg.Payload())
	})

	if token.Wait() && token.Error() != nil {
		return fmt.Errorf("failed to subscribe to topic %s: %v", topic, token.Error())
	}

	a.logger.Debug("Subscribed to MQTT topic", "topic", topic)
	return nil
}

// Publish message to MQTT topic
func (a *Adapter) Publish(topic string, payload interface{}) error {
	var data []byte
	var err error

	switch v := payload.(type) {
	case []byte:
		data = v
	case string:
		data = []byte(v)
	default:
		data, err = json.Marshal(payload)
		if err != nil {
			return fmt.Errorf("failed to marshal payload: %v", err)
		}
	}

	token := a.client.Publish(topic, a.config.QoS, false, data)
	if token.Wait() && token.Error() != nil {
		return fmt.Errorf("failed to publish to topic %s: %v", topic, token.Error())
	}

	a.logger.Debug("Published MQTT message", "topic", topic, "size", len(data))
	return nil
}

// setupDefaultHandlers configures default message handlers
func (a *Adapter) setupDefaultHandlers() {
	// Device telemetry handler
	a.handlers[a.config.Topics.DeviceTelemetry] = a.handleTelemetry

	// Device status handler
	a.handlers[a.config.Topics.DeviceStatus] = a.handleDeviceStatus

	// Device commands response handler
	a.handlers[a.config.Topics.DeviceCommandsResponse] = a.handleCommandResponse

	// Device authentication handler
	a.handlers[a.config.Topics.DeviceAuth] = a.handleDeviceAuth

	// Device registration handler
	a.handlers[a.config.Topics.DeviceRegistration] = a.handleDeviceRegistration

	// Notification acknowledgment handler
	a.handlers[a.config.Topics.NotificationUserAck] = a.handleNotificationAck

	// System notification handler
	a.handlers[a.config.Topics.NotificationSystem] = a.handleSystemNotification
}

// handleMessage processes incoming MQTT messages
func (a *Adapter) handleMessage(topic string, payload []byte) {
	a.mu.RLock()
	defer a.mu.RUnlock()

	// Find matching handler
	for pattern, handler := range a.handlers {
		if a.matchTopic(pattern, topic) {
			if err := handler(topic, payload); err != nil {
				a.logger.Error("Error handling MQTT message", 
					"topic", topic, 
					"error", err,
				)
			}
			return
		}
	}

	a.logger.Debug("No handler found for MQTT topic", "topic", topic)
}

// handleTelemetry processes device telemetry data
func (a *Adapter) handleTelemetry(topic string, payload []byte) error {
	deviceID := a.extractDeviceID(topic)

	var telemetry map[string]interface{}
	if err := json.Unmarshal(payload, &telemetry); err != nil {
		return err
	}

	// Add device ID if not present
	if _, exists := telemetry["device_id"]; !exists {
		telemetry["device_id"] = deviceID
	}

	// Forward to telemetry service via HTTP
	return a.forwardToService("telemetry_service", 
		fmt.Sprintf("/api/v1/devices/%s/telemetry", deviceID), 
		telemetry)
}

// handleDeviceStatus processes device status updates
func (a *Adapter) handleDeviceStatus(topic string, payload []byte) error {
	deviceID := a.extractDeviceID(topic)

	var statusData map[string]interface{}
	if err := json.Unmarshal(payload, &statusData); err != nil {
		return err
	}

	// Transform MQTT status format to DeviceUpdateRequest format
	updateRequest := make(map[string]interface{})
	
	// Map MQTT status to DeviceStatus enum
	if mqttStatus, exists := statusData["status"]; exists {
		switch mqttStatus {
		case "online":
			updateRequest["status"] = "active"
		case "offline":
			updateRequest["status"] = "inactive"
		case "error":
			updateRequest["status"] = "error"
		case "maintenance":
			updateRequest["status"] = "maintenance"
		default:
			updateRequest["status"] = "active" // default fallback
		}
	}

	// Set firmware version if provided
	if fw, exists := statusData["firmware_version"]; exists {
		updateRequest["firmware_version"] = fw
	}

	// Put other device metrics into metadata
	metadata := make(map[string]interface{})
	
	// Move device-specific fields to metadata
	if battery, exists := statusData["battery_level"]; exists {
		metadata["battery_level"] = battery
	}
	if signal, exists := statusData["signal_strength"]; exists {
		metadata["signal_strength"] = signal
	}
	if lastSeen, exists := statusData["last_seen"]; exists {
		metadata["last_seen"] = lastSeen
	}
	if timestamp, exists := statusData["timestamp"]; exists {
		metadata["timestamp"] = timestamp
	}

	// Add metadata if we have any
	if len(metadata) > 0 {
		updateRequest["metadata"] = metadata
	}

	// Forward to device management service - using PUT to update device info
	return a.forwardToServiceWithMethod("device_service", 
		fmt.Sprintf("/api/v1/devices/%s", deviceID), 
		"PUT",
		updateRequest)
}

// handleCommandResponse processes command responses from devices
func (a *Adapter) handleCommandResponse(topic string, payload []byte) error {
	deviceID := a.extractDeviceID(topic)

	var response map[string]interface{}
	if err := json.Unmarshal(payload, &response); err != nil {
		return err
	}

	a.logger.Info("Command response received", 
		"device_id", deviceID, 
		"response", response,
	)

	// Store or forward command response as needed
	// This could be forwarded to a command tracking service
	return nil
}

// handleDeviceAuth handles device authentication requests
func (a *Adapter) handleDeviceAuth(topic string, payload []byte) error {
	deviceID := a.extractDeviceID(topic)

	var authData map[string]interface{}
	if err := json.Unmarshal(payload, &authData); err != nil {
		return err
	}

	// Forward to auth service for device authentication
	authResult, err := a.authenticateDevice(deviceID, authData)
	if err != nil {
		// Send auth failure response
		return a.Publish(fmt.Sprintf("devices/%s/auth/response", deviceID), map[string]interface{}{
			"success": false,
			"error":   err.Error(),
		})
	}

	// Send auth success response
	return a.Publish(fmt.Sprintf("devices/%s/auth/response", deviceID), authResult)
}

// handleDeviceRegistration handles new device registration
func (a *Adapter) handleDeviceRegistration(topic string, payload []byte) error {
	var regData map[string]interface{}
	if err := json.Unmarshal(payload, &regData); err != nil {
		return err
	}

	// Forward to device management service for registration
	result, err := a.registerDevice(regData)
	if err != nil {
		a.logger.Error("Device registration failed", "error", err)
		return err
	}

	// Send registration result back to device if device_id is available
	if deviceID, ok := result["device_id"].(string); ok {
		return a.Publish(fmt.Sprintf("devices/%s/register/response", deviceID), result)
	}

	a.logger.Info("Device registration completed", "result", result)
	return nil
}

// SendCommandToDevice sends a command to a device via MQTT
func (a *Adapter) SendCommandToDevice(deviceID string, command map[string]interface{}) error {
	topic := fmt.Sprintf("devices/%s/commands", deviceID)
	return a.Publish(topic, command)
}

// Connection event handlers
func (a *Adapter) onConnect(client mqtt.Client) {
	a.logger.Info("MQTT client connected")
	a.isConnected = true

	// Subscribe to all configured topics
	topics := []string{
		a.config.Topics.DeviceTelemetry,
		a.config.Topics.DeviceStatus,
		a.config.Topics.DeviceCommandsResponse,
		a.config.Topics.DeviceAuth,
		a.config.Topics.DeviceRegistration,
		a.config.Topics.NotificationUserAck,
		a.config.Topics.NotificationSystem,
	}

	for _, topic := range topics {
		if handler, exists := a.handlers[topic]; exists {
			if err := a.Subscribe(topic, handler); err != nil {
				a.logger.Error("Failed to subscribe to topic", "topic", topic, "error", err)
			}
		}
	}
}

func (a *Adapter) onConnectionLost(client mqtt.Client, err error) {
	a.logger.Warn("MQTT connection lost", "error", err)
	a.isConnected = false
}

func (a *Adapter) onReconnecting(client mqtt.Client, opts *mqtt.ClientOptions) {
	a.logger.Info("MQTT client reconnecting...")
}

// Helper functions

func (a *Adapter) matchTopic(pattern, topic string) bool {
	patternParts := strings.Split(pattern, "/")
	topicParts := strings.Split(topic, "/")

	if len(patternParts) != len(topicParts) {
		return false
	}

	for i, part := range patternParts {
		if part != "+" && part != "#" && part != topicParts[i] {
			return false
		}
		if part == "#" {
			return true // # matches everything after
		}
	}

	return true
}

func (a *Adapter) extractDeviceID(topic string) string {
	parts := strings.Split(topic, "/")
	if len(parts) >= 2 && parts[0] == "devices" {
		return parts[1]
	}
	return ""
}

// forwardToService forwards a message to an HTTP service
func (a *Adapter) forwardToService(serviceName, endpoint string, data interface{}) error {
	if !a.deviceConfig.Enabled {
		a.logger.Debug("Device management disabled, skipping service forward")
		return nil
	}

	var serviceEndpoint *config.ServiceEndpoint
	switch serviceName {
	case "device_service":
		serviceEndpoint = &a.deviceConfig.DeviceService
	case "telemetry_service":
		serviceEndpoint = &a.deviceConfig.TelemetryService
	case "ota_service":
		serviceEndpoint = &a.deviceConfig.OTAService
	default:
		return fmt.Errorf("unknown service: %s", serviceName)
	}

	url := fmt.Sprintf("http://%s:%d%s", 
		serviceEndpoint.Host, 
		serviceEndpoint.HTTPPort, 
		endpoint)

	jsonData, err := json.Marshal(data)
	if err != nil {
		return fmt.Errorf("failed to marshal data: %v", err)
	}

	req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("failed to create request: %v", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "ISA-Gateway-MQTT-Adapter")
	// Add JWT authentication for service-to-service communication
	req.Header.Set("Authorization", "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzU5MTE0MjM3LCJzdWIiOiJnYXRld2F5X21xdHRfYWRhcHRlciIsImVtYWlsIjoiZ2F0ZXdheUBpc2EtY2xvdWQubG9jYWwiLCJyb2xlIjoiYXV0aGVudGljYXRlZCIsImlzcyI6InN1cGFiYXNlIiwiaWF0IjoxNzU5MDI3ODM3fQ.bPflqi4BOCOmSv4xfXEqbxbSBn6c1cwz_c4wS3q6Pc8")

	resp, err := a.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("failed to forward to service: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("service returned error: %d", resp.StatusCode)
	}

	a.logger.Debug("Successfully forwarded to service", 
		"service", serviceName, 
		"endpoint", endpoint,
		"status", resp.StatusCode,
	)

	return nil
}

// forwardToServiceWithMethod forwards data to service with custom HTTP method
func (a *Adapter) forwardToServiceWithMethod(serviceName, endpoint, method string, data interface{}) error {
	if !a.deviceConfig.Enabled {
		a.logger.Debug("Device management disabled, skipping service forward")
		return nil
	}

	var serviceEndpoint *config.ServiceEndpoint
	switch serviceName {
	case "device_service":
		serviceEndpoint = &a.deviceConfig.DeviceService
	case "telemetry_service":
		serviceEndpoint = &a.deviceConfig.TelemetryService
	case "ota_service":
		serviceEndpoint = &a.deviceConfig.OTAService
	default:
		return fmt.Errorf("unknown service: %s", serviceName)
	}

	url := fmt.Sprintf("http://%s:%d%s", 
		serviceEndpoint.Host, 
		serviceEndpoint.HTTPPort, 
		endpoint)

	jsonData, err := json.Marshal(data)
	if err != nil {
		return fmt.Errorf("failed to marshal data: %v", err)
	}

	req, err := http.NewRequest(method, url, bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("failed to create request: %v", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "ISA-Gateway-MQTT-Adapter")
	// Add JWT authentication for service-to-service communication
	req.Header.Set("Authorization", "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzU5MTE0MjM3LCJzdWIiOiJnYXRld2F5X21xdHRfYWRhcHRlciIsImVtYWlsIjoiZ2F0ZXdheUBpc2EtY2xvdWQubG9jYWwiLCJyb2xlIjoiYXV0aGVudGljYXRlZCIsImlzcyI6InN1cGFiYXNlIiwiaWF0IjoxNzU5MDI3ODM3fQ.bPflqi4BOCOmSv4xfXEqbxbSBn6c1cwz_c4wS3q6Pc8")

	resp, err := a.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("failed to forward to service: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("service returned error: %d", resp.StatusCode)
	}

	a.logger.Debug("Successfully forwarded to service", 
		"service", serviceName, 
		"endpoint", endpoint,
		"method", method,
		"status", resp.StatusCode,
	)

	return nil
}

// authenticateDevice authenticates a device via device management service
func (a *Adapter) authenticateDevice(deviceID string, authData map[string]interface{}) (map[string]interface{}, error) {
	// Forward to device management service for authentication
	// The device management service will handle auth-service integration
	
	url := fmt.Sprintf("http://%s:%d/api/v1/devices/auth",
		a.deviceConfig.DeviceService.Host,
		a.deviceConfig.DeviceService.HTTPPort)
	
	// Ensure device_id is in the auth data
	authData["device_id"] = deviceID
	
	jsonData, err := json.Marshal(authData)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal auth data: %v", err)
	}
	
	req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create auth request: %v", err)
	}
	
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "ISA-Gateway-MQTT-Adapter")
	
	resp, err := a.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to authenticate device: %v", err)
	}
	defer resp.Body.Close()
	
	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode auth response: %v", err)
	}
	
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("authentication failed: status %d", resp.StatusCode)
	}
	
	a.logger.Debug("Device authenticated successfully",
		"device_id", deviceID,
		"status", resp.StatusCode,
	)
	
	return result, nil
}

// handleNotificationAck processes user acknowledgment of notifications
func (a *Adapter) handleNotificationAck(topic string, payload []byte) error {
	userID := a.extractUserID(topic)

	var ackData map[string]interface{}
	if err := json.Unmarshal(payload, &ackData); err != nil {
		return err
	}

	// Add user ID if not present
	if _, exists := ackData["user_id"]; !exists {
		ackData["user_id"] = userID
	}

	a.logger.Info("Notification acknowledgment received",
		"user_id", userID,
		"ack_data", ackData,
	)

	// Forward to notification service via HTTP
	return a.forwardToNotificationService(
		fmt.Sprintf("/api/v1/notifications/ack/%s", userID),
		ackData)
}

// handleSystemNotification processes system notification requests
func (a *Adapter) handleSystemNotification(topic string, payload []byte) error {
	var notification map[string]interface{}
	if err := json.Unmarshal(payload, &notification); err != nil {
		return err
	}

	a.logger.Info("System notification received",
		"topic", topic,
		"notification", notification,
	)

	// Forward to notification service for processing
	return a.forwardToNotificationService("/api/v1/notifications/system", notification)
}

// PublishNotificationToUser sends notification to specific user via MQTT
func (a *Adapter) PublishNotificationToUser(userID string, notification map[string]interface{}) error {
	topic := fmt.Sprintf("notifications/users/%s/receive", userID)
	a.logger.Debug("Publishing notification to user",
		"user_id", userID,
		"topic", topic,
	)
	return a.Publish(topic, notification)
}

// PublishBroadcastNotification sends notification to all users via MQTT
func (a *Adapter) PublishBroadcastNotification(notification map[string]interface{}) error {
	topic := "notifications/broadcast"
	a.logger.Debug("Publishing broadcast notification", "topic", topic)
	return a.Publish(topic, notification)
}

// PublishSystemNotification sends system notification via MQTT
func (a *Adapter) PublishSystemNotification(systemID string, notification map[string]interface{}) error {
	topic := fmt.Sprintf("notifications/system/%s", systemID)
	a.logger.Debug("Publishing system notification",
		"system_id", systemID,
		"topic", topic,
	)
	return a.Publish(topic, notification)
}

// extractUserID extracts user ID from notification topic
func (a *Adapter) extractUserID(topic string) string {
	// Topic format: notifications/users/{user_id}/...
	parts := strings.Split(topic, "/")
	if len(parts) >= 3 && parts[0] == "notifications" && parts[1] == "users" {
		return parts[2]
	}
	return ""
}

// forwardToNotificationService forwards data to notification service via HTTP
func (a *Adapter) forwardToNotificationService(endpoint string, data interface{}) error {
	// Use gateway's notification service configuration
	url := fmt.Sprintf("http://localhost:8206%s", endpoint)

	jsonData, err := json.Marshal(data)
	if err != nil {
		return fmt.Errorf("failed to marshal data: %v", err)
	}

	req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("failed to create request: %v", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "ISA-Gateway-MQTT-Adapter")
	// Add JWT authentication for service-to-service communication
	req.Header.Set("Authorization", "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzU5MTE0MjM3LCJzdWIiOiJnYXRld2F5X21xdHRfYWRhcHRlciIsImVtYWlsIjoiZ2F0ZXdheUBpc2EtY2xvdWQubG9jYWwiLCJyb2xlIjoiYXV0aGVudGljYXRlZCIsImlzcyI6InN1cGFiYXNlIiwiaWF0IjoxNzU5MDI3ODM3fQ.bPflqi4BOCOmSv4xfXEqbxbSBn6c1cwz_c4wS3q6Pc8")

	resp, err := a.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("failed to forward to notification service: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("notification service returned error: %d", resp.StatusCode)
	}

	a.logger.Debug("Successfully forwarded to notification service",
		"endpoint", endpoint,
		"status", resp.StatusCode,
	)

	return nil
}

// registerDevice registers a new device via device management service
func (a *Adapter) registerDevice(regData map[string]interface{}) (map[string]interface{}, error) {
	// Forward to device management service
	url := fmt.Sprintf("http://%s:%d/api/v1/devices",
		a.deviceConfig.DeviceService.Host,
		a.deviceConfig.DeviceService.HTTPPort)
	
	jsonData, err := json.Marshal(regData)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal registration data: %v", err)
	}
	
	req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create registration request: %v", err)
	}
	
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "ISA-Gateway-MQTT-Adapter")
	// Note: Device self-registration might not require user auth
	// The device management service should handle this case
	
	resp, err := a.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to register device: %v", err)
	}
	defer resp.Body.Close()
	
	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode registration response: %v", err)
	}
	
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("registration failed: status %d", resp.StatusCode)
	}
	
	a.logger.Debug("Device registered successfully",
		"result", result,
		"status", resp.StatusCode,
	)
	
	return result, nil
}

// IsConnected returns the connection status
func (a *Adapter) IsConnected() bool {
	return a.isConnected && a.client != nil && a.client.IsConnected()
}

// GetStats returns adapter statistics including notification topics
func (a *Adapter) GetStats() map[string]interface{} {
	a.mu.RLock()
	defer a.mu.RUnlock()

	return map[string]interface{}{
		"connected":        a.IsConnected(),
		"broker_url":       a.config.BrokerURL,
		"client_id":        a.config.ClientID,
		"subscribed_topics": len(a.handlers),
		"qos":              a.config.QoS,
		"topics": map[string]interface{}{
			"device_telemetry":          a.config.Topics.DeviceTelemetry,
			"device_status":             a.config.Topics.DeviceStatus,
			"device_commands":           a.config.Topics.DeviceCommands,
			"device_auth":               a.config.Topics.DeviceAuth,
			"device_registration":       a.config.Topics.DeviceRegistration,
			"notification_user_receive": a.config.Topics.NotificationUserReceive,
			"notification_user_ack":     a.config.Topics.NotificationUserAck,
			"notification_broadcast":    a.config.Topics.NotificationBroadcast,
			"notification_system":       a.config.Topics.NotificationSystem,
		},
	}
}