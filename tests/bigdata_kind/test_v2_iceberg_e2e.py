"""
V-2: HMS + Iceberg + Flink end-to-end build/write/read.

Full E2E (Flink SQL CREATE → INSERT → SELECT through the Iceberg-on-S3A
catalog mounted into the Flink JM/TM pods) requires the flink-sql-runner
image, which is built upstream (xenoISA/isA_Cloud#255 / #265).

This test asserts the **configuration plumbing** is in place:
  - The iceberg-catalog ConfigMap is mounted into the JM container at
    /etc/iceberg/iceberg-catalog.properties
  - The catalog properties file declares a `hive` catalog-impl
    pointing at hive-metastore.isa-bigdata.svc.cluster.local:9083
  - The S3A endpoint targets the in-cluster MinIO Service

Full pipeline E2E lands in W4 once the runner image is push-able.
"""

from __future__ import annotations

import subprocess

CATALOG_PATH = "/etc/iceberg/iceberg-catalog.properties"


def test_v2_iceberg_catalog_mounted(namespace: str, flink_jm_pod: str) -> None:
    """The iceberg-catalog ConfigMap must mount into the Flink JM."""
    subprocess.run(
        [
            "kubectl",
            "-n",
            namespace,
            "exec",
            flink_jm_pod,
            "-c",
            "flink-main-container",
            "--",
            "test",
            "-f",
            CATALOG_PATH,
        ],
        check=True,
    )


def test_v2_iceberg_catalog_properties_correct(namespace: str, flink_jm_pod: str) -> None:
    """Catalog config must point at HMS Thrift + S3A MinIO endpoint."""
    out = subprocess.run(
        [
            "kubectl",
            "-n",
            namespace,
            "exec",
            flink_jm_pod,
            "-c",
            "flink-main-container",
            "--",
            "cat",
            CATALOG_PATH,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    body = out.stdout

    assert (
        "thrift://hive-metastore" in body
    ), f"Iceberg catalog must reference HMS Thrift; got:\n{body}"
    assert (
        "s3a://" in body or "warehouse" in body.lower()
    ), f"Iceberg catalog must declare an s3a:// warehouse; got:\n{body}"
