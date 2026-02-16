#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Setup configuration for isA_common package.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="isa-common",
    version="0.1.8",
    author="isA Platform",
    author_email="dev@isa-platform.com",
    description="Shared Python infrastructure library for isA platform",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/isa-platform/isA_Cloud",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "grpcio>=1.50.0",
        "grpcio-tools>=1.50.0",
        "pydantic>=2.0.0",
        "tenacity>=8.0.0",
        "python-consul2>=0.1.5",
        "asyncpg>=0.29.0",  # PostgreSQL async client
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
    },
    include_package_data=True,
    package_data={
        "isa_common.proto": ["*.py"],
    },
)
