package server

import (
	"context"
	"fmt"
	"io"
	"os"
	"strings"
	"time"

	"encoding/json"
	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/filters"
	"github.com/docker/docker/api/types/image"
	"github.com/docker/docker/client"
)

// DockerClient wraps Docker SDK operations
type DockerClient struct {
	client *client.Client
}

// NewDockerClient creates a new Docker client
func NewDockerClient() (*DockerClient, error) {
	cli, err := client.NewClientWithOpts(client.FromEnv, client.WithAPIVersionNegotiation())
	if err != nil {
		return nil, fmt.Errorf("failed to create docker client: %w", err)
	}

	return &DockerClient{
		client: cli,
	}, nil
}

// CreateVM creates a new Docker container (simulating a VM)
func (c *DockerClient) CreateVM(ctx context.Context, config *VMConfig) (string, string, error) {
	// Pull image if not exists
	reader, err := c.client.ImagePull(ctx, config.Image, image.PullOptions{})
	if err != nil {
		return "", "", fmt.Errorf("failed to pull image: %w", err)
	}
	io.Copy(io.Discard, reader)
	reader.Close()

	// Prepare environment variables
	env := []string{}
	for k, v := range config.EnvVars {
		env = append(env, fmt.Sprintf("%s=%s", k, v))
	}

	// Prepare labels
	labels := map[string]string{
		"managed-by": "cloud-os",
		"vm-type":    "docker",
	}
	for k, v := range config.Labels {
		labels[k] = v
	}

	// Create container config
	containerConfig := &container.Config{
		Image: config.Image,
		Env:   env,
		Labels: labels,
		Tty:   true,
		OpenStdin: true,
		Cmd:   []string{"/bin/sh", "-c", "while true; do sleep 30; done"}, // Keep container running
	}

	// Host config with resource limits
	hostConfig := &container.HostConfig{
		Resources: container.Resources{
			NanoCPUs: int64(config.CPUs * 1000000000), // Convert CPUs to nano CPUs
			Memory:   int64(config.MemoryMB * 1024 * 1024), // Convert MB to bytes
		},
		RestartPolicy: container.RestartPolicy{
			Name: "unless-stopped",
		},
	}

	// Create container
	resp, err := c.client.ContainerCreate(ctx, containerConfig, hostConfig, nil, nil, config.Name)
	if err != nil {
		return "", "", fmt.Errorf("failed to create container: %w", err)
	}

	// Start container
	if err := c.client.ContainerStart(ctx, resp.ID, container.StartOptions{}); err != nil {
		return "", "", fmt.Errorf("failed to start container: %w", err)
	}

	// Get container info to retrieve IP
	info, err := c.client.ContainerInspect(ctx, resp.ID)
	if err != nil {
		return resp.ID, "", fmt.Errorf("container created but failed to inspect: %w", err)
	}

	ipAddress := ""
	if info.NetworkSettings != nil && len(info.NetworkSettings.Networks) > 0 {
		for _, network := range info.NetworkSettings.Networks {
			ipAddress = network.IPAddress
			break
		}
	}

	return resp.ID, ipAddress, nil
}

// StartVM starts a Docker container
func (c *DockerClient) StartVM(ctx context.Context, vmID string) error {
	if err := c.client.ContainerStart(ctx, vmID, container.StartOptions{}); err != nil {
		return fmt.Errorf("failed to start container: %w", err)
	}
	return nil
}

// StopVM stops a Docker container
func (c *DockerClient) StopVM(ctx context.Context, vmID string, timeoutSeconds int) error {
	if err := c.client.ContainerStop(ctx, vmID, container.StopOptions{Timeout: &timeoutSeconds}); err != nil {
		return fmt.Errorf("failed to stop container: %w", err)
	}
	return nil
}

// DeleteVM removes a Docker container
func (c *DockerClient) DeleteVM(ctx context.Context, vmID string, force bool) error {
	if err := c.client.ContainerRemove(ctx, vmID, container.RemoveOptions{Force: force}); err != nil {
		return fmt.Errorf("failed to remove container: %w", err)
	}
	return nil
}

// GetVMInfo gets container information
func (c *DockerClient) GetVMInfo(ctx context.Context, vmID string) (*VMStatus, error) {
	info, err := c.client.ContainerInspect(ctx, vmID)
	if err != nil {
		return nil, fmt.Errorf("failed to inspect container: %w", err)
	}

	status := &VMStatus{
		ID:    info.ID,
		Name:  strings.TrimPrefix(info.Name, "/"),
		Image: info.Config.Image,
		State: info.State.Status,
		Labels: info.Config.Labels,
	}

	// Get IP address
	if info.NetworkSettings != nil && len(info.NetworkSettings.Networks) > 0 {
		for _, network := range info.NetworkSettings.Networks {
			status.IPAddress = network.IPAddress
			break
		}
	}

	// Parse created time
	if createdTime, err := time.Parse(time.RFC3339Nano, info.Created); err == nil {
		status.CreatedAt = createdTime.Unix()
	}

	// Calculate uptime if running
	if info.State.Running && info.State.StartedAt != "" {
		if startTime, err := time.Parse(time.RFC3339Nano, info.State.StartedAt); err == nil {
			status.StartedAt = startTime.Unix()
			status.UptimeSeconds = int64(time.Since(startTime).Seconds())
		}
	}

	return status, nil
}

// ListVMs lists Docker containers matching filters
func (c *DockerClient) ListVMs(ctx context.Context, labelFilters map[string]string) ([]*VMStatus, error) {
	filterArgs := filters.NewArgs()
	filterArgs.Add("label", "managed-by=cloud-os")

	for k, v := range labelFilters {
		filterArgs.Add("label", fmt.Sprintf("%s=%s", k, v))
	}

	containers, err := c.client.ContainerList(ctx, container.ListOptions{
		All:     true,
		Filters: filterArgs,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to list containers: %w", err)
	}

	var vms []*VMStatus
	for _, ctr := range containers {
		status := &VMStatus{
			ID:        ctr.ID,
			Name:      strings.TrimPrefix(ctr.Names[0], "/"),
			Image:     ctr.Image,
			State:     ctr.State,
			Labels:    ctr.Labels,
			CreatedAt: ctr.Created,
		}

		// Get IP address
		if len(ctr.NetworkSettings.Networks) > 0 {
			for _, network := range ctr.NetworkSettings.Networks {
				status.IPAddress = network.IPAddress
				break
			}
		}

		vms = append(vms, status)
	}

	return vms, nil
}

// ExecCommand executes a command in a Docker container
func (c *DockerClient) ExecCommand(ctx context.Context, vmID string, config *ExecConfig) (*ExecResult, error) {
	startTime := time.Now()

	// Create exec instance
	execConfig := types.ExecConfig{
		Cmd:          config.Command,
		AttachStdout: true,
		AttachStderr: true,
		WorkingDir:   config.WorkingDir,
		Env:          mapToEnvSlice(config.Env),
		Tty:          config.TTY,
	}

	execID, err := c.client.ContainerExecCreate(ctx, vmID, execConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to create exec: %w", err)
	}

	// Attach to exec
	resp, err := c.client.ContainerExecAttach(ctx, execID.ID, types.ExecStartCheck{})
	if err != nil {
		return nil, fmt.Errorf("failed to attach to exec: %w", err)
	}
	defer resp.Close()

	// Read output
	var stdout, stderr strings.Builder

	// Docker multiplexes stdout/stderr in the response
	buf := make([]byte, 8192)
	for {
		n, err := resp.Reader.Read(buf)
		if err != nil {
			if err != io.EOF {
				return nil, fmt.Errorf("failed to read exec output: %w", err)
			}
			break
		}

		if n > 8 {
			// Docker protocol: first byte is stream type (1=stdout, 2=stderr)
			// Next 3 bytes are padding, then 4 bytes for size
			streamType := buf[0]
			content := buf[8:n]

			if streamType == 1 {
				stdout.Write(content)
			} else if streamType == 2 {
				stderr.Write(content)
			}
		}
	}

	// Get exec exit code
	inspect, err := c.client.ContainerExecInspect(ctx, execID.ID)
	if err != nil {
		return nil, fmt.Errorf("failed to inspect exec: %w", err)
	}

	executionTime := time.Since(startTime)

	return &ExecResult{
		ExitCode:        inspect.ExitCode,
		Stdout:          stdout.String(),
		Stderr:          stderr.String(),
		ExecutionTimeMs: executionTime.Milliseconds(),
	}, nil
}

// ReadFile reads a file from a Docker container
func (c *DockerClient) ReadFile(ctx context.Context, vmID string, filePath string) ([]byte, error) {
	// Use docker cp to get file
	reader, _, err := c.client.CopyFromContainer(ctx, vmID, filePath)
	if err != nil {
		return nil, fmt.Errorf("failed to copy file from container: %w", err)
	}
	defer reader.Close()

	// Docker cp returns a tar archive, we need to extract the file
	// For simplicity, we'll read the entire tar content
	// In production, you'd want to properly extract the tar
	content, err := io.ReadAll(reader)
	if err != nil {
		return nil, fmt.Errorf("failed to read file content: %w", err)
	}

	return content, nil
}

// WriteFile writes a file to a Docker container
func (c *DockerClient) WriteFile(ctx context.Context, vmID string, filePath string, content []byte, permissions int) error {
	// TODO: Implement proper file writing via docker cp with tar
	// For now, use exec with base64 encoding to handle binary content
	return fmt.Errorf("WriteFile via Docker not fully implemented - use ExecCommand as workaround")
}

// GetResourceUsage gets container resource usage
func (c *DockerClient) GetResourceUsage(ctx context.Context, vmID string) (*ResourceUsageInfo, error) {
	stats, err := c.client.ContainerStats(ctx, vmID, false)
	if err != nil {
		return nil, fmt.Errorf("failed to get container stats: %w", err)
	}
	defer stats.Body.Close()

	// Parse stats
	var statsJSON types.StatsJSON
	decoder := json.NewDecoder(stats.Body)
	if err := decoder.Decode(&statsJSON); err != nil {
		return nil, fmt.Errorf("failed to read stats: %w", err)
	}

	// Calculate CPU percentage
	cpuDelta := float64(statsJSON.CPUStats.CPUUsage.TotalUsage - statsJSON.PreCPUStats.CPUUsage.TotalUsage)
	systemDelta := float64(statsJSON.CPUStats.SystemUsage - statsJSON.PreCPUStats.SystemUsage)
	cpuPercent := 0.0
	if systemDelta > 0.0 {
		cpuPercent = (cpuDelta / systemDelta) * float64(len(statsJSON.CPUStats.CPUUsage.PercpuUsage)) * 100.0
	}

	// Memory usage
	memoryUsedMB := int64(statsJSON.MemoryStats.Usage / 1024 / 1024)
	memoryTotalMB := int64(statsJSON.MemoryStats.Limit / 1024 / 1024)

	return &ResourceUsageInfo{
		CPUPercent:    cpuPercent,
		MemoryUsedMB:  memoryUsedMB,
		MemoryTotalMB: memoryTotalMB,
		DiskUsedGB:    0, // Docker doesn't expose this easily
		DiskTotalGB:   0,
		NetworkRxMbps: 0, // TODO: Calculate from network stats
		NetworkTxMbps: 0,
	}, nil
}

// Helper function to convert map to env slice
func mapToEnvSlice(envMap map[string]string) []string {
	if envMap == nil {
		return nil
	}

	env := make([]string, 0, len(envMap))
	for k, v := range envMap {
		env = append(env, fmt.Sprintf("%s=%s", k, v))
	}
	return env
}
