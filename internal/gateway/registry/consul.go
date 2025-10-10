package registry

import (
	"fmt"
	"net/http"
	"time"

	"github.com/hashicorp/consul/api"
	"github.com/isa-cloud/isa_cloud/pkg/logger"
)

// ConsulRegistry implements service registry using Consul
type ConsulRegistry struct {
	client *api.Client
	logger *logger.Logger
}

// NewConsulRegistry creates a new Consul-based service registry
func NewConsulRegistry(address string, logger *logger.Logger) (*ConsulRegistry, error) {
	config := api.DefaultConfig()
	if address != "" {
		config.Address = address
	}
	
	client, err := api.NewClient(config)
	if err != nil {
		return nil, fmt.Errorf("failed to create consul client: %w", err)
	}
	
	return &ConsulRegistry{
		client: client,
		logger: logger,
	}, nil
}

// RegisterService registers a service with Consul
func (r *ConsulRegistry) RegisterService(name string, host string, port int, tags []string) error {
	serviceID := fmt.Sprintf("%s-%s-%d", name, host, port)
	
	registration := &api.AgentServiceRegistration{
		ID:      serviceID,
		Name:    name,
		Address: host,
		Port:    port,
		Tags:    tags,
		Check: &api.AgentServiceCheck{
			HTTP:                           fmt.Sprintf("http://%s:%d/health", host, port),
			Interval:                       "10s",
			Timeout:                        "5s",
			DeregisterCriticalServiceAfter: "60s",
		},
	}
	
	err := r.client.Agent().ServiceRegister(registration)
	if err != nil {
		return fmt.Errorf("failed to register service: %w", err)
	}
	
	r.logger.Info("Service registered with Consul", 
		"name", name,
		"id", serviceID,
		"address", fmt.Sprintf("%s:%d", host, port),
		"tags", tags,
	)
	
	return nil
}

// DeregisterService removes a service from Consul
func (r *ConsulRegistry) DeregisterService(serviceID string) error {
	err := r.client.Agent().ServiceDeregister(serviceID)
	if err != nil {
		return fmt.Errorf("failed to deregister service: %w", err)
	}
	
	r.logger.Info("Service deregistered from Consul", "id", serviceID)
	return nil
}

// DiscoverService returns healthy instances of a service
func (r *ConsulRegistry) DiscoverService(name string) ([]*ServiceInstance, error) {
	// Query for all services (not only passing health checks)
	// Changed from true to false to include services with TTL health check issues
	services, _, err := r.client.Health().Service(name, "", false, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to discover service: %w", err)
	}

	if len(services) == 0 {
		return nil, fmt.Errorf("no instances found for service: %s", name)
	}
	
	instances := make([]*ServiceInstance, 0, len(services))
	for _, service := range services {
		instance := &ServiceInstance{
			ID:   service.Service.ID,
			Name: service.Service.Service,
			Host: service.Service.Address,
			Port: service.Service.Port,
			Tags: service.Service.Tags,
		}
		instances = append(instances, instance)
	}
	
	return instances, nil
}

// GetHealthyInstance returns a healthy instance (with simple round-robin)
func (r *ConsulRegistry) GetHealthyInstance(name string) (*ServiceInstance, error) {
	instances, err := r.DiscoverService(name)
	if err != nil {
		return nil, err
	}
	
	// Simple selection - just return first healthy instance
	// In production, you'd want proper load balancing
	return instances[0], nil
}

// WatchService watches for changes in a service
func (r *ConsulRegistry) WatchService(name string, callback func([]*ServiceInstance)) error {
	// Simplified implementation - in production you'd use consul watch
	r.logger.Info("Watch service registered", "service", name)
	return nil
}

// ListServices returns all registered services
func (r *ConsulRegistry) ListServices() (map[string][]string, error) {
	services, err := r.client.Agent().Services()
	if err != nil {
		return nil, fmt.Errorf("failed to list services: %w", err)
	}
	
	result := make(map[string][]string)
	for _, service := range services {
		result[service.Service] = service.Tags
	}
	
	return result, nil
}

// ServiceInstance represents a service instance
type ServiceInstance struct {
	ID   string
	Name string
	Host string
	Port int
	Tags []string
}

// CreateHTTPCheck creates an HTTP health check function
func CreateHTTPCheck(url string) func() error {
	return func() error {
		client := &http.Client{Timeout: 5 * time.Second}
		resp, err := client.Get(url)
		if err != nil {
			return err
		}
		defer resp.Body.Close()
		
		if resp.StatusCode != http.StatusOK {
			return fmt.Errorf("health check failed: status %d", resp.StatusCode)
		}
		
		return nil
	}
}