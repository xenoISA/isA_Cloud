package server

import "context"

// ContainerBackend is the interface that both IgniteClient and DockerClient implement
type ContainerBackend interface {
	// CreateVM creates a new VM/container
	CreateVM(ctx context.Context, config *VMConfig) (vmID string, ipAddress string, error error)

	// StartVM starts a VM/container
	StartVM(ctx context.Context, vmID string) error

	// StopVM stops a VM/container
	StopVM(ctx context.Context, vmID string, timeoutSeconds int) error

	// DeleteVM removes a VM/container
	DeleteVM(ctx context.Context, vmID string, force bool) error

	// GetVMInfo gets VM/container information
	GetVMInfo(ctx context.Context, vmID string) (*VMStatus, error)

	// ListVMs lists VMs/containers matching filters
	ListVMs(ctx context.Context, labelFilters map[string]string) ([]*VMStatus, error)

	// ExecCommand executes a command in a VM/container
	ExecCommand(ctx context.Context, vmID string, config *ExecConfig) (*ExecResult, error)

	// GetResourceUsage gets resource usage of a VM/container
	GetResourceUsage(ctx context.Context, vmID string) (*ResourceUsageInfo, error)

	// ReadFile reads a file from a VM/container
	ReadFile(ctx context.Context, vmID string, filePath string) ([]byte, error)

	// WriteFile writes a file to a VM/container
	WriteFile(ctx context.Context, vmID string, filePath string, content []byte, permissions int) error
}

// Common structures used by both backends

// VMConfig represents VM/container configuration
type VMConfig struct {
	Name       string
	Image      string
	CPUs       int
	MemoryMB   int
	DiskSizeGB int
	EnvVars    map[string]string
	Ports      []string
	SSHKeys    []string
	Labels     map[string]string
}

// VMStatus represents VM/container status
type VMStatus struct {
	ID            string
	Name          string
	Image         string
	State         string
	IPAddress     string
	CreatedAt     int64
	StartedAt     int64
	UptimeSeconds int64
	Labels        map[string]string
}

// ExecConfig represents command execution configuration
type ExecConfig struct {
	Command    []string
	WorkingDir string
	Env        map[string]string
	TTY        bool
	Timeout    int
}

// ExecResult represents command execution result
type ExecResult struct {
	ExitCode        int
	Stdout          string
	Stderr          string
	ExecutionTimeMs int64
}

// ResourceUsageInfo represents resource usage information
type ResourceUsageInfo struct {
	CPUPercent    float64
	MemoryUsedMB  int64
	MemoryTotalMB int64
	DiskUsedGB    int64
	DiskTotalGB   int64
	NetworkRxMbps float64
	NetworkTxMbps float64
}
