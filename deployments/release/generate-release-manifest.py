#!/usr/bin/env python3
"""generate-release-manifest.py — platform release manifest + offline-bundle CSV.

ADR 0007 (docs/adr/0007-artifact-delivery.md), phase 1 — the release-manifest
generator. Given a platform version, it reads the data-driven source list
(platform-services.yaml), optionally resolves each GHCR image to an immutable
@sha256 digest, and writes two artifacts under releases/:

  * platform-vX.Y.Z.json          — the release manifest (single source of truth
                                     for "what is platform vX.Y.Z").
  * platform-vX.Y.Z.offline-bundle.csv
                                   — the SN offline bundle, populated in the SAME
                                     column shape as
                                     sn_cloud/.../offline-bundle/offline-bundle-manifest.csv
                                     so SN's existing mirror-to-harbor.sh consumes it.

Design constraints (ADR 0007, task brief):
  * Timestamp is INJECTED (--generated-at / $RELEASE_GENERATED_AT), never
    datetime.now() inline — manifests are reproducible / testable.
  * Digest resolution is best-effort: with --resolve-digests it queries the
    registry; unreachable images fall back to the :X.Y.Z tag. Offline-safe.
  * Pure additive: reads charts' Chart.yaml only to record their version (= the
    platform version at release per ADR 0007 §3); does not mutate anything.

Usage:
  generate-release-manifest.py --version 1.2.3
  generate-release-manifest.py --version 1.2.3 --resolve-digests
  generate-release-manifest.py --version 1.2.3 \
      --generated-at 2026-06-05T00:00:00Z --harbor-host harbor.prod.sn.local

Exit non-zero on bad input; prints the two output paths on success.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml  # PyYAML
except ImportError:  # pragma: no cover - import guard
    sys.stderr.write("error: PyYAML required (pip install pyyaml)\n")
    raise

# --- Constants ---------------------------------------------------------------

DEFAULT_HARBOR_HOST = "harbor.prod.sn.local"
HARBOR_PROJECT = "isa"  # harbor.<host>/isa/<image>:<ref>  (white-label sanitizer -> sn)

# Column order MUST match SN's offline-bundle-manifest.csv so mirror-to-harbor.sh
# (which reads via csv.DictReader on these headers) can consume our output.
CSV_COLUMNS = [
    "category",
    "component",
    "source_ref",
    "harbor_target",
    "approx_size",
    "action",
    "notes",
]

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+].+)?$")


# --- Pure helpers (unit-testable, no I/O) ------------------------------------


def validate_version(version: str) -> str:
    """Return a normalized X.Y.Z (strip a leading v/platform-v). Raise on junk."""
    v = version.strip()
    v = re.sub(r"^(platform-)?v", "", v)
    if not SEMVER_RE.match(v):
        raise ValueError(f"invalid platform version: {version!r} (want X.Y.Z)")
    return v


def image_ref(image: str, version: str, digest: Optional[str]) -> str:
    """Build the image reference: digest-pinned if available, else :version tag."""
    if digest:
        return f"{image}@{digest}"
    return f"{image}:{version}"


def harbor_target(image: str, version: str, digest: Optional[str], host: str) -> str:
    """Map a GHCR image to its Harbor target: <host>/isa/<name>:<version>.

    Harbor target always uses the :version tag (Harbor re-tags on push); the
    immutable digest lives in the source_ref. Strips the ghcr.io/<org>/ prefix.
    """
    name = image.rsplit("/", 1)[-1]
    return f"{host}/{HARBOR_PROJECT}/{name}:{version}"


def build_manifest(
    services_cfg: Dict[str, Any],
    version: str,
    generated_at: str,
    chart_versions: Dict[str, str],
    digests: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build the release-manifest dict (ADR 0007 §2). Pure — no I/O.

    services_cfg: the parsed platform-services.yaml "services" mapping.
    digests:      optional {service_name: "sha256:..."} resolved refs.
    """
    digests = digests or {}
    services: Dict[str, str] = {}
    for name, meta in sorted(services_cfg.items()):
        if not meta.get("has_image"):
            continue
        image = meta["image"]
        services[f"isa-{name.replace('_', '-')}"] = image_ref(
            image, version, digests.get(name)
        )
    return {
        "platform_version": version,
        "generated_at": generated_at,
        "services": services,
        "charts": chart_versions,
    }


def build_bundle_rows(
    services_cfg: Dict[str, Any],
    version: str,
    host: str,
    digests: Optional[Dict[str, str]] = None,
) -> list[dict]:
    """Build offline-bundle CSV rows for image-bearing platform services.

    Action = MIRROR (mirror-to-harbor.sh acts on MIRROR/PIN/DRIFT/WEIGHTS rows).
    source_ref is digest-pinned when resolved (immutable, per FW-OUT-001).
    """
    digests = digests or {}
    rows: list[dict] = []
    for name, meta in sorted(services_cfg.items()):
        if not meta.get("has_image"):
            continue
        image = meta["image"]
        digest = digests.get(name)
        note = "platform image (edition-agnostic); pinned by release manifest"
        if not digest:
            note += "; tag fallback — resolve digest before mirror"
        rows.append(
            {
                "category": "platform-service",
                "component": f"isa-{name.replace('_', '-')}",
                "source_ref": image_ref(image, version, digest),
                "harbor_target": harbor_target(image, version, digest, host),
                "approx_size": meta.get("approx_size", "~1GB"),
                "action": "MIRROR",
                "notes": note,
            }
        )
    return rows


# --- I/O boundary ------------------------------------------------------------


def resolve_digest(image: str, version: str) -> Optional[str]:
    """Query the registry for the :version manifest digest. Best-effort.

    Returns "sha256:..." or None if unreachable / not found / no tooling.
    Prefers `skopeo inspect`; this is mocked/skipped in offline tests.
    """
    if not _have("skopeo"):
        return None
    try:
        out = subprocess.run(
            [
                "skopeo",
                "inspect",
                "--format",
                "{{.Digest}}",
                f"docker://{image}:{version}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        d = out.stdout.strip()
        return d if d.startswith("sha256:") else None
    except (subprocess.SubprocessError, OSError):
        return None


def _have(cmd: str) -> bool:
    from shutil import which

    return which(cmd) is not None


def read_chart_version(chart_yaml: Path) -> Optional[str]:
    """Read .version from a Chart.yaml (for recording; not the release version)."""
    if not chart_yaml.is_file():
        return None
    with chart_yaml.open() as f:
        data = yaml.safe_load(f) or {}
    return data.get("version")


def load_services(path: Path) -> Dict[str, Any]:
    with path.open() as f:
        cfg = yaml.safe_load(f) or {}
    services = cfg.get("services")
    if not isinstance(services, dict) or not services:
        raise ValueError(f"{path}: no 'services' mapping found")
    return services


# --- CLI ---------------------------------------------------------------------


def resolve_generated_at(arg: Optional[str]) -> str:
    """Timestamp resolution order: --generated-at arg, $RELEASE_GENERATED_AT.

    Never calls datetime.now() — the timestamp must be injected so manifests are
    reproducible and testable. If neither is provided, error out (explicit).
    """
    ts = arg or os.environ.get("RELEASE_GENERATED_AT")
    if not ts:
        raise ValueError(
            "no timestamp: pass --generated-at or set $RELEASE_GENERATED_AT "
            "(injected, never computed, for reproducible manifests)"
        )
    return ts


def main(argv: Optional[list[str]] = None) -> int:
    here = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(
        description="Generate a platform release manifest + offline-bundle CSV (ADR 0007)."
    )
    p.add_argument("--version", required=True, help="platform version X.Y.Z")
    p.add_argument(
        "--generated-at",
        default=None,
        help="ISO-8601 timestamp (injected; falls back to $RELEASE_GENERATED_AT)",
    )
    p.add_argument(
        "--resolve-digests",
        action="store_true",
        help="query the registry for @sha256 digests (falls back to :version tags offline)",
    )
    p.add_argument(
        "--harbor-host",
        default=DEFAULT_HARBOR_HOST,
        help=f"Harbor host (default {DEFAULT_HARBOR_HOST})",
    )
    p.add_argument("--services-file", default=str(here / "platform-services.yaml"))
    p.add_argument(
        "--out-dir",
        default=str(here / "releases"),
        help="output dir for manifest + CSV",
    )
    p.add_argument(
        "--charts-root",
        default=str((here.parent / "charts")),
        help="dir containing isa-service chart (default deployments/charts)",
    )
    p.add_argument(
        "--umbrella-root",
        default=str((here.parent / "umbrella")),
        help="dir containing isa-bigdata umbrella (default deployments/umbrella)",
    )
    args = p.parse_args(argv)

    try:
        version = validate_version(args.version)
        generated_at = resolve_generated_at(args.generated_at)
        services_cfg = load_services(Path(args.services_file))
    except (ValueError, FileNotFoundError, OSError) as e:
        sys.stderr.write(f"error: {e}\n")
        return 2

    # Chart versions: = platform version at release (ADR 0007 §3). We record the
    # release version (what `package-charts.sh` will stamp), not the on-disk 0.1.0.
    chart_versions = {"isa-service": version, "isa-bigdata": version}

    digests: Dict[str, str] = {}
    if args.resolve_digests:
        for name, meta in services_cfg.items():
            if not meta.get("has_image"):
                continue
            d = resolve_digest(meta["image"], version)
            if d:
                digests[name] = d
        resolved = len(digests)
        total = sum(1 for m in services_cfg.values() if m.get("has_image"))
        sys.stderr.write(
            f"resolved {resolved}/{total} digests (rest fall back to :{version})\n"
        )

    manifest = build_manifest(
        services_cfg, version, generated_at, chart_versions, digests
    )
    rows = build_bundle_rows(services_cfg, version, args.harbor_host, digests)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / f"platform-v{version}.json"
    csv_path = out_dir / f"platform-v{version}.offline-bundle.csv"

    with manifest_path.open("w") as f:
        json.dump(manifest, f, indent=2, sort_keys=False)
        f.write("\n")

    write_bundle_csv(csv_path, rows)

    print(str(manifest_path))
    print(str(csv_path))
    return 0


def write_bundle_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)


if __name__ == "__main__":
    raise SystemExit(main())
