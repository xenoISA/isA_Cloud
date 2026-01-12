//go:build unit

// Package golden provides unit tests for Redis service contracts.
package golden

import (
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	redis_contract "github.com/isa-cloud/isa_cloud/tests/contracts/redis"
)

// ===================================================================================
// TEST: DATA FACTORY - Redis
// ===================================================================================

func TestRedisTestDataFactory_MakeSetRequest(t *testing.T) {
	factory := redis_contract.NewTestDataFactory()

	t.Run("creates valid request with defaults", func(t *testing.T) {
		req := factory.MakeSetRequest()

		assert.NotEmpty(t, req.UserId, "user_id should not be empty")
		assert.NotEmpty(t, req.OrganizationId, "organization_id should not be empty")
		assert.NotEmpty(t, req.Key, "key should not be empty")
		assert.NotEmpty(t, req.Value, "value should not be empty")
	})

	t.Run("accepts custom key via option", func(t *testing.T) {
		customKey := "my-custom-key"
		req := factory.MakeSetRequest(redis_contract.WithKey(customKey))

		assert.Equal(t, customKey, req.Key)
	})

	t.Run("accepts custom value via option", func(t *testing.T) {
		customValue := "my-custom-value"
		req := factory.MakeSetRequest(redis_contract.WithValue(customValue))

		assert.Equal(t, customValue, req.Value)
	})

	t.Run("accepts user/org override via option", func(t *testing.T) {
		userID := "custom-user"
		orgID := "custom-org"
		req := factory.MakeSetRequest(redis_contract.WithUser(userID, orgID))

		assert.Equal(t, userID, req.UserId)
		assert.Equal(t, orgID, req.OrganizationId)
	})

	t.Run("generates unique random keys", func(t *testing.T) {
		req1 := factory.MakeSetRequest(factory.WithRandomKey())
		req2 := factory.MakeSetRequest(factory.WithRandomKey())

		assert.NotEqual(t, req1.Key, req2.Key, "random keys should be unique")
	})

	t.Run("supports multiple options chained", func(t *testing.T) {
		req := factory.MakeSetRequest(
			redis_contract.WithKey("chained-key"),
			redis_contract.WithValue("chained-value"),
			redis_contract.WithUser("user-x", "org-x"),
		)

		assert.Equal(t, "chained-key", req.Key)
		assert.Equal(t, "chained-value", req.Value)
		assert.Equal(t, "user-x", req.UserId)
		assert.Equal(t, "org-x", req.OrganizationId)
	})
}

func TestRedisTestDataFactory_MakeGetRequest(t *testing.T) {
	factory := redis_contract.NewTestDataFactory()

	t.Run("creates valid request with defaults", func(t *testing.T) {
		req := factory.MakeGetRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.OrganizationId)
		assert.NotEmpty(t, req.Key)
	})

	t.Run("accepts custom key via option", func(t *testing.T) {
		customKey := "get-custom-key"
		req := factory.MakeGetRequest(redis_contract.WithGetKey(customKey))

		assert.Equal(t, customKey, req.Key)
	})

	t.Run("accepts user override via option", func(t *testing.T) {
		req := factory.MakeGetRequest(redis_contract.WithGetUser("u1", "o1"))

		assert.Equal(t, "u1", req.UserId)
		assert.Equal(t, "o1", req.OrganizationId)
	})
}

func TestRedisTestDataFactory_MakeDeleteRequest(t *testing.T) {
	factory := redis_contract.NewTestDataFactory()

	t.Run("creates valid request with defaults", func(t *testing.T) {
		req := factory.MakeDeleteRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.OrganizationId)
		assert.NotEmpty(t, req.Key)
	})

	t.Run("accepts custom key via option", func(t *testing.T) {
		req := factory.MakeDeleteRequest(redis_contract.WithDeleteKey("delete-key"))

		assert.Equal(t, "delete-key", req.Key)
	})
}

func TestRedisTestDataFactory_MakeDeleteMultipleRequest(t *testing.T) {
	factory := redis_contract.NewTestDataFactory()

	t.Run("creates valid request with defaults", func(t *testing.T) {
		req := factory.MakeDeleteMultipleRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.OrganizationId)
		assert.NotEmpty(t, req.Keys)
	})

	t.Run("accepts multiple keys via option", func(t *testing.T) {
		keys := []string{"key1", "key2", "key3"}
		req := factory.MakeDeleteMultipleRequest(redis_contract.WithDeleteKeys(keys...))

		assert.Equal(t, keys, req.Keys)
	})
}

func TestRedisTestDataFactory_MakeHSetRequest(t *testing.T) {
	factory := redis_contract.NewTestDataFactory()

	t.Run("creates valid hash request with defaults", func(t *testing.T) {
		req := factory.MakeHSetRequest()

		assert.NotEmpty(t, req.UserId)
		assert.NotEmpty(t, req.OrganizationId)
		assert.NotEmpty(t, req.Key)
		assert.NotEmpty(t, req.Fields)
	})

	t.Run("accepts custom fields via option", func(t *testing.T) {
		fields := map[string]string{
			"name":  "test",
			"value": "123",
		}
		req := factory.MakeHSetRequest(redis_contract.WithFieldsFromMap(fields))

		assert.Len(t, req.Fields, 2)
	})

	t.Run("accepts custom key via option", func(t *testing.T) {
		req := factory.MakeHSetRequest(redis_contract.WithHashKey("user:123:profile"))

		assert.Equal(t, "user:123:profile", req.Key)
	})
}

// ===================================================================================
// TEST: SCENARIOS
// ===================================================================================

func TestRedisScenarios(t *testing.T) {
	scenarios := redis_contract.NewScenarios()

	t.Run("ValidSetRequest returns usable request", func(t *testing.T) {
		req := scenarios.ValidSetRequest()

		require.NotNil(t, req)
		assert.NotEmpty(t, req.Key)
		assert.NotEmpty(t, req.Value)
	})

	t.Run("SetRequestEmptyKey for EC-001", func(t *testing.T) {
		req := scenarios.SetRequestEmptyKey()

		assert.Empty(t, req.Key, "key should be empty for edge case EC-001")
	})

	t.Run("SetRequestLongKey for EC-002", func(t *testing.T) {
		req := scenarios.SetRequestLongKey()

		assert.Greater(t, len(req.Key), 1024, "key should exceed 1024 chars for EC-002")
	})

	t.Run("MultiTenantScenario creates isolated requests", func(t *testing.T) {
		tenant1, tenant2 := scenarios.MultiTenantScenario()

		assert.Equal(t, tenant1.Key, tenant2.Key, "keys should match")
		assert.NotEqual(t, tenant1.UserId, tenant2.UserId, "user IDs should differ")
		assert.NotEqual(t, tenant1.OrganizationId, tenant2.OrganizationId, "org IDs should differ")
	})
}

// ===================================================================================
// TEST: ASSERTION HELPERS
// ===================================================================================

func TestRedisAssertionHelpers(t *testing.T) {
	t.Run("ExpectedIsolatedKey formats correctly", func(t *testing.T) {
		result := redis_contract.ExpectedIsolatedKey("org-001", "user-001", "mykey")

		assert.Equal(t, "org-001:user-001:mykey", result)
	})

	t.Run("DefaultIsolatedKey uses test defaults", func(t *testing.T) {
		result := redis_contract.DefaultIsolatedKey("mykey")

		assert.Contains(t, result, "test-org-001")
		assert.Contains(t, result, "test-user-001")
		assert.Contains(t, result, "mykey")
	})
}

// ===================================================================================
// TEST: BUSINESS RULES (from logic_contract.md)
// ===================================================================================

func TestRedisBusinessRules(t *testing.T) {
	factory := redis_contract.NewTestDataFactory()

	// BR-001: Multi-tenant Key Isolation
	t.Run("BR-001: keys are isolated by tenant", func(t *testing.T) {
		req1 := factory.MakeSetRequest(redis_contract.WithUser("user-a", "org-a"))
		req2 := factory.MakeSetRequest(redis_contract.WithUser("user-b", "org-b"))

		key1 := redis_contract.ExpectedIsolatedKey(req1.OrganizationId, req1.UserId, req1.Key)
		key2 := redis_contract.ExpectedIsolatedKey(req2.OrganizationId, req2.UserId, req2.Key)

		assert.NotEqual(t, key1, key2, "isolated keys must differ for different tenants")
	})

	// BR-002: Key Namespace Format
	t.Run("BR-002: key namespace follows org:user:key format", func(t *testing.T) {
		key := redis_contract.ExpectedIsolatedKey("myorg", "myuser", "mykey")
		parts := strings.Split(key, ":")

		require.Len(t, parts, 3)
		assert.Equal(t, "myorg", parts[0])
		assert.Equal(t, "myuser", parts[1])
		assert.Equal(t, "mykey", parts[2])
	})

	// BR-004: Required Fields
	t.Run("BR-004: SetRequest requires key and value", func(t *testing.T) {
		req := factory.MakeSetRequest()

		assert.NotEmpty(t, req.Key, "key is required")
		assert.NotEmpty(t, req.Value, "value is required")
	})

	// BR-005: Required Auth Fields
	t.Run("BR-005: requests require user_id and organization_id", func(t *testing.T) {
		req := factory.MakeSetRequest()

		assert.NotEmpty(t, req.UserId, "user_id is required for auth")
		assert.NotEmpty(t, req.OrganizationId, "organization_id is required for auth")
	})
}

// ===================================================================================
// TEST: EDGE CASES (from logic_contract.md)
// ===================================================================================

func TestRedisEdgeCases(t *testing.T) {
	scenarios := redis_contract.NewScenarios()
	factory := redis_contract.NewTestDataFactory()

	// EC-001: Empty Key
	t.Run("EC-001: empty key should be rejectable", func(t *testing.T) {
		req := scenarios.SetRequestEmptyKey()

		assert.Empty(t, req.Key)
	})

	// EC-002: Key Length Limit
	t.Run("EC-002: key exceeding 1024 chars should be rejectable", func(t *testing.T) {
		req := scenarios.SetRequestLongKey()

		assert.Greater(t, len(req.Key), 1024)
	})

	// EC-003: Empty Value (may be valid depending on use case)
	t.Run("EC-003: empty value is a valid edge case", func(t *testing.T) {
		req := factory.MakeSetRequest(redis_contract.WithValue(""))

		assert.Empty(t, req.Value)
	})

	// EC-004: Binary Data in Value
	t.Run("EC-004: binary-like data in value", func(t *testing.T) {
		binaryValue := string([]byte{0x00, 0x01, 0x02, 0xFF})
		req := factory.MakeSetRequest(redis_contract.WithValue(binaryValue))

		assert.Equal(t, binaryValue, req.Value)
	})

	// EC-007: Special Characters in Key
	t.Run("EC-007: special characters in key", func(t *testing.T) {
		specialKey := "key:with:colons:and/slashes"
		req := factory.MakeSetRequest(redis_contract.WithKey(specialKey))

		assert.Equal(t, specialKey, req.Key)
	})

	// EC-008: Unicode in Value
	t.Run("EC-008: unicode characters in value", func(t *testing.T) {
		unicodeValue := "Hello 世界 🌍 مرحبا"
		req := factory.MakeSetRequest(redis_contract.WithValue(unicodeValue))

		assert.Equal(t, unicodeValue, req.Value)
	})
}

// ===================================================================================
// TEST: HASH OPERATIONS
// ===================================================================================

func TestRedisHashOperations(t *testing.T) {
	factory := redis_contract.NewTestDataFactory()

	t.Run("hash request with multiple fields", func(t *testing.T) {
		fields := map[string]string{
			"field1": "value1",
			"field2": "value2",
			"field3": "value3",
		}
		req := factory.MakeHSetRequest(redis_contract.WithFieldsFromMap(fields))

		assert.Len(t, req.Fields, 3)
	})

	t.Run("hash request with custom key", func(t *testing.T) {
		req := factory.MakeHSetRequest(redis_contract.WithHashKey("user:123:profile"))

		assert.Equal(t, "user:123:profile", req.Key)
	})
}

// ===================================================================================
// TEST: MULTI-TENANT ISOLATION
// ===================================================================================

func TestRedisMultiTenantIsolation(t *testing.T) {
	scenarios := redis_contract.NewScenarios()

	t.Run("same logical key resolves to different physical keys per tenant", func(t *testing.T) {
		tenant1, tenant2 := scenarios.MultiTenantScenario()

		physicalKey1 := redis_contract.ExpectedIsolatedKey(
			tenant1.OrganizationId, tenant1.UserId, tenant1.Key,
		)
		physicalKey2 := redis_contract.ExpectedIsolatedKey(
			tenant2.OrganizationId, tenant2.UserId, tenant2.Key,
		)

		assert.Equal(t, tenant1.Key, tenant2.Key)
		assert.NotEqual(t, physicalKey1, physicalKey2)
	})

	t.Run("tenant isolation includes both org and user", func(t *testing.T) {
		factory := redis_contract.NewTestDataFactory()

		req1 := factory.MakeSetRequest(redis_contract.WithUser("user-1", "org-shared"))
		req2 := factory.MakeSetRequest(redis_contract.WithUser("user-2", "org-shared"))

		key1 := redis_contract.ExpectedIsolatedKey(req1.OrganizationId, req1.UserId, req1.Key)
		key2 := redis_contract.ExpectedIsolatedKey(req2.OrganizationId, req2.UserId, req2.Key)

		assert.NotEqual(t, key1, key2, "different users in same org should have different keys")
	})
}
