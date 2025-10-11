// MQTT SDK 使用示例
//
// 这个示例展示了如何使用 MQTT SDK 进行设备通信和消息传递
//
// 运行示例:
//
//	go run examples/go/mqtt_client_example.go
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"time"

	"github.com/isa-cloud/isa_cloud/pkg/infrastructure/messaging/mqtt"
)

// SensorData 传感器数据结构
type SensorData struct {
	DeviceID    string  `json:"device_id"`
	Temperature float64 `json:"temperature"`
	Humidity    float64 `json:"humidity"`
	Timestamp   int64   `json:"timestamp"`
}

// DeviceCommand 设备命令结构
type DeviceCommand struct {
	Action string                 `json:"action"`
	Params map[string]interface{} `json:"params"`
}

func main() {
	fmt.Println("=== MQTT SDK 使用示例 ===\n")

	// 1. 创建 MQTT 客户端（发布者）
	publisherCfg := &mqtt.Config{
		BrokerURL:     "tcp://localhost:1883",
		ClientID:      "publisher-demo",
		Username:      "",
		Password:      "",
		QoS:           1,
		AutoReconnect: true,
		CleanSession:  true,

		// 设置遗嘱消息
		WillEnabled: true,
		WillTopic:   "devices/publisher-demo/status",
		WillPayload: "offline",
		WillQoS:     1,
		WillRetain:  true,
	}

	publisher, err := mqtt.NewClient(publisherCfg)
	if err != nil {
		log.Fatalf("Failed to create publisher: %v", err)
	}
	defer publisher.Close()
	fmt.Println("✓ 发布者客户端创建成功")

	// 2. 创建 MQTT 客户端（订阅者）
	subscriberCfg := &mqtt.Config{
		BrokerURL:     "tcp://localhost:1883",
		ClientID:      "subscriber-demo",
		QoS:           1,
		AutoReconnect: true,
	}

	subscriber, err := mqtt.NewClient(subscriberCfg)
	if err != nil {
		log.Fatalf("Failed to create subscriber: %v", err)
	}
	defer subscriber.Close()
	fmt.Println("✓ 订阅者客户端创建成功")

	// 3. 发布在线状态
	fmt.Println("\n--- 发布设备状态 ---")
	err = publisher.Publish("devices/publisher-demo/status", "online", true)
	if err != nil {
		log.Printf("Failed to publish status: %v", err)
	} else {
		fmt.Println("✓ 设备状态发布成功")
	}

	// 4. 订阅传感器数据（使用通配符）
	fmt.Println("\n--- 订阅传感器数据 ---")
	err = subscriber.Subscribe("sensors/+/telemetry", func(topic string, payload []byte) error {
		fmt.Printf("📊 收到传感器数据: %s\n", topic)

		var data SensorData
		if err := json.Unmarshal(payload, &data); err != nil {
			log.Printf("Failed to unmarshal: %v", err)
			return err
		}

		fmt.Printf("   设备: %s, 温度: %.1f°C, 湿度: %.1f%%\n",
			data.DeviceID, data.Temperature, data.Humidity)

		return nil
	})
	if err != nil {
		log.Printf("Failed to subscribe: %v", err)
	} else {
		fmt.Println("✓ 订阅 sensors/+/telemetry 成功")
	}

	// 5. 订阅设备命令
	fmt.Println("\n--- 订阅设备命令 ---")
	err = subscriber.Subscribe("devices/sensor001/commands", func(topic string, payload []byte) error {
		fmt.Printf("📨 收到设备命令: %s\n", topic)

		var cmd DeviceCommand
		if err := json.Unmarshal(payload, &cmd); err != nil {
			log.Printf("Failed to unmarshal command: %v", err)
			return err
		}

		fmt.Printf("   动作: %s, 参数: %v\n", cmd.Action, cmd.Params)

		// 执行命令
		switch cmd.Action {
		case "update_config":
			fmt.Println("   → 执行配置更新")
		case "restart":
			fmt.Println("   → 执行设备重启")
		case "get_status":
			fmt.Println("   → 获取设备状态")
		default:
			fmt.Printf("   ⚠ 未知命令: %s\n", cmd.Action)
		}

		return nil
	})
	if err != nil {
		log.Printf("Failed to subscribe commands: %v", err)
	} else {
		fmt.Println("✓ 订阅 devices/sensor001/commands 成功")
	}

	// 6. 批量订阅
	fmt.Println("\n--- 批量订阅多个主题 ---")
	filters := map[string]byte{
		"devices/+/status": 1,
		"alerts/#":         2,
		"events/system/#":  1,
	}
	err = subscriber.SubscribeMultiple(filters, func(topic string, payload []byte) error {
		fmt.Printf("📬 批量订阅收到消息: %s = %s\n", topic, string(payload))
		return nil
	})
	if err != nil {
		log.Printf("Failed to subscribe multiple: %v", err)
	} else {
		fmt.Println("✓ 批量订阅成功")
	}

	// 等待订阅生效
	time.Sleep(1 * time.Second)

	// 7. 发布传感器数据（JSON 对象）
	fmt.Println("\n--- 发布传感器遥测数据 ---")
	for i := 1; i <= 3; i++ {
		sensorData := SensorData{
			DeviceID:    fmt.Sprintf("sensor%03d", i),
			Temperature: 20.0 + float64(i)*2.5,
			Humidity:    50.0 + float64(i)*5.0,
			Timestamp:   time.Now().Unix(),
		}

		topic := fmt.Sprintf("sensors/sensor%03d/telemetry", i)
		err = publisher.Publish(topic, sensorData, false)
		if err != nil {
			log.Printf("Failed to publish sensor data: %v", err)
		} else {
			fmt.Printf("✓ 传感器数据发布成功: %s\n", topic)
		}

		time.Sleep(500 * time.Millisecond)
	}

	// 8. 发布设备命令
	fmt.Println("\n--- 发布设备命令 ---")
	commands := []DeviceCommand{
		{
			Action: "update_config",
			Params: map[string]interface{}{
				"refresh_rate": 30,
				"mode":         "high_performance",
			},
		},
		{
			Action: "get_status",
			Params: map[string]interface{}{},
		},
		{
			Action: "restart",
			Params: map[string]interface{}{
				"delay": 10,
			},
		},
	}

	for _, cmd := range commands {
		err = publisher.PublishWithQoS("devices/sensor001/commands", cmd, 2, false)
		if err != nil {
			log.Printf("Failed to publish command: %v", err)
		} else {
			fmt.Printf("✓ 命令发布成功: %s\n", cmd.Action)
		}
		time.Sleep(500 * time.Millisecond)
	}

	// 9. 发布不同 QoS 级别的消息
	fmt.Println("\n--- 测试不同 QoS 级别 ---")
	qosLevels := []struct {
		qos         byte
		description string
	}{
		{0, "QoS 0 - 最多一次"},
		{1, "QoS 1 - 至少一次"},
		{2, "QoS 2 - 恰好一次"},
	}

	for _, level := range qosLevels {
		msg := fmt.Sprintf("测试消息 - %s", level.description)
		err = publisher.PublishWithQoS("test/qos", msg, level.qos, false)
		if err != nil {
			log.Printf("Failed to publish QoS %d: %v", level.qos, err)
		} else {
			fmt.Printf("✓ %s 发布成功\n", level.description)
		}
	}

	// 10. 发布告警消息
	fmt.Println("\n--- 发布告警消息 ---")
	alerts := []struct {
		level   string
		message string
	}{
		{"info", "系统启动完成"},
		{"warning", "内存使用率超过 80%"},
		{"critical", "磁盘空间不足"},
	}

	for _, alert := range alerts {
		topic := fmt.Sprintf("alerts/%s", alert.level)
		alertData := map[string]interface{}{
			"level":     alert.level,
			"message":   alert.message,
			"timestamp": time.Now().Unix(),
		}

		err = publisher.Publish(topic, alertData, false)
		if err != nil {
			log.Printf("Failed to publish alert: %v", err)
		} else {
			fmt.Printf("✓ 告警发布成功: [%s] %s\n", alert.level, alert.message)
		}
		time.Sleep(300 * time.Millisecond)
	}

	// 11. 发布系统事件
	fmt.Println("\n--- 发布系统事件 ---")
	events := []string{
		"events/system/startup",
		"events/system/config/updated",
		"events/system/maintenance/scheduled",
	}

	for _, topic := range events {
		eventData := map[string]interface{}{
			"event":     mqtt.ExtractTopicParts(topic)[2],
			"timestamp": time.Now().Unix(),
		}

		err = publisher.Publish(topic, eventData, false)
		if err != nil {
			log.Printf("Failed to publish event: %v", err)
		} else {
			fmt.Printf("✓ 事件发布成功: %s\n", topic)
		}
		time.Sleep(300 * time.Millisecond)
	}

	// 12. 保留消息示例
	fmt.Println("\n--- 发布保留消息 ---")
	config := map[string]interface{}{
		"refresh_rate": 60,
		"mode":         "standard",
		"enabled":      true,
	}
	err = publisher.Publish("devices/sensor001/config", config, true)
	if err != nil {
		log.Printf("Failed to publish retained message: %v", err)
	} else {
		fmt.Println("✓ 保留消息发布成功（新订阅者会立即收到）")
	}

	// 13. 主题提取工具示例
	fmt.Println("\n--- 主题解析工具 ---")
	testTopics := []string{
		"devices/dev123/telemetry",
		"sensors/room1/temperature",
		"alerts/critical",
	}

	for _, topic := range testTopics {
		parts := mqtt.ExtractTopicParts(topic)
		fmt.Printf("主题: %s\n", topic)
		fmt.Printf("  层级: %v\n", parts)

		if parts[0] == "devices" {
			deviceID := mqtt.ExtractDeviceID(topic)
			fmt.Printf("  设备ID: %s\n", deviceID)
		}
	}

	// 14. 检查连接状态
	fmt.Println("\n--- 客户端状态 ---")
	if publisher.IsConnected() {
		fmt.Println("✓ 发布者已连接")
	}
	if subscriber.IsConnected() {
		fmt.Println("✓ 订阅者已连接")
	}

	// 15. 获取统计信息
	fmt.Println("\n--- 客户端统计 ---")
	pubStats := publisher.GetStats()
	fmt.Printf("发布者:\n")
	fmt.Printf("  连接状态: %v\n", pubStats["connected"])
	fmt.Printf("  客户端ID: %v\n", pubStats["client_id"])

	subStats := subscriber.GetStats()
	fmt.Printf("订阅者:\n")
	fmt.Printf("  连接状态: %v\n", subStats["connected"])
	fmt.Printf("  订阅主题数: %v\n", subStats["subscribed_topics"])

	// 16. 健康检查
	fmt.Println("\n--- 健康检查 ---")
	ctx := context.Background()
	err = publisher.Ping(ctx)
	if err != nil {
		log.Printf("⚠ 发布者健康检查失败: %v", err)
	} else {
		fmt.Println("✓ 发布者健康检查通过")
	}

	// 等待消息处理
	fmt.Println("\n等待消息处理...")
	time.Sleep(3 * time.Second)

	// 17. 取消订阅
	fmt.Println("\n--- 取消订阅 ---")
	err = subscriber.Unsubscribe("sensors/+/telemetry")
	if err != nil {
		log.Printf("Failed to unsubscribe: %v", err)
	} else {
		fmt.Println("✓ 取消订阅成功")
	}

	fmt.Println("\n=== 示例完成 ===")
	fmt.Println("\n提示: 订阅的消息处理器会继续运行，按 Ctrl+C 退出")

	// 保持运行一段时间以接收可能的消息
	time.Sleep(5 * time.Second)
}
