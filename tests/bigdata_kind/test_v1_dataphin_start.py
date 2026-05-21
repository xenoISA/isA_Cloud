"""
V-1: Dataphin community image starts.

Vendor delivery is tracked in xenoISA/isA_Cloud#263. The Dataphin chart
itself is not yet in the umbrella, so this test is intentionally a
parameterized skip that records the gate state for the test report.

When the vendor delivers the chart, this file flips to the actual
boot probe (Pod reaches Ready, /api/v1/system/version returns 200).
Until then the suite stays green and the gate stays SKIP.
"""

from __future__ import annotations

import subprocess

import pytest


def _dataphin_pod_present(namespace: str) -> bool:
    try:
        out = subprocess.run(
            [
                "kubectl",
                "-n",
                namespace,
                "get",
                "deploy",
                "dataphin",
                "-o",
                "jsonpath={.metadata.name}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return out.returncode == 0 and out.stdout.strip() == "dataphin"


def test_v1_dataphin_chart_present(namespace: str) -> None:
    """Skip until vendor delivers the chart (xenoISA/isA_Cloud#263).

    When the chart lands, replace this assertion with a Deployment
    Ready probe + /api/v1/system/version 200 check."""
    if not _dataphin_pod_present(namespace):
        pytest.skip(
            "Dataphin chart not delivered by vendor (xenoISA/isA_Cloud#263). "
            "V-1 gate stays SKIP until vendor ships."
        )

    # Once present, assert the Deployment is Ready.
    out = subprocess.run(
        [
            "kubectl",
            "-n",
            namespace,
            "get",
            "deploy",
            "dataphin",
            "-o",
            "jsonpath={.status.readyReplicas}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert int(out.stdout.strip() or "0") >= 1, "Dataphin Deployment present but no replicas Ready"
