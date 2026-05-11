"""
Pytest fixtures for V-1..V-5 acceptance tests against the isa-bigdata
umbrella running on a local kind cluster.

The fixtures wrap kubectl + port-forward so the tests can talk to
in-cluster Services from the test runner without hard-coding NodePorts.
Each port-forward runs in a background subprocess and is torn down
deterministically at fixture scope.

Skip behavior:
    Each fixture probes the underlying Service first; if it's not
    present the test is auto-skipped with `pytest.skip(...)`. This
    keeps the suite green when the cluster is partially deployed
    (e.g. Dataphin chart not yet installed) instead of forcing the
    operator to remember `-k` selectors.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Iterator

import pytest

NAMESPACE = os.environ.get("BIGDATA_NAMESPACE", "isa-bigdata")
RELEASE = os.environ.get("BIGDATA_RELEASE", "bigdata")
PORT_FORWARD_TIMEOUT_S = 15


def _kubectl(*args: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    cmd = ["kubectl", *args]
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
    )


def _service_exists(service: str) -> bool:
    try:
        _kubectl("-n", NAMESPACE, "get", "svc", service, capture=True)
    except subprocess.CalledProcessError:
        return False
    return True


def _wait_port_open(host: str, port: int, timeout_s: int = PORT_FORWARD_TIMEOUT_S) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.settimeout(0.5)
            try:
                s.connect((host, port))
                return True
            except OSError:
                time.sleep(0.25)
    return False


@dataclass
class PortForward:
    service: str
    local_port: int
    remote_port: int
    process: subprocess.Popen


@contextlib.contextmanager
def _port_forward(service: str, local_port: int, remote_port: int) -> Iterator[PortForward]:
    """Open a `kubectl port-forward svc/<service>` for the duration of
    the with-block. Caller must `_wait_port_open` before using it."""
    proc = subprocess.Popen(
        [
            "kubectl",
            "-n",
            NAMESPACE,
            "port-forward",
            f"svc/{service}",
            f"{local_port}:{remote_port}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not _wait_port_open("127.0.0.1", local_port):
            proc.terminate()
            proc.wait(timeout=5)
            pytest.fail(
                f"port-forward to svc/{service} ({remote_port}) "
                f"never became reachable on 127.0.0.1:{local_port}"
            )
        yield PortForward(service, local_port, remote_port, proc)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def pytest_collection_modifyitems(config, items):  # noqa: D401
    """Skip the entire suite if kubectl is not on PATH or the kind
    namespace doesn't exist — the suite has no meaning otherwise."""
    if shutil.which("kubectl") is None:
        skip = pytest.mark.skip(reason="kubectl not on PATH")
        for item in items:
            item.add_marker(skip)
        return

    try:
        _kubectl("get", "namespace", NAMESPACE, capture=True)
    except subprocess.CalledProcessError:
        skip = pytest.mark.skip(
            reason=f"namespace {NAMESPACE} not found — run `make setup-datalake-kind`"
        )
        for item in items:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def namespace() -> str:
    return NAMESPACE


@pytest.fixture(scope="session")
def release() -> str:
    return RELEASE


@pytest.fixture
def hms_pod() -> str:
    """Returns the name of the first ready hive-metastore Pod, or skips."""
    try:
        out = _kubectl(
            "-n", NAMESPACE, "get", "pod",
            "-l", "app=hive-metastore",
            "-o", "jsonpath={.items[0].metadata.name}",
            capture=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        pytest.skip("hive-metastore Pod not present")
    if not out:
        pytest.skip("hive-metastore Pod not yet scheduled")
    return out


@pytest.fixture
def flink_jm_pod() -> str:
    """Returns the name of the first ready Flink JM Pod, or skips."""
    try:
        out = _kubectl(
            "-n", NAMESPACE, "get", "pod",
            "-l", "app=flink-session,component=jobmanager",
            "-o", "jsonpath={.items[0].metadata.name}",
            capture=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        pytest.skip("Flink JM Pod not present")
    if not out:
        pytest.skip("Flink JM Pod not yet scheduled")
    return out


@pytest.fixture
def apicurio_forward() -> Iterator[PortForward]:
    if not _service_exists("apicurio-registry"):
        pytest.skip("apicurio-registry Service not present")
    with _port_forward("apicurio-registry", 18080, 8080) as pf:
        yield pf


@pytest.fixture
def starrocks_fe_forward(release: str) -> Iterator[PortForward]:
    svc = f"{release}-starrocks-fe-service"
    if not _service_exists(svc):
        pytest.skip(f"{svc} Service not present")
    # 8030 = HTTP query API, 9030 = mysql protocol. Tests pick what they need.
    with _port_forward(svc, 18030, 8030) as pf:
        yield pf
