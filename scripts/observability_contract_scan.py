#!/usr/bin/env python3
"""Scan service code for likely observability contract violations.

This is intentionally lightweight: it uses the Python AST for service source
checks and a text-level ServiceMonitor pass for manifests. It is meant as a
preflight for deployable service repositories, not as a full static analyzer.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_SERVICES = (
    "isa-mcp",
    "isa-model",
    "isa-agent",
    "isa-data",
    "isa-user",
    "isa-trade",
    "isa-creative",
    "isa-mate",
    "isa-os",
)

DEFAULT_SERVICE_MONITOR_PATHS = (
    "deployments/kubernetes/production/manifests/app-service-monitors.yaml",
    "deployments/kubernetes/production/manifests/prometheus-service-monitors.yaml",
)

DEFAULT_SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
        "node_modules",
        "site-packages",
        "venv",
    }
)

DOC_TEST_PARTS = frozenset({"docs", "doc", "examples", "example", "tests", "test"})

DEFAULT_ALLOW_GLOBS = (
    # isa_common is the approved implementation of this contract, so it must
    # be able to import prometheus_client and configure an OTel provider.
    "isA_common/**",
    "isa_common/**",
)


@dataclass(frozen=True)
class Finding:
    """A single scanner finding."""

    rule: str
    severity: str
    path: str
    line: int
    message: str
    service: Optional[str] = None


@dataclass(frozen=True)
class ScanSummary:
    """Result metadata used by tests and CLI output."""

    scanned_files: int
    findings: List[Finding]

    @property
    def error_count(self) -> int:
        return sum(1 for finding in self.findings if finding.severity == "error")


def normalize_service_name(name: str) -> str:
    """Normalize service names to the Kubernetes app label style."""
    normalized = name.strip().replace("_", "-").lower()
    if normalized.startswith("isa-"):
        return normalized
    if normalized.startswith("isa"):
        return "isa-" + normalized[3:].lstrip("-")
    return normalized


def _relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _matches_any(path: Path, repo_root: Path, patterns: Iterable[str]) -> bool:
    rel = _relative(path, repo_root)
    return any(fnmatch.fnmatch(rel, pattern) for pattern in patterns)


def _is_doc_or_test_path(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return bool(parts & DOC_TEST_PARTS)


def should_scan_python_file(
    path: Path,
    repo_root: Path,
    *,
    include_docs_tests: bool = False,
    allow_globs: Sequence[str] = DEFAULT_ALLOW_GLOBS,
) -> bool:
    """Return True when a Python file is in the service-enforcement scope."""
    if path.suffix != ".py":
        return False
    if _matches_any(path, repo_root, allow_globs):
        return False
    if not include_docs_tests and _is_doc_or_test_path(path):
        return False
    return True


def iter_python_files(
    roots: Sequence[Path],
    repo_root: Path,
    *,
    include_docs_tests: bool = False,
    excludes: Sequence[str] = (),
    allow_globs: Sequence[str] = DEFAULT_ALLOW_GLOBS,
) -> Iterable[Tuple[Path, Path]]:
    """Yield ``(scan_root, file)`` pairs for Python files in scope."""
    for root in roots:
        root = root.resolve()
        if root.is_file():
            if should_scan_python_file(
                root,
                repo_root,
                include_docs_tests=include_docs_tests,
                allow_globs=allow_globs,
            ) and not _matches_any(root, repo_root, excludes):
                yield root.parent, root
            continue

        for dirpath, dirnames, filenames in os.walk(str(root)):
            current = Path(dirpath)
            dirnames[:] = [
                name
                for name in dirnames
                if name not in DEFAULT_SKIP_DIRS
                and not _matches_any(current / name, repo_root, excludes)
                and (include_docs_tests or not _is_doc_or_test_path(current / name))
            ]

            for filename in filenames:
                path = current / filename
                if _matches_any(path, repo_root, excludes):
                    continue
                if should_scan_python_file(
                    path,
                    repo_root,
                    include_docs_tests=include_docs_tests,
                    allow_globs=allow_globs,
                ):
                    yield root, path


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parent = _call_name(func.value)
        if parent:
            return parent + "." + func.attr
        return func.attr
    return ""


def _root_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return _root_name(func.value)
    return ""


def _first_string_arg(node: ast.Call) -> Optional[str]:
    if not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _is_metrics_route_call(node: ast.Call) -> bool:
    first = _first_string_arg(node)
    if first != "/metrics":
        return False

    func_name = _call_name(node.func)
    if func_name in {"Route", "starlette.routing.Route"} or func_name.endswith(".Route"):
        return True

    if isinstance(node.func, ast.Attribute):
        root = _root_name(node.func)
        if node.func.attr in {"get", "route", "add_route"}:
            return root in {"app", "api", "router"} or root.endswith("router")

    return False


def _is_prometheus_import(module: str) -> bool:
    return module == "prometheus_client" or module.startswith("prometheus_client.")


def _is_instrumentator_import(module: str) -> bool:
    return module == "prometheus_fastapi_instrumentator" or module.startswith(
        "prometheus_fastapi_instrumentator."
    )


def _is_setup_observability_call(func_name: str) -> bool:
    leaf = func_name.rsplit(".", 1)[-1].lstrip("_")
    return leaf == "setup_observability"


class ObservabilityVisitor(ast.NodeVisitor):
    """AST visitor for Python observability contract checks."""

    def __init__(self, path: Path, repo_root: Path) -> None:
        self.path = path
        self.repo_root = repo_root
        self.findings: List[Finding] = []
        self.setup_observability_calls: List[int] = []

    def _add(self, rule: str, node: ast.AST, message: str, severity: str = "error") -> None:
        self.findings.append(
            Finding(
                rule=rule,
                severity=severity,
                path=_relative(self.path, self.repo_root),
                line=getattr(node, "lineno", 0),
                message=message,
            )
        )

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if _is_prometheus_import(alias.name):
                self._add(
                    "raw-prometheus-client",
                    node,
                    "raw prometheus_client import; use isa_common.metrics factories",
                )
            if _is_instrumentator_import(alias.name):
                self._add(
                    "prometheus-fastapi-instrumentator",
                    node,
                    "prometheus-fastapi-instrumentator competes with isa_common.metrics",
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        imported_names = {alias.name for alias in node.names}

        if _is_prometheus_import(module):
            self._add(
                "raw-prometheus-client",
                node,
                "raw prometheus_client import; use isa_common.metrics factories",
            )
        if _is_instrumentator_import(module):
            self._add(
                "prometheus-fastapi-instrumentator",
                node,
                "prometheus-fastapi-instrumentator competes with isa_common.metrics",
            )
        if module == "opentelemetry.sdk.trace" and "TracerProvider" in imported_names:
            self._add(
                "raw-tracer-provider",
                node,
                "raw TracerProvider import; use isa_common.tracing/setup_observability",
            )
        if module == "opentelemetry.trace" and "set_tracer_provider" in imported_names:
            self._add(
                "raw-tracer-provider",
                node,
                "raw set_tracer_provider import; use isa_common.tracing/setup_observability",
            )

        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if node.name == "PrometheusMiddleware":
            self._add(
                "custom-prometheus-middleware",
                node,
                "custom PrometheusMiddleware competes with isa_common.metrics middleware",
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func_name = _call_name(node.func)

        if _is_setup_observability_call(func_name):
            self.setup_observability_calls.append(getattr(node, "lineno", 0))

        if func_name.endswith("set_tracer_provider"):
            self._add(
                "raw-tracer-provider",
                node,
                "raw set_tracer_provider call; use isa_common.tracing/setup_observability",
            )

        if _is_metrics_route_call(node):
            self._add(
                "custom-metrics-route",
                node,
                "custom /metrics route; use isa_common.metrics/setup_observability",
            )

        if func_name.endswith("add_middleware") and node.args:
            first = node.args[0]
            middleware_name = _call_name(first)
            if middleware_name.rsplit(".", 1)[-1] == "PrometheusMiddleware":
                self._add(
                    "custom-prometheus-middleware",
                    node,
                    "custom PrometheusMiddleware registered; use isa_common.metrics middleware",
                )

        self.generic_visit(node)


def scan_python_roots(
    roots: Sequence[Path],
    repo_root: Path,
    *,
    include_docs_tests: bool = False,
    excludes: Sequence[str] = (),
    allow_globs: Sequence[str] = DEFAULT_ALLOW_GLOBS,
) -> ScanSummary:
    """Scan Python files for contract violations."""
    findings: List[Finding] = []
    scanned_files = 0
    setup_calls_by_root: Dict[Path, List[Tuple[Path, int]]] = {}

    for scan_root, path in iter_python_files(
        roots,
        repo_root,
        include_docs_tests=include_docs_tests,
        excludes=excludes,
        allow_globs=allow_globs,
    ):
        scanned_files += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            findings.append(
                Finding(
                    rule="python-parse-error",
                    severity="warning",
                    path=_relative(path, repo_root),
                    line=exc.lineno or 0,
                    message="could not parse Python file; scanner skipped AST checks",
                )
            )
            continue

        visitor = ObservabilityVisitor(path, repo_root)
        visitor.visit(tree)
        findings.extend(visitor.findings)
        if visitor.setup_observability_calls:
            setup_calls_by_root.setdefault(scan_root, []).extend(
                (path, line) for line in visitor.setup_observability_calls
            )

    for root, calls in sorted(setup_calls_by_root.items(), key=lambda item: item[0].as_posix()):
        if len(calls) <= 1:
            continue
        first_path, first_line = calls[0]
        locations = ", ".join(
            "{}:{}".format(_relative(path, repo_root), line) for path, line in calls
        )
        findings.append(
            Finding(
                rule="multiple-setup-observability",
                severity="error",
                path=_relative(first_path, repo_root),
                line=first_line,
                service=root.name,
                message=(
                    "setup_observability() is called {} times under {}; expected one "
                    "startup/lifespan entrypoint. Locations: {}"
                ).format(len(calls), _relative(root, repo_root), locations),
            )
        )

    return ScanSummary(scanned_files=scanned_files, findings=sorted_findings(findings))


def sorted_findings(findings: Sequence[Finding]) -> List[Finding]:
    return sorted(findings, key=lambda finding: (finding.path, finding.line, finding.rule))


def _service_monitor_blocks(text: str) -> Iterable[str]:
    for block in re.split(r"^---\s*$", text, flags=re.MULTILINE):
        if re.search(r"^\s*kind:\s*ServiceMonitor\s*$", block, flags=re.MULTILINE):
            yield block


def collect_service_monitor_refs(paths: Sequence[Path]) -> Dict[str, List[str]]:
    """Return normalized service references found in ServiceMonitor manifests."""
    refs: Dict[str, List[str]] = {}
    value_re = re.compile(r"^\s*(?:name|app):\s*['\"]?([A-Za-z0-9_.-]+)", re.MULTILINE)

    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for block in _service_monitor_blocks(text):
            for raw_value in value_re.findall(block):
                service = normalize_service_name(raw_value)
                refs.setdefault(service, []).append(path.as_posix())
    return refs


def service_monitor_findings(
    services: Sequence[str],
    monitor_paths: Sequence[Path],
    repo_root: Path,
) -> List[Finding]:
    """Check that each configured service has a ServiceMonitor reference."""
    existing_paths = [path for path in monitor_paths if path.is_file()]
    if not existing_paths:
        return []

    refs = collect_service_monitor_refs(existing_paths)
    findings: List[Finding] = []
    manifest_path = _relative(existing_paths[0], repo_root)

    for service in services:
        normalized = normalize_service_name(service)
        present = any(
            ref == normalized or ref.startswith(normalized + "-") for ref in refs
        )
        if not present:
            findings.append(
                Finding(
                    rule="missing-service-monitor",
                    severity="error",
                    path=manifest_path,
                    line=0,
                    service=normalized,
                    message=(
                        "no ServiceMonitor reference found for {}; add a production "
                        "ServiceMonitor or pass --skip-service-monitor-check"
                    ).format(normalized),
                )
            )

    return findings


def default_monitor_paths(repo_root: Path) -> List[Path]:
    return [repo_root / rel for rel in DEFAULT_SERVICE_MONITOR_PATHS]


def scan(
    roots: Sequence[Path],
    repo_root: Path,
    *,
    include_docs_tests: bool = False,
    excludes: Sequence[str] = (),
    allow_globs: Sequence[str] = DEFAULT_ALLOW_GLOBS,
    services: Sequence[str] = DEFAULT_SERVICES,
    monitor_paths: Optional[Sequence[Path]] = None,
    check_service_monitors: bool = True,
) -> ScanSummary:
    """Run all observability contract checks."""
    summary = scan_python_roots(
        roots,
        repo_root,
        include_docs_tests=include_docs_tests,
        excludes=excludes,
        allow_globs=allow_globs,
    )
    findings = list(summary.findings)

    if check_service_monitors:
        if monitor_paths is None:
            monitor_paths = default_monitor_paths(repo_root)
        findings.extend(service_monitor_findings(services, monitor_paths, repo_root))

    return ScanSummary(scanned_files=summary.scanned_files, findings=sorted_findings(findings))


def print_text(summary: ScanSummary) -> None:
    print("Observability contract scan")
    print("  scanned Python files: {}".format(summary.scanned_files))
    print("  findings: {} error(s), {} total".format(summary.error_count, len(summary.findings)))

    if not summary.findings:
        print("  no likely contract violations found")
        return

    for finding in summary.findings:
        location = finding.path
        if finding.line:
            location = "{}:{}".format(location, finding.line)
        service = " [{}]".format(finding.service) if finding.service else ""
        print(
            "{} {}{} {} - {}".format(
                finding.severity.upper(),
                finding.rule,
                service,
                location,
                finding.message,
            )
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan deployable service code for isa_common observability drift."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="service source roots or files to scan (default: current repo)",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="repository root used for relative output and default ServiceMonitor paths",
    )
    parser.add_argument(
        "--include-docs-tests",
        action="store_true",
        help="include docs, examples, and tests in Python scanning",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="glob path to exclude; may be repeated",
    )
    parser.add_argument(
        "--allow-path",
        action="append",
        default=[],
        help="glob path to ignore even if it contains scanner patterns; may be repeated",
    )
    parser.add_argument(
        "--service",
        action="append",
        default=[],
        help="service expected to have ServiceMonitor coverage; may be repeated",
    )
    parser.add_argument(
        "--service-monitor",
        action="append",
        default=[],
        help="ServiceMonitor manifest to check; may be repeated",
    )
    parser.add_argument(
        "--skip-service-monitor-check",
        action="store_true",
        help="disable ServiceMonitor coverage check",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="print findings but exit 0",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    roots = [Path(path).resolve() for path in args.paths]
    allow_globs = tuple(DEFAULT_ALLOW_GLOBS) + tuple(args.allow_path)
    services = tuple(args.service) if args.service else DEFAULT_SERVICES

    if args.service_monitor:
        monitor_paths = [Path(path).resolve() for path in args.service_monitor]
    else:
        monitor_paths = default_monitor_paths(repo_root)

    summary = scan(
        roots,
        repo_root,
        include_docs_tests=args.include_docs_tests,
        excludes=tuple(args.exclude),
        allow_globs=allow_globs,
        services=services,
        monitor_paths=monitor_paths,
        check_service_monitors=not args.skip_service_monitor_check,
    )

    if args.format == "json":
        print(
            json.dumps(
                {
                    "scanned_files": summary.scanned_files,
                    "error_count": summary.error_count,
                    "findings": [asdict(finding) for finding in summary.findings],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print_text(summary)

    if summary.error_count and not args.warn_only:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
