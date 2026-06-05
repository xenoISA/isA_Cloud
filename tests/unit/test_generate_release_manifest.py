#!/usr/bin/env python3
"""L1/L2 tests for the release-manifest generator (ADR 0007 phase 1, #320).

Covers:
  * version validation / normalization
  * manifest JSON shape (platform_version, generated_at injected, services, charts)
  * image-bearing vs libs-only filtering
  * digest-pinned vs :tag fallback refs
  * offline-bundle CSV columns EXACTLY match SN's offline-bundle-manifest.csv
  * digest-resolve path is mocked (offline-safe)
  * end-to-end main() writes a valid manifest + CSV with a fixed timestamp

The generator lives at deployments/release/generate-release-manifest.py (a
hyphenated, non-importable filename), so it is loaded by path via importlib.
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GEN_PATH = REPO_ROOT / "deployments" / "release" / "generate-release-manifest.py"
SN_CSV = (
    Path.home()
    / "Documents/fun/sn/sn_cloud/docs/implementation-delivery/production/assets"
    / "offline-bundle/offline-bundle-manifest.csv"
)

FIXED_TS = "2026-06-05T00:00:00Z"

FAKE_SERVICES = {
    "agent": {
        "repo": "isA_Agent",
        "image": "ghcr.io/xenoisa/isa-agent",
        "has_image": True,
        "approx_size": "~1GB",
    },
    "mcp": {
        "repo": "isA_MCP",
        "image": "ghcr.io/xenoisa/isa-mcp",
        "has_image": True,
        "approx_size": "~2GB",
    },
    "vibe": {"repo": "isA_Vibe", "has_image": False, "note": "lib/tooling, no image"},
}


def _load_gen():
    spec = importlib.util.spec_from_file_location("gen_release_manifest", GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gen():
    return _load_gen()


class TestValidateVersion:
    def test_plain_semver(self, gen):
        assert gen.validate_version("1.2.3") == "1.2.3"

    def test_strips_v_and_platform_prefix(self, gen):
        assert gen.validate_version("v1.2.3") == "1.2.3"
        assert gen.validate_version("platform-v1.2.3") == "1.2.3"

    def test_prerelease_ok(self, gen):
        assert gen.validate_version("1.2.3-rc1") == "1.2.3-rc1"

    @pytest.mark.parametrize("bad", ["", "1.2", "latest", "abc", "v1"])
    def test_rejects_junk(self, gen, bad):
        with pytest.raises(ValueError):
            gen.validate_version(bad)


class TestImageRef:
    def test_tag_fallback(self, gen):
        assert (
            gen.image_ref("ghcr.io/xenoisa/isa-agent", "1.0.0", None)
            == "ghcr.io/xenoisa/isa-agent:1.0.0"
        )

    def test_digest_pinned(self, gen):
        ref = gen.image_ref("ghcr.io/xenoisa/isa-agent", "1.0.0", "sha256:deadbeef")
        assert ref == "ghcr.io/xenoisa/isa-agent@sha256:deadbeef"


class TestHarborTarget:
    def test_maps_to_harbor_isa_project_with_version_tag(self, gen):
        t = gen.harbor_target(
            "ghcr.io/xenoisa/isa-mcp", "1.0.0", "sha256:x", "harbor.prod.sn.local"
        )
        assert t == "harbor.prod.sn.local/isa/isa-mcp:1.0.0"

    def test_custom_host(self, gen):
        t = gen.harbor_target(
            "ghcr.io/xenoisa/isa-mcp", "1.0.0", None, "harbor.example.com"
        )
        assert t == "harbor.example.com/isa/isa-mcp:1.0.0"


class TestBuildManifest:
    def test_shape_and_injected_timestamp(self, gen):
        m = gen.build_manifest(
            FAKE_SERVICES,
            "1.0.0",
            FIXED_TS,
            {"isa-service": "1.0.0", "isa-bigdata": "1.0.0"},
        )
        assert m["platform_version"] == "1.0.0"
        assert m["generated_at"] == FIXED_TS  # injected, not computed
        assert m["charts"] == {"isa-service": "1.0.0", "isa-bigdata": "1.0.0"}

    def test_excludes_libs_only(self, gen):
        m = gen.build_manifest(FAKE_SERVICES, "1.0.0", FIXED_TS, {})
        assert "isa-vibe" not in m["services"]
        assert set(m["services"]) == {"isa-agent", "isa-mcp"}

    def test_tag_fallback_when_no_digest(self, gen):
        m = gen.build_manifest(FAKE_SERVICES, "1.0.0", FIXED_TS, {})
        assert m["services"]["isa-agent"] == "ghcr.io/xenoisa/isa-agent:1.0.0"

    def test_digest_pinned_when_resolved(self, gen):
        m = gen.build_manifest(
            FAKE_SERVICES, "1.0.0", FIXED_TS, {}, digests={"agent": "sha256:abc123"}
        )
        assert m["services"]["isa-agent"] == "ghcr.io/xenoisa/isa-agent@sha256:abc123"


class TestBuildBundleRows:
    def test_columns_and_action(self, gen):
        rows = gen.build_bundle_rows(FAKE_SERVICES, "1.0.0", "harbor.prod.sn.local")
        assert {r["component"] for r in rows} == {"isa-agent", "isa-mcp"}
        for r in rows:
            assert set(r) == set(gen.CSV_COLUMNS)
            assert r["action"] == "MIRROR"
            assert r["category"] == "platform-service"

    def test_source_ref_digest_pinned(self, gen):
        rows = gen.build_bundle_rows(
            FAKE_SERVICES, "1.0.0", "h", digests={"mcp": "sha256:zzz"}
        )
        mcp = next(r for r in rows if r["component"] == "isa-mcp")
        assert mcp["source_ref"] == "ghcr.io/xenoisa/isa-mcp@sha256:zzz"
        assert mcp["harbor_target"] == "h/isa/isa-mcp:1.0.0"


class TestCsvColumnsMatchSN:
    @pytest.mark.skipif(
        not SN_CSV.is_file(),
        reason="SN offline-bundle-manifest.csv not present locally",
    )
    def test_header_matches_sn_format(self, gen):
        import csv as _csv

        with SN_CSV.open(newline="") as f:
            sn_header = next(_csv.reader(f))
        assert gen.CSV_COLUMNS == sn_header


class TestResolveDigestMocked:
    def test_returns_none_offline_when_no_skopeo(self, gen, monkeypatch):
        monkeypatch.setattr(gen, "_have", lambda cmd: False)
        assert gen.resolve_digest("ghcr.io/xenoisa/isa-agent", "1.0.0") is None

    def test_parses_skopeo_digest(self, gen, monkeypatch):
        monkeypatch.setattr(gen, "_have", lambda cmd: True)

        class _R:
            stdout = "sha256:cafebabe\n"

        monkeypatch.setattr(gen.subprocess, "run", lambda *a, **k: _R())
        assert (
            gen.resolve_digest("ghcr.io/xenoisa/isa-agent", "1.0.0")
            == "sha256:cafebabe"
        )

    def test_swallows_subprocess_error(self, gen, monkeypatch):
        import subprocess as _sp

        monkeypatch.setattr(gen, "_have", lambda cmd: True)

        def _boom(*a, **k):
            raise _sp.CalledProcessError(1, "skopeo")

        monkeypatch.setattr(gen.subprocess, "run", _boom)
        assert gen.resolve_digest("ghcr.io/xenoisa/isa-agent", "1.0.0") is None


class TestResolveGeneratedAt:
    def test_arg_wins(self, gen, monkeypatch):
        monkeypatch.delenv("RELEASE_GENERATED_AT", raising=False)
        assert gen.resolve_generated_at(FIXED_TS) == FIXED_TS

    def test_env_fallback(self, gen, monkeypatch):
        monkeypatch.setenv("RELEASE_GENERATED_AT", "2030-01-01T00:00:00Z")
        assert gen.resolve_generated_at(None) == "2030-01-01T00:00:00Z"

    def test_errors_when_neither(self, gen, monkeypatch):
        monkeypatch.delenv("RELEASE_GENERATED_AT", raising=False)
        with pytest.raises(ValueError):
            gen.resolve_generated_at(None)


class TestMainEndToEnd:
    def test_writes_valid_manifest_and_csv(self, gen, tmp_path, monkeypatch):
        import csv as _csv
        import yaml

        services_file = tmp_path / "platform-services.yaml"
        services_file.write_text(
            yaml.safe_dump({"registry": "ghcr.io/xenoisa", "services": FAKE_SERVICES})
        )
        out_dir = tmp_path / "releases"

        rc = gen.main(
            [
                "--version",
                "2.0.0",
                "--generated-at",
                FIXED_TS,
                "--services-file",
                str(services_file),
                "--out-dir",
                str(out_dir),
                "--harbor-host",
                "harbor.prod.sn.local",
            ]
        )
        assert rc == 0

        manifest_path = out_dir / "platform-v2.0.0.json"
        csv_path = out_dir / "platform-v2.0.0.offline-bundle.csv"
        assert manifest_path.is_file() and csv_path.is_file()

        m = json.loads(manifest_path.read_text())  # valid JSON
        assert m["platform_version"] == "2.0.0"
        assert m["generated_at"] == FIXED_TS
        assert m["services"]["isa-agent"] == "ghcr.io/xenoisa/isa-agent:2.0.0"
        assert "isa-vibe" not in m["services"]

        with csv_path.open(newline="") as f:
            reader = _csv.DictReader(f)
            assert reader.fieldnames == gen.CSV_COLUMNS
            comps = {r["component"] for r in reader}
        assert comps == {"isa-agent", "isa-mcp"}

    def test_bad_version_returns_nonzero(self, gen, tmp_path):
        rc = gen.main(
            [
                "--version",
                "nope",
                "--generated-at",
                FIXED_TS,
                "--out-dir",
                str(tmp_path),
            ]
        )
        assert rc == 2
