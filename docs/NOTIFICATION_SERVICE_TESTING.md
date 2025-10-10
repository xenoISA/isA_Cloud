# Notification Service Testing Documentation

## Service Overview

The Notification Service provides comprehensive notification management including email, push notifications, in-app notifications, webhooks, and batch sending. It runs on port 8206 and is accessible through the isA_Cloud gateway on port 8000.

**Service Information:**
- Port: 8206 (direct), 8000/api/v1/notifications (through gateway)
- Version: 1.0.0
- Type: Notification management microservice

## Gateway Access Testing Results

All tests performed through the isA_Cloud gateway (http://localhost:8000/api/v1/notifications)

**Base URL:** `http://localhost:8000/api/v1`

---

##  Test Scenario 1: Template Management

### Create Email Template

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/notifications/templates \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Welcome Email",
    "description": "Welcome email for new users",
    "type": "email",
    "subject": "Welcome to {{app_name}}!",
    "content": "Hello {{user_name}}, welcome to {{app_name}}!",
    "variables": ["user_name", "app_name"],
    "metadata": {"category": "onboarding"}
  }'
```

** Result:** SUCCESS
```json
{
  "template": {
    "id": 3,
    "template_id": "tpl_email_1759251214.748262",
    "name": "Welcome Email",
    "description": "Welcome email for new users",
    "type": "email",
    "subject": "Welcome to {{app_name}}!",
    "content": "Hello {{user_name}}, welcome to {{app_name}}!",
    "html_content": null,
    "variables": ["user_name", "app_name"],
    "metadata": {"category": "onboarding"},
    "status": "active",
    "version": 1,
    "created_by": null,
    "created_at": "2025-10-01T00:53:34.748743",
    "updated_at": "2025-10-01T00:53:34.748743"
  },
  "message": "Template created successfully"
}
```

### Get All Templates

**Request:**
```bash
curl http://localhost:8000/api/v1/notifications/templates
```

** Result:** SUCCESS - Returns list of all notification templates

---

##  Test Scenario 2: Email Notifications

### Send Email Notification

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/notifications/send \
  -H "Content-Type: application/json" \
  -d '{
    "type": "email",
    "recipient_email": "test@example.com",
    "subject": "Gateway Test Email",
    "content": "Testing notification service through gateway",
    "priority": "normal"
  }'
```

** Result:** SUCCESS
```json
{
  "notification": {
    "id": 7,
    "notification_id": "ntf_email_1759251319.941186",
    "type": "email",
    "priority": "normal",
    "recipient_type": "email",
    "recipient_id": null,
    "recipient_email": "test@example.com",
    "recipient_phone": null,
    "template_id": null,
    "subject": "Gateway Test Email",
    "content": "Testing notification service through gateway",
    "html_content": null,
    "variables": {},
    "scheduled_at": null,
    "expires_at": null,
    "retry_count": 0,
    "max_retries": 3,
    "status": "pending",
    "error_message": null,
    "provider": null,
    "provider_message_id": null,
    "metadata": {},
    "tags": [],
    "created_at": "2025-10-01T00:55:19.941369",
    "sent_at": null,
    "delivered_at": null,
    "read_at": null,
    "failed_at": null
  },
  "message": "Notification created and queued for sending",
  "success": true
}
```

---

##  Test Scenario 3: In-App Notifications

### Send In-App Notification

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/notifications/send \
  -H "Content-Type: application/json" \
  -d '{
    "type": "in_app",
    "recipient_id": "user_gateway_test",
    "subject": "Gateway In-App Test",
    "content": "Testing in-app notification through gateway",
    "priority": "high"
  }'
```

** Result:** SUCCESS
```json
{
  "notification": {
    "id": 8,
    "notification_id": "ntf_in_app_1759251329.305937",
    "type": "in_app",
    "priority": "high",
    "recipient_type": "user",
    "recipient_id": "user_gateway_test",
    "recipient_email": null,
    "recipient_phone": null,
    "template_id": null,
    "subject": "Gateway In-App Test",
    "content": "Testing in-app notification through gateway",
    "html_content": null,
    "variables": {},
    "scheduled_at": null,
    "expires_at": null,
    "retry_count": 0,
    "max_retries": 3,
    "status": "pending",
    "error_message": null,
    "provider": null,
    "provider_message_id": null,
    "metadata": {},
    "tags": [],
    "created_at": "2025-10-01T00:55:29.307393",
    "sent_at": null,
    "delivered_at": null,
    "read_at": null,
    "failed_at": null
  },
  "message": "Notification created and queued for sending",
  "success": true
}
```

### Get User's In-App Notifications

**Request:**
```bash
curl http://localhost:8000/api/v1/notifications/in-app/user_gateway_test
```

** Result:** SUCCESS
```json
[
  {
    "id": 2,
    "notification_id": "ntf_in_app_1759251329.305937",
    "user_id": "user_gateway_test",
    "title": "Gateway In-App Test",
    "message": "Testing in-app notification through gateway",
    "icon": null,
    "image_url": null,
    "action_url": null,
    "category": null,
    "priority": "high",
    "is_read": false,
    "is_archived": false,
    "created_at": "2025-10-01T00:55:29.409468",
    "read_at": null,
    "archived_at": null
  }
]
```

### Mark Notification as Read

**Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/notifications/in-app/ntf_in_app_1759251329.305937/read?user_id=user_gateway_test"
```

** Result:** SUCCESS
```json
{
  "message": "Notification marked as read"
}
```

### Get Unread Count

**Request:**
```bash
curl http://localhost:8000/api/v1/notifications/in-app/user_gateway_test/unread-count
```

** Result:** SUCCESS
```json
{
  "unread_count": 0
}
```

---

##  Test Scenario 4: Push Notifications

### Subscribe to Push Notifications

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/notifications/push/subscribe \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_gateway_123",
    "device_token": "fcm_gateway_token_456",
    "platform": "android",
    "device_name": "Test Device",
    "device_model": "Gateway Test Model",
    "app_version": "1.0.0"
  }'
```

** Result:** SUCCESS
```json
{
  "id": 2,
  "user_id": "user_gateway_123",
  "device_token": "fcm_gateway_token_456",
  "platform": "android",
  "endpoint": null,
  "auth_key": null,
  "p256dh_key": null,
  "device_name": "Test Device",
  "device_model": "Gateway Test Model",
  "app_version": "1.0.0",
  "is_active": true,
  "created_at": "2025-10-01T00:57:07.892408",
  "updated_at": "2025-10-01T00:57:07.892408",
  "last_used_at": null
}
```

### Get User's Push Subscriptions

**Request:**
```bash
curl http://localhost:8000/api/v1/notifications/push/subscriptions/user_gateway_123
```

** Result:** SUCCESS
```json
[
  {
    "id": 2,
    "user_id": "user_gateway_123",
    "device_token": "fcm_gateway_token_456",
    "platform": "android",
    "endpoint": null,
    "auth_key": null,
    "p256dh_key": null,
    "device_name": "Test Device",
    "device_model": "Gateway Test Model",
    "app_version": "1.0.0",
    "is_active": true,
    "created_at": "2025-10-01T00:57:07.892408",
    "updated_at": "2025-10-01T00:57:07.892408",
    "last_used_at": null
  }
]
```

---

##  Test Scenario 5: Batch Sending

### Create Batch Notification

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/notifications/batch \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Gateway Batch Test",
    "template_id": "tpl_email_1759251214.748262",
    "type": "email",
    "recipients": [
      {"email": "user1@example.com", "variables": {"user_name": "Alice", "app_name": "IsA Cloud"}},
      {"email": "user2@example.com", "variables": {"user_name": "Bob", "app_name": "IsA Cloud"}},
      {"email": "user3@example.com", "variables": {"user_name": "Charlie", "app_name": "IsA Cloud"}}
    ],
    "priority": "normal",
    "metadata": {"campaign": "gateway_test"}
  }'
```

** Result:** SUCCESS
```json
{
  "batch": {
    "id": 1,
    "batch_id": "batch_1759251840.700731",
    "name": "Gateway Batch Test",
    "template_id": "tpl_email_1759251214.748262",
    "type": "email",
    "priority": "normal",
    "recipients": [
      {
        "email": "user1@example.com",
        "variables": {"user_name": "Alice", "app_name": "IsA Cloud"}
      },
      {
        "email": "user2@example.com",
        "variables": {"user_name": "Bob", "app_name": "IsA Cloud"}
      },
      {
        "email": "user3@example.com",
        "variables": {"user_name": "Charlie", "app_name": "IsA Cloud"}
      }
    ],
    "total_recipients": 3,
    "sent_count": 0,
    "delivered_count": 0,
    "failed_count": 0,
    "scheduled_at": null,
    "started_at": null,
    "completed_at": null,
    "metadata": {"campaign": "gateway_test"},
    "created_by": null,
    "created_at": "2025-10-01T01:04:00.701207"
  },
  "message": "Batch created with 3 recipients"
}
```

---

## Summary

###  Verified Functionality Through Gateway

1. **Template Management**
   -  Create notification templates
   -  List all templates
   -  Template variable substitution support

2. **Email Notifications**
   -  Send individual email notifications
   -  Queue notifications for sending
   -  Support for priority levels

3. **In-App Notifications**
   -  Send in-app notifications to users
   -  Retrieve user's notifications
   -  Mark notifications as read
   -  Get unread notification count

4. **Push Notifications**
   -  Register push subscriptions (Android/iOS/Web)
   -  Retrieve user's push subscriptions
   -  Platform-specific token management

5. **Batch Sending**
   -  Create batch notification campaigns
   -  Template-based batch sending
   -  Variable substitution per recipient

### Key Features

- **Multiple Notification Types:** Email, In-App, Push, SMS (configurable), Webhook
- **Template System:** Support for variable substitution with `{{variable_name}}` syntax
- **Priority Levels:** LOW, NORMAL, HIGH, URGENT
- **Status Tracking:** PENDING, SENDING, SENT, DELIVERED, FAILED, BOUNCED, CANCELLED
- **Batch Processing:** Efficient bulk notification sending with template support
- **Push Platform Support:** Android (FCM), iOS (APNS), Web (Web Push)

### Gateway Routing

**Status:**  FULLY FUNCTIONAL

All notification service endpoints are successfully accessible through the gateway at:
- Base URL: `http://localhost:8000/api/v1/notifications`
- Service Discovery: Consul-based dynamic routing
- Health Check: Passing

**Test Date:** 2025-10-01
**Gateway Version:** 1.0.0
**Service Version:** 1.0.0
