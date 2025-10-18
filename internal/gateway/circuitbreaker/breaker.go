package circuitbreaker

import (
	"context"
	"fmt"
	"time"

	"github.com/sony/gobreaker"
	"github.com/isa-cloud/isa_cloud/pkg/logger"
)

// CircuitBreaker wraps gobreaker with logging and metrics
type CircuitBreaker struct {
	breaker *gobreaker.CircuitBreaker
	logger  *logger.Logger
	name    string
}

// Config for circuit breaker
type Config struct {
	Name          string
	MaxRequests   uint32        // Max requests in half-open state
	Interval      time.Duration // Interval to clear counts
	Timeout       time.Duration // Timeout to switch from open to half-open
	ReadyToTrip   func(counts gobreaker.Counts) bool
	OnStateChange func(name string, from gobreaker.State, to gobreaker.State)
}

// New creates a new circuit breaker
func New(cfg Config, logger *logger.Logger) *CircuitBreaker {
	settings := gobreaker.Settings{
		Name:        cfg.Name,
		MaxRequests: cfg.MaxRequests,
		Interval:    cfg.Interval,
		Timeout:     cfg.Timeout,
		ReadyToTrip: cfg.ReadyToTrip,
		OnStateChange: func(name string, from gobreaker.State, to gobreaker.State) {
			logger.Warn("Circuit breaker state changed",
				"breaker", name,
				"from", from.String(),
				"to", to.String(),
			)
			if cfg.OnStateChange != nil {
				cfg.OnStateChange(name, from, to)
			}
		},
	}

	return &CircuitBreaker{
		breaker: gobreaker.NewCircuitBreaker(settings),
		logger:  logger,
		name:    cfg.Name,
	}
}

// Execute runs a function with circuit breaker protection
func (cb *CircuitBreaker) Execute(ctx context.Context, fn func() (interface{}, error)) (interface{}, error) {
	result, err := cb.breaker.Execute(func() (interface{}, error) {
		return fn()
	})

	if err != nil {
		cb.logger.Debug("Circuit breaker request failed",
			"breaker", cb.name,
			"error", err,
			"state", cb.breaker.State().String(),
		)
		return nil, err
	}

	return result, nil
}

// State returns the current state of the circuit breaker
func (cb *CircuitBreaker) State() gobreaker.State {
	return cb.breaker.State()
}

// Counts returns the current counts
func (cb *CircuitBreaker) Counts() gobreaker.Counts {
	return cb.breaker.Counts()
}

// DefaultReadyToTrip returns a default ready-to-trip function
func DefaultReadyToTrip(threshold uint32) func(counts gobreaker.Counts) bool {
	return func(counts gobreaker.Counts) bool {
		failureRatio := float64(counts.TotalFailures) / float64(counts.Requests)
		return counts.Requests >= 3 && (counts.ConsecutiveFailures >= threshold || failureRatio >= 0.6)
	}
}

// NewAuthServiceBreaker creates a circuit breaker for auth service
func NewAuthServiceBreaker(threshold uint32, timeout time.Duration, logger *logger.Logger) *CircuitBreaker {
	return New(Config{
		Name:        "auth-service",
		MaxRequests: 3,
		Interval:    10 * time.Second,
		Timeout:     timeout,
		ReadyToTrip: DefaultReadyToTrip(threshold),
	}, logger)
}

// NewAuthorizationServiceBreaker creates a circuit breaker for authorization service
func NewAuthorizationServiceBreaker(threshold uint32, timeout time.Duration, logger *logger.Logger) *CircuitBreaker {
	return New(Config{
		Name:        "authorization-service",
		MaxRequests: 3,
		Interval:    10 * time.Second,
		Timeout:     timeout,
		ReadyToTrip: DefaultReadyToTrip(threshold),
	}, logger)
}

// IsCircuitBreakerError checks if the error is from an open circuit breaker
func IsCircuitBreakerError(err error) bool {
	return err == gobreaker.ErrOpenState || err == gobreaker.ErrTooManyRequests
}

// WrapError wraps a circuit breaker error with context
func WrapError(err error, serviceName string) error {
	if IsCircuitBreakerError(err) {
		return fmt.Errorf("%s circuit breaker is open (service unavailable)", serviceName)
	}
	return err
}
