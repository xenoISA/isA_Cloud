package middleware

import (
	"net/http"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"golang.org/x/time/rate"

	"github.com/isa-cloud/isa_cloud/pkg/logger"
)

// RateLimiter manages rate limiting for different keys (users, IPs, API keys)
type RateLimiter struct {
	limiters map[string]*rate.Limiter
	mu       sync.RWMutex
	rps      rate.Limit
	burst    int
	logger   *logger.Logger
}

// NewRateLimiter creates a new rate limiter
func NewRateLimiter(rps int, burst int, logger *logger.Logger) *RateLimiter {
	rl := &RateLimiter{
		limiters: make(map[string]*rate.Limiter),
		rps:      rate.Limit(rps),
		burst:    burst,
		logger:   logger,
	}

	// Start cleanup goroutine
	go rl.cleanupInactive()

	return rl
}

// getLimiter returns or creates a rate limiter for a key
func (rl *RateLimiter) getLimiter(key string) *rate.Limiter {
	rl.mu.RLock()
	limiter, exists := rl.limiters[key]
	rl.mu.RUnlock()

	if exists {
		return limiter
	}

	// Create new limiter
	rl.mu.Lock()
	defer rl.mu.Unlock()

	// Double-check after acquiring write lock
	limiter, exists = rl.limiters[key]
	if exists {
		return limiter
	}

	limiter = rate.NewLimiter(rl.rps, rl.burst)
	rl.limiters[key] = limiter

	return limiter
}

// Allow checks if a request for the given key is allowed
func (rl *RateLimiter) Allow(key string) bool {
	limiter := rl.getLimiter(key)
	return limiter.Allow()
}

// cleanupInactive removes inactive limiters periodically
func (rl *RateLimiter) cleanupInactive() {
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()

	for range ticker.C {
		rl.mu.Lock()
		// In production, you'd track last access time
		// For now, just keep all limiters (they're lightweight)
		rl.mu.Unlock()
	}
}

// PerUserRateLimit creates a rate limiting middleware that limits per user
func PerUserRateLimit(rps, burst int, logger *logger.Logger) gin.HandlerFunc {
	limiter := NewRateLimiter(rps, burst, logger)

	return func(c *gin.Context) {
		// Determine the key for rate limiting
		key := getRateLimitKey(c)

		if !limiter.Allow(key) {
			logger.Warn("Rate limit exceeded",
				"key", key,
				"ip", c.ClientIP(),
				"path", c.Request.URL.Path,
			)

			c.JSON(http.StatusTooManyRequests, gin.H{
				"error":   "rate_limit_exceeded",
				"message": "Too many requests. Please try again later.",
				"retry_after": "60s",
			})
			c.Abort()
			return
		}

		c.Next()
	}
}

// getRateLimitKey determines the key to use for rate limiting
func getRateLimitKey(c *gin.Context) string {
	// Priority 1: Use user_id from context (after authentication)
	if userID, exists := c.Get("user_id"); exists {
		if uid, ok := userID.(string); ok && uid != "" {
			return "user:" + uid
		}
	}

	// Priority 2: Use API key if present
	apiKey := c.GetHeader("X-API-Key")
	if apiKey != "" {
		return "apikey:" + apiKey[:min(10, len(apiKey))] // Use prefix only
	}

	// Priority 3: Use IP address
	return "ip:" + c.ClientIP()
}

// TieredRateLimiter implements subscription-tier based rate limiting
type TieredRateLimiter struct {
	freeLimiter       *RateLimiter
	proLimiter        *RateLimiter
	enterpriseLimiter *RateLimiter
	logger            *logger.Logger
}

// NewTieredRateLimiter creates a tiered rate limiter
func NewTieredRateLimiter(freeRPS, proRPS, enterpriseRPS int, burst int, logger *logger.Logger) *TieredRateLimiter {
	return &TieredRateLimiter{
		freeLimiter:       NewRateLimiter(freeRPS, burst, logger),
		proLimiter:        NewRateLimiter(proRPS, burst*2, logger),
		enterpriseLimiter: NewRateLimiter(enterpriseRPS, burst*5, logger),
		logger:            logger,
	}
}

// TieredRateLimit creates a subscription-tier aware rate limiting middleware
func TieredRateLimit(freeRPS, proRPS, enterpriseRPS, burst int, logger *logger.Logger) gin.HandlerFunc {
	limiter := NewTieredRateLimiter(freeRPS, proRPS, enterpriseRPS, burst, logger)

	return func(c *gin.Context) {
		key := getRateLimitKey(c)
		tier := getSubscriptionTier(c)

		var allowed bool
		switch tier {
		case "enterprise":
			allowed = limiter.enterpriseLimiter.Allow(key)
		case "pro":
			allowed = limiter.proLimiter.Allow(key)
		default:
			allowed = limiter.freeLimiter.Allow(key)
		}

		if !allowed {
			logger.Warn("Rate limit exceeded",
				"key", key,
				"tier", tier,
				"ip", c.ClientIP(),
				"path", c.Request.URL.Path,
			)

			c.JSON(http.StatusTooManyRequests, gin.H{
				"error":        "rate_limit_exceeded",
				"message":      "Too many requests. Please upgrade your plan for higher limits.",
				"current_tier": tier,
				"retry_after":  "60s",
			})
			c.Abort()
			return
		}

		c.Next()
	}
}

// getSubscriptionTier gets the subscription tier from context (set by auth middleware)
func getSubscriptionTier(c *gin.Context) string {
	if tier, exists := c.Get("subscription_tier"); exists {
		if t, ok := tier.(string); ok {
			return t
		}
	}

	// Default to free tier
	return "free"
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
