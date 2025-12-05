package server

import (
	"context"
	"fmt"
	"log"
	"time"

	pb "github.com/isa-cloud/isa_cloud/api/proto/container"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// ContainerService implements the gRPC ContainerService
type ContainerService struct {
	pb.UnimplementedContainerServiceServer
	backend ContainerBackend
}

// NewContainerService creates a new container service
func NewContainerService(backend ContainerBackend) *ContainerService {
	return &ContainerService{
		backend: backend,
	}
}

// CreateVM creates a new Firecracker microVM using Ignite
func (s *ContainerService) CreateVM(ctx context.Context, req *pb.CreateVMRequest) (*pb.VMResponse, error) {
	log.Printf("Creating VM for user %s with image %s", req.UserId, req.Image)

	// Validate request
	if req.UserId == "" {
		return nil, status.Error(codes.InvalidArgument, "user_id is required")
	}
	if req.Image == "" {
		return nil, status.Error(codes.InvalidArgument, "image is required")
	}

	// Set default VM name if not provided
	vmName := req.VmName
	if vmName == "" {
		vmName = fmt.Sprintf("%s-env", req.UserId)
	}

	// Set default resource limits if not provided
	limits := req.Limits
	if limits == nil {
		limits = &pb.ResourceLimits{
			CpuCount:   2,
			MemoryMb:   4096,
			DiskSizeGb: 20,
		}
	}

	// Create VM using Ignite
	vmID, ipAddress, err := s.backend.CreateVM(ctx, &VMConfig{
		Name:       vmName,
		Image:      req.Image,
		CPUs:       int(limits.CpuCount),
		MemoryMB:   int(limits.MemoryMb),
		DiskSizeGB: int(limits.DiskSizeGb),
		EnvVars:    req.EnvVars,
		SSHKeys:    req.SshKeys,
		Labels:     req.Labels,
		Ports:      req.Ports,
	})

	if err != nil {
		log.Printf("Failed to create VM: %v", err)
		return nil, status.Errorf(codes.Internal, "failed to create VM: %v", err)
	}

	log.Printf("✅ VM created successfully: %s (ID: %s, IP: %s)", vmName, vmID, ipAddress)

	return &pb.VMResponse{
		VmId:      vmID,
		UserId:    req.UserId,
		VmName:    vmName,
		Status:    "running",
		Message:   "VM created and started successfully",
		CreatedAt: time.Now().Unix(),
		IpAddress: ipAddress,
		Ports:     req.Ports,
	}, nil
}

// StartVM starts a stopped VM
func (s *ContainerService) StartVM(ctx context.Context, req *pb.StartVMRequest) (*pb.VMResponse, error) {
	log.Printf("Starting VM: %s", req.VmId)

	if req.VmId == "" {
		return nil, status.Error(codes.InvalidArgument, "vm_id is required")
	}

	err := s.backend.StartVM(ctx, req.VmId)
	if err != nil {
		log.Printf("Failed to start VM: %v", err)
		return nil, status.Errorf(codes.Internal, "failed to start VM: %v", err)
	}

	log.Printf("✅ VM started successfully: %s", req.VmId)

	return &pb.VMResponse{
		VmId:    req.VmId,
		Status:  "running",
		Message: "VM started successfully",
	}, nil
}

// StopVM stops a running VM
func (s *ContainerService) StopVM(ctx context.Context, req *pb.StopVMRequest) (*pb.VMResponse, error) {
	log.Printf("Stopping VM: %s", req.VmId)

	if req.VmId == "" {
		return nil, status.Error(codes.InvalidArgument, "vm_id is required")
	}

	timeout := int(req.TimeoutSeconds)
	if timeout == 0 {
		timeout = 30 // default 30 seconds
	}

	err := s.backend.StopVM(ctx, req.VmId, timeout)
	if err != nil {
		log.Printf("Failed to stop VM: %v", err)
		return nil, status.Errorf(codes.Internal, "failed to stop VM: %v", err)
	}

	log.Printf("✅ VM stopped successfully: %s", req.VmId)

	return &pb.VMResponse{
		VmId:    req.VmId,
		Status:  "stopped",
		Message: "VM stopped successfully",
	}, nil
}

// DeleteVM deletes a VM
func (s *ContainerService) DeleteVM(ctx context.Context, req *pb.DeleteVMRequest) (*pb.VMResponse, error) {
	log.Printf("Deleting VM: %s (force: %v)", req.VmId, req.Force)

	if req.VmId == "" {
		return nil, status.Error(codes.InvalidArgument, "vm_id is required")
	}

	err := s.backend.DeleteVM(ctx, req.VmId, req.Force)
	if err != nil {
		log.Printf("Failed to delete VM: %v", err)
		return nil, status.Errorf(codes.Internal, "failed to delete VM: %v", err)
	}

	log.Printf("✅ VM deleted successfully: %s", req.VmId)

	return &pb.VMResponse{
		VmId:    req.VmId,
		Status:  "deleted",
		Message: "VM deleted successfully",
	}, nil
}

// GetVMStatus gets the status of a VM
func (s *ContainerService) GetVMStatus(ctx context.Context, req *pb.GetVMStatusRequest) (*pb.VMStatusResponse, error) {
	log.Printf("Getting VM status: %s", req.VmId)

	if req.VmId == "" {
		return nil, status.Error(codes.InvalidArgument, "vm_id is required")
	}

	vmStatus, err := s.backend.GetVMInfo(ctx, req.VmId)
	if err != nil {
		log.Printf("Failed to get VM status: %v", err)
		return nil, status.Errorf(codes.Internal, "failed to get VM status: %v", err)
	}

	return &pb.VMStatusResponse{
		VmId:       vmStatus.ID,
		UserId:     vmStatus.UserID,
		VmName:     vmStatus.Name,
		Status:     vmStatus.Status,
		Image:      vmStatus.Image,
		CreatedAt:  vmStatus.CreatedAt,
		StartedAt:  vmStatus.StartedAt,
		UptimeSeconds: vmStatus.UptimeSeconds,
		IpAddress:  vmStatus.IPAddress,
		Labels:     vmStatus.Labels,
		ResourceUsage: &pb.ResourceUsage{
			CpuPercent:     vmStatus.ResourceUsage.CPUPercent,
			MemoryUsedMb:   vmStatus.ResourceUsage.MemoryUsedMB,
			MemoryTotalMb:  vmStatus.ResourceUsage.MemoryTotalMB,
			DiskUsedGb:     vmStatus.ResourceUsage.DiskUsedGB,
			DiskTotalGb:    vmStatus.ResourceUsage.DiskTotalGB,
			NetworkRxMbps:  vmStatus.ResourceUsage.NetworkRxMbps,
			NetworkTxMbps:  vmStatus.ResourceUsage.NetworkTxMbps,
		},
	}, nil
}

// ListVMs lists VMs with optional filtering
func (s *ContainerService) ListVMs(ctx context.Context, req *pb.ListVMsRequest) (*pb.ListVMsResponse, error) {
	log.Printf("Listing VMs (user: %s, status: %s)", req.UserId, req.Status)

	// Build filters
	filters := make(map[string]string)
	if req.UserId != "" {
		filters["user_id"] = req.UserId
	}
	if req.Status != "" {
		filters["status"] = req.Status
	}

	vms, err := s.backend.ListVMs(ctx, filters)
	if err != nil {
		log.Printf("Failed to list VMs: %v", err)
		return nil, status.Errorf(codes.Internal, "failed to list VMs: %v", err)
	}

	// Apply pagination
	limit := int(req.Limit)
	if limit == 0 {
		limit = 100 // default limit
	}
	offset := int(req.Offset)

	total := len(vms)
	end := offset + limit
	if end > total {
		end = total
	}

	var paginatedVMs []*VMInfo
	if offset < total {
		paginatedVMs = vms[offset:end]
	}

	// Convert to protobuf messages
	pbVMs := make([]*pb.VMInfo, len(paginatedVMs))
	for i, vm := range paginatedVMs {
		pbVMs[i] = &pb.VMInfo{
			VmId:      vm.ID,
			UserId:    vm.UserID,
			VmName:    vm.Name,
			Status:    vm.Status,
			Image:     vm.Image,
			CreatedAt: vm.CreatedAt,
			IpAddress: vm.IPAddress,
		}
	}

	log.Printf("✅ Listed %d VMs (total: %d)", len(pbVMs), total)

	return &pb.ListVMsResponse{
		Vms:   pbVMs,
		Total: int32(total),
	}, nil
}

// ExecuteCommand executes a command in a VM
func (s *ContainerService) ExecuteCommand(ctx context.Context, req *pb.ExecuteCommandRequest) (*pb.ExecuteCommandResponse, error) {
	log.Printf("Executing command in VM %s: %v", req.VmId, req.Command)

	if req.VmId == "" {
		return nil, status.Error(codes.InvalidArgument, "vm_id is required")
	}
	if len(req.Command) == 0 {
		return nil, status.Error(codes.InvalidArgument, "command is required")
	}

	startTime := time.Now()

	result, err := s.backend.ExecCommand(ctx, req.VmId, &ExecConfig{
		Command:    req.Command,
		WorkingDir: req.WorkingDir,
		Env:        req.Env,
		Timeout:    int(req.TimeoutSeconds),
		TTY:        req.Tty,
	})

	executionTime := time.Since(startTime).Milliseconds()

	if err != nil {
		log.Printf("Failed to execute command: %v", err)
		return nil, status.Errorf(codes.Internal, "failed to execute command: %v", err)
	}

	log.Printf("✅ Command executed in %dms (exit code: %d)", executionTime, result.ExitCode)

	return &pb.ExecuteCommandResponse{
		ExitCode:        int32(result.ExitCode),
		Stdout:          result.Stdout,
		Stderr:          result.Stderr,
		ExecutionTimeMs: executionTime,
	}, nil
}

// ReadFile reads a file from a VM
func (s *ContainerService) ReadFile(ctx context.Context, req *pb.ReadFileRequest) (*pb.ReadFileResponse, error) {
	log.Printf("Reading file from VM %s: %s", req.VmId, req.FilePath)

	if req.VmId == "" {
		return nil, status.Error(codes.InvalidArgument, "vm_id is required")
	}
	if req.FilePath == "" {
		return nil, status.Error(codes.InvalidArgument, "file_path is required")
	}

	content, err := s.backend.ReadFile(ctx, req.VmId, req.FilePath)
	if err != nil {
		log.Printf("Failed to read file: %v", err)
		return nil, status.Errorf(codes.Internal, "failed to read file: %v", err)
	}

	log.Printf("✅ File read successfully (%d bytes)", len(content))

	return &pb.ReadFileResponse{
		Content:      content,
		Size:         int64(len(content)),
		ModifiedTime: time.Now().Unix(),
		Permissions:  0644,
	}, nil
}

// WriteFile writes a file to a VM
func (s *ContainerService) WriteFile(ctx context.Context, req *pb.WriteFileRequest) (*pb.WriteFileResponse, error) {
	log.Printf("Writing file to VM %s: %s (%d bytes)", req.VmId, req.FilePath, len(req.Content))

	if req.VmId == "" {
		return nil, status.Error(codes.InvalidArgument, "vm_id is required")
	}
	if req.FilePath == "" {
		return nil, status.Error(codes.InvalidArgument, "file_path is required")
	}

	err := s.backend.WriteFile(ctx, req.VmId, req.FilePath, req.Content, int(req.Permissions))

	if err != nil {
		log.Printf("Failed to write file: %v", err)
		return nil, status.Errorf(codes.Internal, "failed to write file: %v", err)
	}

	log.Printf("✅ File written successfully")

	return &pb.WriteFileResponse{
		Success:      true,
		Message:      "File written successfully",
		BytesWritten: int64(len(req.Content)),
	}, nil
}

// GetResourceUsage gets resource usage of a VM
func (s *ContainerService) GetResourceUsage(ctx context.Context, req *pb.GetResourceUsageRequest) (*pb.ResourceUsageResponse, error) {
	log.Printf("Getting resource usage for VM: %s", req.VmId)

	if req.VmId == "" {
		return nil, status.Error(codes.InvalidArgument, "vm_id is required")
	}

	usage, err := s.backend.GetResourceUsage(ctx, req.VmId)
	if err != nil {
		log.Printf("Failed to get resource usage: %v", err)
		return nil, status.Errorf(codes.Internal, "failed to get resource usage: %v", err)
	}

	return &pb.ResourceUsageResponse{
		VmId:      req.VmId,
		Timestamp: time.Now().Unix(),
		Usage: &pb.ResourceUsage{
			CpuPercent:     usage.CPUPercent,
			MemoryUsedMb:   usage.MemoryUsedMB,
			MemoryTotalMb:  usage.MemoryTotalMB,
			DiskUsedGb:     usage.DiskUsedGB,
			DiskTotalGb:    usage.DiskTotalGB,
			NetworkRxMbps:  usage.NetworkRxMbps,
			NetworkTxMbps:  usage.NetworkTxMbps,
		},
	}, nil
}

// Implement other methods (DeleteFile, ListFiles, CreateDirectory, etc.)
// For brevity, showing main structure
