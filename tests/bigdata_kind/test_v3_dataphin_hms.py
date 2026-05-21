"""
V-3: Dataphin → HMS → Iceberg-on-S3A read-through (the key valve).

Real V-3 needs the Dataphin chart (xenoISA/isA_Cloud#263) which the
vendor has not delivered. This test mocks the Dataphin tier with a
generic HMS schemaTool probe — exercising the same Thrift +
JDBC-to-PostgreSQL path Dataphin would use.

When V-3 has a real Dataphin client this test should be replaced with
a Dataphin REST call that lists tables under the iceberg catalog.
For now the gate verifies HMS is healthy enough to serve a Dataphin
client when one shows up.
"""

from __future__ import annotations

import subprocess


def test_v3_hms_schematool_info_succeeds(namespace: str, hms_pod: str) -> None:
    """`schematool -dbType postgres -info` proves HMS can talk to
    the postgres-bigdata schema, which is the JDBC path Dataphin
    would use for metadata lookups."""
    out = subprocess.run(
        [
            "kubectl",
            "-n",
            namespace,
            "exec",
            hms_pod,
            "--",
            "/opt/hive/bin/schematool",
            "-dbType",
            "postgres",
            "-info",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        # Surface stderr for debugging in CI logs.
        raise AssertionError(
            f"schematool -info failed (rc={out.returncode}):\n"
            f"stdout:\n{out.stdout}\n\nstderr:\n{out.stderr}"
        )

    # schematool -info typically prints something like:
    #   Hive distribution version: 4.0.0
    #   Metastore schema version:  4.0.0
    # We don't pin the version; just confirm it found a schema.
    body = out.stdout.lower()
    assert "schema" in body, f"schematool -info ran but produced no schema info; got:\n{out.stdout}"
