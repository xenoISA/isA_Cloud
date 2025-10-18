package cache

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"sync"
	"time"
)

// Cache interface for storing authentication results
type Cache interface {
	Get(ctx context.Context, key string) (interface{}, bool)
	Set(ctx context.Context, key string, value interface{}, ttl time.Duration) error
	Delete(ctx context.Context, key string) error
	Clear(ctx context.Context) error
}

// MemoryCache is an in-memory implementation of Cache with TTL support
type MemoryCache struct {
	data sync.Map
	mu   sync.RWMutex
}

type cacheEntry struct {
	value      interface{}
	expiration time.Time
}

// NewMemoryCache creates a new in-memory cache
func NewMemoryCache() *MemoryCache {
	cache := &MemoryCache{}

	// Start background cleanup goroutine
	go cache.cleanupExpired()

	return cache
}

// Get retrieves a value from cache
func (c *MemoryCache) Get(ctx context.Context, key string) (interface{}, bool) {
	value, ok := c.data.Load(key)
	if !ok {
		return nil, false
	}

	entry := value.(*cacheEntry)

	// Check if expired
	if time.Now().After(entry.expiration) {
		c.data.Delete(key)
		return nil, false
	}

	return entry.value, true
}

// Set stores a value in cache with TTL
func (c *MemoryCache) Set(ctx context.Context, key string, value interface{}, ttl time.Duration) error {
	entry := &cacheEntry{
		value:      value,
		expiration: time.Now().Add(ttl),
	}

	c.data.Store(key, entry)
	return nil
}

// Delete removes a value from cache
func (c *MemoryCache) Delete(ctx context.Context, key string) error {
	c.data.Delete(key)
	return nil
}

// Clear removes all values from cache
func (c *MemoryCache) Clear(ctx context.Context) error {
	c.data.Range(func(key, value interface{}) bool {
		c.data.Delete(key)
		return true
	})
	return nil
}

// cleanupExpired runs periodically to remove expired entries
func (c *MemoryCache) cleanupExpired() {
	ticker := time.NewTicker(1 * time.Minute)
	defer ticker.Stop()

	for range ticker.C {
		now := time.Now()
		c.data.Range(func(key, value interface{}) bool {
			entry := value.(*cacheEntry)
			if now.After(entry.expiration) {
				c.data.Delete(key)
			}
			return true
		})
	}
}

// HashToken creates a cache key from a token
func HashToken(token string) string {
	hash := sha256.Sum256([]byte(token))
	return "token:" + hex.EncodeToString(hash[:])
}

// PermissionCacheKey creates a cache key for permissions
func PermissionCacheKey(userID, resourceType, resourceName string) string {
	data := userID + ":" + resourceType + ":" + resourceName
	hash := sha256.Sum256([]byte(data))
	return "perm:" + hex.EncodeToString(hash[:])
}

// APIKeyCacheKey creates a cache key for API keys
func APIKeyCacheKey(apiKey string) string {
	hash := sha256.Sum256([]byte(apiKey))
	return "apikey:" + hex.EncodeToString(hash[:])
}
