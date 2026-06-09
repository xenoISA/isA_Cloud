"""Environment-agnostic config for the cloud-native parity test suite.

ONE suite, runs against ANY environment by config — the cloud-native goal:
  - local dev        : services on localhost / kind NodePorts
  - in-cluster (SN)  : K8s service DNS (air-gapped IDC)
  - in-cluster (GCP) : K8s service DNS (GKE) — same shape as SN

The target is chosen by the PARITY_TARGET env var:
  PARITY_TARGET=local      -> http://localhost:<port>   (override host via PARITY_HOST)
  PARITY_TARGET=incluster  -> http://<svc>.<ns>.svc.cluster.local:<port>  (ns via PARITY_NAMESPACE)

Because SN-IDC and GCP-GKE are both "incluster", the SAME profile covers both —
that is the whole point: edition-agnostic, cloud-native, deploy anywhere.
"""

from __future__ import annotations

import os

TARGET = os.getenv("PARITY_TARGET", "incluster").lower()
NAMESPACE = os.getenv("PARITY_NAMESPACE", "sn-cloud-production")
LOCAL_HOST = os.getenv("PARITY_HOST", "localhost")

# service -> port (the platform's canonical ports; identical across editions)
PORTS = {
    # platform
    "isa-agent": 8080,
    "isa-agent-mt": 8080,
    "isa-data": 8084,
    "isa-mate": 18789,
    "isa-mcp": 8081,
    "isa-model": 8082,
    "isa-os": 8083,
    # user microservices (8201-8262)
    "user-auth": 8201,
    "user-account": 8202,
    "user-session": 8203,
    "user-authorization": 8204,
    "user-audit": 8205,
    "user-notification": 8206,
    "user-payment": 8207,
    "user-wallet": 8208,
    "user-storage": 8209,
    "user-order": 8210,
    "user-task": 8211,
    "user-organization": 8212,
    "user-invitation": 8213,
    "user-vault": 8214,
    "user-product": 8215,
    "user-billing": 8216,
    "user-calendar": 8217,
    "user-weather": 8218,
    "user-album": 8219,
    "user-device": 8220,
    "user-ota": 8221,
    "user-media": 8222,
    "user-memory": 8223,
    "user-location": 8224,
    "user-telemetry": 8225,
    "user-compliance": 8226,
    "user-document": 8227,
    "user-subscription": 8228,
    "user-credit": 8229,
    "user-event": 8230,
    "user-membership": 8250,
    "user-campaign": 8251,
    "user-inventory": 8252,
    "user-tax": 8253,
    "user-fulfillment": 8254,
    "user-sharing": 8255,
    "user-project": 8260,
    "user-developer": 8261,
    "user-training": 8262,
    "user-artifact": 8291,
    "user-connector": 8292,
    "user-project-sharing": 8270,
}


def base_url(service: str) -> str:
    """Resolve a service's base URL for the active target environment."""
    port = PORTS[service]
    if TARGET == "local":
        return f"http://{LOCAL_HOST}:{port}"
    # incluster: SN-IDC or GCP-GKE — identical K8s service-DNS shape
    return f"http://{service}.{NAMESPACE}.svc.cluster.local:{port}"


def all_services() -> list[str]:
    return sorted(PORTS)
