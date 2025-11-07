#!/usr/bin/env python3
"""
gRPC Clients Package
统一的 gRPC 客户端接口

使用示例:
    from core.clients import get_client, PostgresClient, MinIOClient

    # 方式 1: 使用工厂函数
    postgres = get_client('postgres', user_id='user_123')

    # 方式 2: 直接实例化
    minio = MinIOClient(host='localhost', port=50051, user_id='user_123')

    # 方式 3: 使用 with 语句自动管理连接
    with PostgresClient() as client:
        client.query('SELECT * FROM users')
"""

from typing import Optional, Dict
from .base_client import BaseGRPCClient
from .postgres_client import PostgresClient
from .qdrant_client import QdrantClient
from .neo4j_client import Neo4jClient
from .minio_client import MinIOClient
from .duckdb_client import DuckDBClient
from .mqtt_client import MQTTClient
from .nats_client import NATSClient
from .redis_client import RedisClient
from .loki_client import LokiClient
from .consul_client import ConsulRegistry, consul_lifespan

# Import events module (but don't unpack, keep as submodule)
from . import events

# 导出所有客户端
__all__ = [
    'BaseGRPCClient',
    'PostgresClient',
    'QdrantClient',
    'Neo4jClient',
    'MinIOClient',
    'DuckDBClient',
    'MQTTClient',
    'NATSClient',
    'RedisClient',
    'LokiClient',
    'ConsulRegistry',
    'consul_lifespan',
    'get_client',
    'ClientFactory',
    'events',  # Export events submodule
]

# 默认配置
DEFAULT_PORTS: Dict[str, int] = {
    'minio': 50051,
    'duckdb': 50052,
    'mqtt': 50053,
    'loki': 50054,
    'redis': 50055,
    'nats': 50056,
    'postgres': 50064,
    'qdrant': 50062,
    'neo4j': 50063,
}

DEFAULT_HOST = 'localhost'


class ClientFactory:
    """gRPC 客户端工厂"""
    
    # 客户端映射
    _clients = {
        'postgres': PostgresClient,
        'qdrant': QdrantClient,
        'neo4j': Neo4jClient,
        'minio': MinIOClient,
        'duckdb': DuckDBClient,
        'mqtt': MQTTClient,
        'nats': NATSClient,
        'redis': RedisClient,
        'loki': LokiClient,
    }
    
    @classmethod
    def create(cls, service_name: str, host: Optional[str] = None, 
               port: Optional[int] = None, user_id: Optional[str] = None) -> BaseGRPCClient:
        """
        创建 gRPC 客户端
        
        Args:
            service_name: 服务名称 (supabase, minio, duckdb, etc.)
            host: 服务地址 (默认: localhost)
            port: 服务端口 (默认: 根据服务自动选择)
            user_id: 用户 ID
        
        Returns:
            客户端实例
        
        Raises:
            ValueError: 如果服务名称不支持
        
        示例:
            client = ClientFactory.create('supabase', user_id='user_123')
            client = ClientFactory.create('minio', host='192.168.1.100', port=50051)
        """
        service_name = service_name.lower()
        
        if service_name not in cls._clients:
            available = ', '.join(cls._clients.keys())
            raise ValueError(f"不支持的服务: {service_name}. 可用服务: {available}")
        
        # 使用默认值
        if host is None:
            host = DEFAULT_HOST
        if port is None:
            port = DEFAULT_PORTS.get(service_name, 50051)
        
        client_class = cls._clients[service_name]
        return client_class(host=host, port=port, user_id=user_id)
    
    @classmethod
    def register_client(cls, service_name: str, client_class):
        """
        注册新的客户端类
        
        Args:
            service_name: 服务名称
            client_class: 客户端类 (必须继承 BaseGRPCClient)
        """
        if not issubclass(client_class, BaseGRPCClient):
            raise TypeError(f"{client_class} 必须继承 BaseGRPCClient")
        
        cls._clients[service_name.lower()] = client_class
        print(f"✅ 注册客户端: {service_name} -> {client_class.__name__}")
    
    @classmethod
    def list_services(cls) -> list:
        """列出所有可用的服务"""
        return list(cls._clients.keys())


# 便捷函数
def get_client(service_name: str, host: Optional[str] = None, 
               port: Optional[int] = None, user_id: Optional[str] = None) -> BaseGRPCClient:
    """
    获取 gRPC 客户端 (便捷函数)
    
    Args:
        service_name: 服务名称
        host: 服务地址
        port: 服务端口
        user_id: 用户 ID
    
    Returns:
        客户端实例
    
    示例:
        from core.clients import get_client
        
        supabase = get_client('supabase', user_id='user_123')
        minio = get_client('minio', host='192.168.1.100')
    """
    return ClientFactory.create(service_name, host, port, user_id)


# 显示所有可用服务
def show_available_services():
    """显示所有可用的 gRPC 服务"""
    print("📦 可用的 gRPC 服务:")
    print()
    for service in sorted(ClientFactory.list_services()):
        port = DEFAULT_PORTS.get(service, 'N/A')
        client_class = ClientFactory._clients[service]
        print(f"  • {service:12} (端口: {port})  -> {client_class.__name__}")
    print()


if __name__ == '__main__':
    # 显示可用服务
    show_available_services()
    
    # 测试客户端创建
    print("测试客户端创建:")
    print("-" * 60)
    
    # 使用工厂创建客户端
    with get_client('postgres', user_id='test_user') as postgres:
        postgres.health_check()

    print()

    with get_client('minio', user_id='test_user') as minio:
        minio.health_check()

