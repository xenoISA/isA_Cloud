"""
Service Discovery Helper Module

Provides helper functions for discovering services via Consul
"""

import logging
from typing import Optional
from .consul_client import ConsulRegistry

logger = logging.getLogger(__name__)


class ServiceDiscovery:
    """Helper class for service discovery via Consul"""
    
    def __init__(self, consul_registry: Optional[ConsulRegistry] = None):
        """
        Initialize service discovery helper
        
        Args:
            consul_registry: ConsulRegistry instance (optional)
        """
        self.consul_registry = consul_registry
    
    def get_service_url(self, service_name: str) -> str:
        """
        Get service URL from Consul discovery
        
        Args:
            service_name: Name of the service to discover
            
        Returns:
            Service URL from Consul
            
        Raises:
            ValueError: If service not found in Consul
        """
        if not self.consul_registry:
            raise ValueError("No Consul registry available for service discovery")
        
        # Use Consul discovery without fallback
        endpoint = self.consul_registry.get_service_endpoint(service_name)
        if endpoint:
            logger.debug(f"Discovered {service_name} at {endpoint}")
            return endpoint
        
        raise ValueError(f"Service {service_name} not found in Consul")
    
    def get_auth_service_url(self) -> str:
        """Get auth service URL"""
        return self.get_service_url("auth_service")
    
    def get_payment_service_url(self) -> str:
        """Get payment service URL"""
        return self.get_service_url("payment_service")
    
    def get_storage_service_url(self) -> str:
        """Get storage service URL"""
        return self.get_service_url("storage_service")
    
    def get_notification_service_url(self) -> str:
        """Get notification service URL"""
        return self.get_service_url("notification_service")
    
    def get_account_service_url(self) -> str:
        """Get account service URL"""
        return self.get_service_url("account_service")
    
    def get_session_service_url(self) -> str:
        """Get session service URL"""
        return self.get_service_url("session_service")
    
    def get_order_service_url(self) -> str:
        """Get order service URL"""
        return self.get_service_url("order_service")
    
    def get_task_service_url(self) -> str:
        """Get task service URL"""
        return self.get_service_url("task_service")
    
    def get_device_service_url(self) -> str:
        """Get device service URL"""
        return self.get_service_url("device_service")
    
    def get_organization_service_url(self) -> str:
        """Get organization service URL"""
        return self.get_service_url("organization_service")
    
    # Infrastructure Services Discovery
    def get_nats_url(self) -> str:
        """Get NATS message queue URL"""
        return self.get_service_url("nats")
    
    def get_redis_url(self) -> str:
        """Get Redis cache URL"""
        return self.get_service_url("redis")
    
    def get_loki_url(self) -> str:
        """Get Loki logging service URL"""
        return self.get_service_url("loki")
    
    def get_minio_endpoint(self) -> str:
        """Get MinIO object storage endpoint"""
        return self.get_service_url("minio")


def get_service_discovery(app) -> ServiceDiscovery:
    """
    Get service discovery helper from FastAPI app state
    
    Args:
        app: FastAPI app instance
        
    Returns:
        ServiceDiscovery instance
    """
    if hasattr(app.state, 'consul_registry') and app.state.consul_registry:
        return ServiceDiscovery(app.state.consul_registry)
    
    raise ValueError("No Consul registry found in app state. Service discovery is not available.")