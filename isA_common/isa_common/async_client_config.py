#!/usr/bin/env python3
"""
Async Client Configuration
Shared configuration dataclass for async infrastructure clients.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ClientConfig:
    """
    Shared configuration for all async clients.

    Can be instantiated directly or loaded from environment variables.
    """
    host: str
    port: int
    user_id: str = 'default'
    organization_id: str = 'default-org'
    lazy_connect: bool = True

    # Optional authentication
    username: Optional[str] = None
    password: Optional[str] = None

    # Optional connection settings
    timeout: int = 30
    max_retries: int = 3

    @classmethod
    def from_env(
        cls,
        prefix: str,
        default_host: str = 'localhost',
        default_port: int = 0
    ) -> 'ClientConfig':
        """
        Load config from environment variables.

        Args:
            prefix: Environment variable prefix (e.g., 'REDIS' for REDIS_HOST)
            default_host: Default host if env var not set
            default_port: Default port if env var not set

        Returns:
            ClientConfig instance

        Environment variables read:
            {PREFIX}_HOST, {PREFIX}_PORT, {PREFIX}_USER, {PREFIX}_PASSWORD
            USER_ID, ORGANIZATION_ID
        """
        return cls(
            host=os.getenv(f'{prefix}_HOST', default_host),
            port=int(os.getenv(f'{prefix}_PORT', str(default_port))),
            user_id=os.getenv('USER_ID', 'default'),
            organization_id=os.getenv('ORGANIZATION_ID', 'default-org'),
            username=os.getenv(f'{prefix}_USER'),
            password=os.getenv(f'{prefix}_PASSWORD'),
        )

    def to_dict(self) -> dict:
        """Convert config to dictionary."""
        return {
            'host': self.host,
            'port': self.port,
            'user_id': self.user_id,
            'organization_id': self.organization_id,
            'lazy_connect': self.lazy_connect,
            'username': self.username,
            'password': self.password,
            'timeout': self.timeout,
            'max_retries': self.max_retries,
        }


@dataclass
class PostgresConfig(ClientConfig):
    """PostgreSQL-specific configuration."""
    database: str = 'postgres'
    min_pool_size: int = 5
    max_pool_size: int = 20
    ssl: bool = False

    @classmethod
    def from_env(cls, prefix: str = 'POSTGRES') -> 'PostgresConfig':
        base = ClientConfig.from_env(prefix, 'localhost', 5432)
        return cls(
            **base.to_dict(),
            database=os.getenv(f'{prefix}_DB', 'postgres'),
            min_pool_size=int(os.getenv(f'{prefix}_MIN_POOL', '5')),
            max_pool_size=int(os.getenv(f'{prefix}_MAX_POOL', '20')),
            ssl=os.getenv(f'{prefix}_SSL', 'false').lower() == 'true',
        )


@dataclass
class RedisConfig(ClientConfig):
    """Redis-specific configuration."""
    db: int = 0
    max_connections: int = 20

    @classmethod
    def from_env(cls, prefix: str = 'REDIS') -> 'RedisConfig':
        base = ClientConfig.from_env(prefix, 'localhost', 6379)
        return cls(
            **base.to_dict(),
            db=int(os.getenv(f'{prefix}_DB', '0')),
            max_connections=int(os.getenv(f'{prefix}_MAX_CONNECTIONS', '20')),
        )


@dataclass
class MinIOConfig(ClientConfig):
    """MinIO-specific configuration."""
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    secure: bool = False
    region: str = 'us-east-1'

    @classmethod
    def from_env(cls, prefix: str = 'MINIO') -> 'MinIOConfig':
        base = ClientConfig.from_env(prefix, 'localhost', 9000)
        return cls(
            **base.to_dict(),
            access_key=os.getenv(f'{prefix}_ACCESS_KEY', 'minioadmin'),
            secret_key=os.getenv(f'{prefix}_SECRET_KEY', 'minioadmin'),
            secure=os.getenv(f'{prefix}_SECURE', 'false').lower() == 'true',
            region=os.getenv(f'{prefix}_REGION', 'us-east-1'),
        )
