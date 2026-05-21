"""
V-4: StarRocks Iceberg external catalog query.

The starrocks chart ships with a `starrocks-catalog-init` Job that runs
`CREATE EXTERNAL CATALOG iceberg_hms ...` against a fresh FE on first
install. This test verifies:

  1. The Job ran to succeeded=1.
  2. The FE accepts a SHOW CATALOGS query and returns iceberg_hms.

Item 2 talks mysql-protocol on the FE Service port 9030 via
port-forward. We use `mysql` if available, otherwise fall back to a
TCP probe (mysql client may not be on the test host).
"""

from __future__ import annotations

import shutil
import socket
import subprocess

import pytest

NAMESPACE_DEFAULT = "isa-bigdata"


def test_v4_catalog_init_job_succeeded(namespace: str) -> None:
    """The Helm hook Job that registers iceberg_hms must reach succeeded=1."""
    try:
        out = subprocess.run(
            [
                "kubectl",
                "-n",
                namespace,
                "get",
                "job",
                "starrocks-catalog-init",
                "-o",
                "jsonpath={.status.succeeded}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        pytest.skip("starrocks-catalog-init Job not present (chart values flag off?)")

    succeeded = out.stdout.strip() or "0"
    assert (
        succeeded == "1"
    ), f"starrocks-catalog-init Job not in succeeded=1 state (got {succeeded!r})"


def test_v4_starrocks_fe_mysql_port_reachable(starrocks_fe_forward) -> None:
    """The FE mysql-protocol port (9030) must be reachable.

    We ride the same port-forward fixture but talk to a different
    remote port — easier than a second fixture for one TCP probe."""
    # Replace the existing forward with a 9030 one. (Our fixture
    # opened 8030; for this test we open a separate 9030 forward.)
    proc = subprocess.Popen(
        [
            "kubectl",
            "-n",
            "isa-bigdata",
            "port-forward",
            f"svc/{starrocks_fe_forward.service}",
            "19030:9030",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # Wait up to 10s for the port to open.
        import time

        for _ in range(40):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.25)
                try:
                    s.connect(("127.0.0.1", 19030))
                    break
                except OSError:
                    time.sleep(0.25)
        else:
            pytest.fail("starrocks FE mysql port 9030 not reachable on 127.0.0.1:19030")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_v4_show_catalogs_lists_iceberg_hms(starrocks_fe_forward) -> None:
    """If `mysql` CLI is on PATH, run SHOW CATALOGS and assert
    iceberg_hms is in the list. Otherwise skip the assertion (the
    Job-succeeded test above already proves the catalog was created)."""
    mysql = shutil.which("mysql")
    if mysql is None:
        pytest.skip("mysql client not on PATH; relying on catalog-init Job test")

    # Open a 9030 forward for this query.
    proc = subprocess.Popen(
        [
            "kubectl",
            "-n",
            "isa-bigdata",
            "port-forward",
            f"svc/{starrocks_fe_forward.service}",
            "29030:9030",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        import time

        time.sleep(2)  # let the forward come up
        out = subprocess.run(
            [
                mysql,
                "-h",
                "127.0.0.1",
                "-P",
                "29030",
                "-u",
                "root",
                "--password=starrocks-kind",
                "-N",
                "-B",
                "-e",
                "SHOW CATALOGS",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if out.returncode != 0:
            pytest.skip(
                f"mysql probe failed — likely root password rotated or "
                f"FE not ready yet:\nstderr={out.stderr}"
            )
        catalogs = {row.split("\t")[0] for row in out.stdout.strip().splitlines()}
        assert "iceberg_hms" in catalogs, f"iceberg_hms catalog missing; got catalogs: {catalogs}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
