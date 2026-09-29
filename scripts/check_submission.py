"""Submission checker for CivicPulse — Assignment 01.

Run from the repository root:

    python scripts/check_submission.py

This is a *lint*, not a grader. It catches the mechanical failures that cause
automatic deductions (§5.3) and the structural requirements listed in the
rubric (§4). A clean run does not guarantee a good mark; a failing run nearly
guarantees a bad one.

Exit codes:
    0 — no failures (warnings may still be present)
    1 — one or more FAIL items detected
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BOLD = "\033[1m"
RESET = "\033[0m"

_failures: list[str] = []
_warnings: list[str] = []
_passes: list[str] = []


class _CheckResult(NamedTuple):
    level: str  # "PASS" | "WARN" | "FAIL"
    message: str


def _emit(level: str, message: str) -> None:
    colour = {
        "PASS": GREEN,
        "WARN": YELLOW,
        "FAIL": RED,
    }[level]
    print(f"  {colour}{BOLD}[{level}]{RESET} {message}")
    if level == "FAIL":
        _failures.append(message)
    elif level == "WARN":
        _warnings.append(message)
    else:
        _passes.append(message)


def _check(condition: bool, pass_msg: str, fail_msg: str, *, warn: bool = False) -> None:
    if condition:
        _emit("PASS", pass_msg)
    elif warn:
        _emit("WARN", fail_msg)
    else:
        _emit("FAIL", fail_msg)


def _section(title: str) -> None:
    print(f"\n{BOLD}{'─' * 60}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{'─' * 60}{RESET}")


def _file_contains(path: Path, pattern: str) -> bool:
    """Return True if *path* exists and contains *pattern* (plain string)."""
    try:
        return pattern in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _file_matches(path: Path, regex: str, flags: int = 0) -> bool:
    """Return True if *path* exists and its content matches *regex*."""
    try:
        return bool(re.search(regex, path.read_text(encoding="utf-8", errors="replace"), flags))
    except OSError:
        return False


def _count_files(directory: Path, pattern: str = "*.py") -> int:
    if not directory.exists():
        return 0
    return len(list(directory.rglob(pattern)))


def _yaml_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# § 5.3 Automatic-Deduction Checks  (each costs marks if present)
# ---------------------------------------------------------------------------


def check_no_secrets_in_git() -> None:
    _section("§5.3 · Secrets / Credentials in Git  (−20 / −15 per violation)")

    # Run git log to check if .env or key files were ever committed
    try:
        result = subprocess.run(
            ["git", "log", "--all", "--name-only", "--pretty=format:", "--diff-filter=A"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        committed_files = result.stdout.lower().splitlines()
    except FileNotFoundError:
        _emit("WARN", "git not found; cannot check for committed secrets")
        return

    dotenv_committed = any(f.strip().endswith(".env") and f.strip() != ".env.example"
                           for f in committed_files)
    _check(
        not dotenv_committed,
        ".env was never committed to Git history",
        ".env appears to have been committed — rotate all credentials immediately  [−20]",
    )

    # Check .gitignore contains .env
    gitignore = ROOT / ".gitignore"
    _check(
        _file_contains(gitignore, ".env"),
        ".env is in .gitignore",
        ".env is NOT in .gitignore — it could accidentally be committed  [−20 risk]",
    )

    # Check .env.example exists
    _check(
        (ROOT / ".env.example").exists(),
        ".env.example committed (safe template present)",
        ".env.example is missing — collaborators have no credentials template",
        warn=True,
    )

    # Check no raw-looking API keys in committed YAML/Python files (heuristic)
    suspicious_patterns = [
        (r"(?i)(groq_api_key|gemini_api_key|openai_api_key)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}",
         "Possible LLM API key literal found in"),
        (r"(?i)sk-[A-Za-z0-9]{20,}", "OpenAI-style key literal found in"),
    ]
    secret_hits: list[str] = []
    for candidate in ROOT.rglob("*"):
        if not candidate.is_file():
            continue
        # Skip node_modules, .venv, .git, build outputs
        rel = candidate.relative_to(ROOT)
        parts = rel.parts
        if any(p in parts for p in ("node_modules", ".venv", ".git", "dist", "__pycache__",
                                     ".pytest_cache", "civicpulse_backend.egg-info")):
            continue
        if candidate.suffix not in (".py", ".yml", ".yaml", ".env", ".json", ".ts", ".tsx", ".js"):
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for regex, label in suspicious_patterns:
            if re.search(regex, text):
                # Ignore placeholder-style values like "${...}" or "CHANGE_ME_IN_CLUSTER".
                # Must use finditer (full match) not findall (only the captured group),
                # otherwise the placeholder filter never sees the value.
                real_matches = [
                    m.group(0) for m in re.finditer(regex, text)
                    if not re.search(
                        r"(\$\{|your[-_]|<|>|placeholder|CHANGE_ME|CHANGE|xxx|example|INSERT|REPLACE|TODO|IN_CLUSTER|IN_PROD)",
                        m.group(0), re.I,
                    )
                ]
                if real_matches:
                    secret_hits.append(f"{label} {rel}")

    _check(
        not secret_hits,
        "No raw API key literals detected in source files",
        "Possible key literals found:\n    " + "\n    ".join(secret_hits[:5]) + "  [−20]",
    )

    # Check k8s secrets don't have real base64-encoded values
    k8s_secret = ROOT / "k8s" / "base" / "secret.yaml"
    if k8s_secret.exists():
        text = k8s_secret.read_text(encoding="utf-8", errors="replace")
        real_b64 = re.findall(r":\s+([A-Za-z0-9+/]{20,}={0,2})\s*$", text, re.MULTILINE)
        placeholder_patterns = re.compile(
            r"(CHANGE_ME|placeholder|your[-_]|<[^>]+>|REPLACE|TODO|xxx|==\s*$|changeit|password123)",
            re.I,
        )
        suspicious_b64 = [v for v in real_b64 if not placeholder_patterns.search(v) and len(v) > 20]
        _check(
            not suspicious_b64,
            "k8s/base/secret.yaml contains only placeholders (no real base64 values)",
            "k8s/base/secret.yaml may contain real base64-encoded secrets  [−15]",
        )


# ---------------------------------------------------------------------------
# Image / compose checks
# ---------------------------------------------------------------------------


def check_images_pinned() -> None:
    _section("§5.3 · Unpinned Base Images  (−8 per violation)")

    unpinned_patterns = [
        # bare image name with no tag at all (e.g. "image: postgres")
        r"^\s*image:\s+(postgres|redis|node|python|nginx|ollama/ollama)\s*$",
        # explicit :latest tag
        r"^\s*image:\s+\S+:latest",
        r"^FROM\s+\S+:latest",
    ]

    files_to_check = [
        ROOT / "compose.yaml",
        ROOT / "compose.prod.yaml",
        ROOT / "backend" / "Dockerfile",
        ROOT / "frontend" / "Dockerfile",
    ]

    for f in files_to_check:
        if not f.exists():
            _emit("WARN", f"{f.relative_to(ROOT)} not found — cannot check image pinning")
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        hits = []
        for pat in unpinned_patterns:
            for m in re.finditer(pat, text, re.MULTILINE):
                hits.append(m.group(0).strip())
        _check(
            not hits,
            f"{f.relative_to(ROOT)}: all images appear pinned",
            f"{f.relative_to(ROOT)}: unpinned image(s) detected: {hits[:3]}  [−8]",
        )

    # Check :latest is not referenced anywhere in CD workflow deploy step
    cd = ROOT / ".github" / "workflows" / "cd.yml"
    if cd.exists():
        text = cd.read_text(encoding="utf-8", errors="replace")
        _check(
            ":latest" not in text or "push" in text,   # push :latest is OK, deploy :latest is not
            "cd.yml does not deploy :latest (deploy-by-SHA pattern expected)",
            "cd.yml appears to deploy :latest — use the commit SHA instead  [−8]",
            warn=True,
        )


def check_compose_networks() -> None:
    _section("§5.3 / §3.2 · Docker Compose — Network Segmentation  (−8 if missing)")

    compose = ROOT / "compose.yaml"
    prod = ROOT / "compose.prod.yaml"

    for path in (compose, prod):
        if not path.exists():
            _emit("WARN", f"{path.name} not found")
            continue
        text = _yaml_text(path)
        name = path.name

        _check(
            "internal: true" in text,
            f"{name}: 'internal: true' declared on the internal network",
            f"{name}: 'internal: true' is MISSING — DB is reachable from the outside  [−8]",
        )

        # frontend should only be on edge, not internal
        # Simple heuristic: look for frontend stanza and check it doesn't reference internal
        frontend_section = re.search(
            r"frontend:.*?(?=\n\w|\Z)", text, re.DOTALL
        )
        if frontend_section:
            frontend_text = frontend_section.group(0)
            _check(
                "internal" not in frontend_text,
                f"{name}: frontend service does not join the internal network",
                f"{name}: frontend appears to join the internal network — segmentation broken  [−8]",
            )

    # Check no published port on DB or cache in prod file
    if prod.exists():
        text = _yaml_text(prod)
        # Extract only the service stanza for postgres and redis by looking for
        # the block up to the next top-level service key or end-of-services block.
        services_block = re.search(r"^services:(.*?)^(networks|volumes):", text, re.MULTILINE | re.DOTALL)
        svc_text = services_block.group(1) if services_block else text

        for label in ("postgres", "redis"):
            # Match the stanza for this service up to the next sibling service
            pattern = rf"^\s{{2}}{label}:(.*?)(?=^\s{{2}}\w|\Z)"
            section = re.search(pattern, svc_text, re.MULTILINE | re.DOTALL)
            if section:
                svc_block = section.group(0)
                # Ignore comment lines when checking for ports:
                non_comment_lines = [
                    l for l in svc_block.splitlines()
                    if not l.lstrip().startswith("#")
                ]
                has_ports = any(
                    re.match(r"\s+ports:", l) for l in non_comment_lines
                )
                _check(
                    not has_ports,
                    f"compose.prod.yaml: {label} has no published port",
                    f"compose.prod.yaml: {label} has a published port — data service must not be exposed  [−8]",
                )


def check_compose_volumes() -> None:
    _section("§3.2 · Docker Compose — Named Volumes")

    for fname in ("compose.yaml", "compose.prod.yaml"):
        path = ROOT / fname
        if not path.exists():
            _emit("WARN", f"{fname} not found")
            continue
        text = _yaml_text(path)
        for vol in ("pgdata", "redisdata", "ollama_models"):
            _check(
                vol in text,
                f"{fname}: volume '{vol}' declared",
                f"{fname}: volume '{vol}' missing  [rubric G]",
                warn=True,
            )


def check_compose_healthchecks() -> None:
    _section("§3.2 · Docker Compose — Healthchecks & depends_on")

    for fname in ("compose.yaml", "compose.prod.yaml"):
        path = ROOT / fname
        if not path.exists():
            continue
        text = _yaml_text(path)
        _check(
            text.count("healthcheck:") >= 4,
            f"{fname}: at least 4 healthchecks found",
            f"{fname}: fewer than 4 healthchecks — every service needs one  [rubric G]",
        )
        _check(
            "service_healthy" in text,
            f"{fname}: 'service_healthy' condition used in depends_on",
            f"{fname}: depends_on is not using 'service_healthy' condition  [rubric G]",
        )

    # Dev compose must have a bind mount for hot reload
    dev = ROOT / "compose.yaml"
    if dev.exists():
        _check(
            _file_contains(dev, "./backend:/app"),
            "compose.yaml: dev bind mount (./backend:/app) present for hot reload",
            "compose.yaml: dev bind mount missing — hot reload won't work",
            warn=True,
        )

    # Prod compose must NOT have build: keys
    prod = ROOT / "compose.prod.yaml"
    if prod.exists():
        prod_text = _yaml_text(prod)
        # Strip comment lines so "# No build:" comments don't cause false positives
        non_comment = "\n".join(
            l for l in prod_text.splitlines() if not l.lstrip().startswith("#")
        )
        _check(
            "build:" not in non_comment,
            "compose.prod.yaml: no 'build:' key (deploy uses pre-built images)",
            "compose.prod.yaml: 'build:' key found — prod should deploy pre-built images  [−8 risk]",
        )
        _check(
            "IMAGE_TAG" in prod_text,
            "compose.prod.yaml: IMAGE_TAG used for backend/frontend images",
            "compose.prod.yaml: IMAGE_TAG not referenced — build-once-deploy-many broken  [−8 risk]",
        )


def check_localhost_references() -> None:
    _section("§5.3 · localhost for Service-to-Service Communication  (−8)")

    backend_app = ROOT / "backend" / "app"
    if not backend_app.exists():
        _emit("WARN", "backend/app/ directory not found")
        return

    hits: list[str] = []
    skip_names = {"config.py"}  # config files may reference localhost as a default
    for py in backend_app.rglob("*.py"):
        if py.name in skip_names:
            continue
        text = py.read_text(encoding="utf-8", errors="replace")
        # Flag hardcoded localhost:NNNN URLs (not in comments/strings that look like examples)
        for m in re.finditer(r"['\"]https?://localhost:\d+", text):
            line_no = text[: m.start()].count("\n") + 1
            hits.append(f"{py.relative_to(ROOT)}:{line_no}")

    _check(
        not hits,
        "No hardcoded localhost service URLs in backend/app/",
        "Hardcoded localhost URLs found (breaks Compose/k8s networking):\n    "
        + "\n    ".join(hits[:5]) + "  [−8]",
    )


# ---------------------------------------------------------------------------
# Kubernetes checks
# ---------------------------------------------------------------------------


def check_k8s_structure() -> None:
    _section("§3.3 · Kubernetes Manifests")

    k8s = ROOT / "k8s"
    base = k8s / "base"
    overlays_dev = k8s / "overlays" / "dev"
    overlays_prod = k8s / "overlays" / "prod"

    _check(base.exists(), "k8s/base/ exists", "k8s/base/ is missing  [rubric H]")
    _check(overlays_dev.exists(), "k8s/overlays/dev/ exists", "k8s/overlays/dev/ missing  [rubric H]", warn=True)
    _check(overlays_prod.exists(), "k8s/overlays/prod/ exists", "k8s/overlays/prod/ missing  [rubric H]")

    required_manifests = [
        "namespace.yaml", "backend.yaml", "frontend.yaml",
        "postgres.yaml", "redis.yaml", "ingress.yaml",
        "configmap.yaml", "secret.yaml", "hpa.yaml",
    ]
    for name in required_manifests:
        path = base / name
        _check(path.exists(), f"k8s/base/{name} exists", f"k8s/base/{name} MISSING  [rubric H]")

    # Postgres must be a StatefulSet, not a Deployment
    pg = base / "postgres.yaml"
    if pg.exists():
        text = _yaml_text(pg)
        _check(
            "StatefulSet" in text,
            "postgres.yaml uses StatefulSet (correct)",
            "postgres.yaml is NOT a StatefulSet — a Deployment for DB is a marked error  [rubric H]",
        )
        _check(
            "volumeClaimTemplates" in text,
            "postgres.yaml has volumeClaimTemplates",
            "postgres.yaml missing volumeClaimTemplates — data will be lost on pod restart  [rubric H]",
        )

    # Namespace must be civicpulse, never default
    ns = base / "namespace.yaml"
    if ns.exists():
        text = _yaml_text(ns)
        _check(
            "civicpulse" in text,
            "namespace.yaml declares 'civicpulse' namespace",
            "namespace.yaml does not mention 'civicpulse'  [rubric H]",
        )

    # Check HPA uses autoscaling/v2
    hpa = base / "hpa.yaml"
    if hpa.exists():
        text = _yaml_text(hpa)
        _check(
            "autoscaling/v2" in text,
            "hpa.yaml uses autoscaling/v2 API",
            "hpa.yaml does not use autoscaling/v2  [rubric H]",
        )

    # Backend must never be a NodePort/LoadBalancer
    backend_yaml = base / "backend.yaml"
    if backend_yaml.exists():
        text = _yaml_text(backend_yaml)
        _check(
            "NodePort" not in text and "LoadBalancer" not in text,
            "backend.yaml: no NodePort or LoadBalancer on backend Service",
            "backend.yaml: backend Service uses NodePort/LoadBalancer — should be ClusterIP  [rubric H]",
            warn=True,
        )

    # Secret manifest must contain only placeholders
    secret_yaml = base / "secret.yaml"
    if secret_yaml.exists():
        text = _yaml_text(secret_yaml)
        _check(
            re.search(r"(CHANGE_ME|placeholder|<[^>]+>|YOUR_|changeit)", text, re.I) is not None
            or re.search(r"data:", text) is None,
            "k8s/base/secret.yaml has placeholder values only",
            "k8s/base/secret.yaml may contain real secrets — committed manifests must be safe  [−15]",
        )

    # VPA present
    vpa = base / "vpa.yaml"
    _check(vpa.exists(), "k8s/base/vpa.yaml present (VPA recommender mode)", "k8s/base/vpa.yaml missing  [rubric H]", warn=True)
    if vpa.exists():
        text = _yaml_text(vpa)
        _check(
            'updateMode: "Off"' in text or "updateMode: Off" in text,
            "VPA is in Off (recommender) mode — correct",
            "VPA updateMode is not 'Off' — HPA+VPA Auto mode fight over CPU  [rubric H]",
        )

    # PDB present
    pdb = base / "pdb.yaml"
    _check(pdb.exists(), "k8s/base/pdb.yaml present (PodDisruptionBudget)", "k8s/base/pdb.yaml missing  [rubric H]", warn=True)


def check_k8s_probes() -> None:
    _section("§3.3 · Kubernetes Probes (startup / liveness / readiness)")

    backend_yaml = ROOT / "k8s" / "base" / "backend.yaml"
    if not backend_yaml.exists():
        _emit("WARN", "k8s/base/backend.yaml not found — skipping probe checks")
        return

    text = _yaml_text(backend_yaml)
    for probe in ("startupProbe", "livenessProbe", "readinessProbe"):
        _check(
            probe in text,
            f"backend Deployment declares {probe}",
            f"backend Deployment missing {probe}  [rubric H]",
        )

    # Liveness must use /health, readiness must use /ready
    _check(
        re.search(r"livenessProbe.*?/health", text, re.DOTALL) is not None,
        "livenessProbe points to /health (does not touch DB)",
        "livenessProbe path is not /health  [rubric H]",
    )
    _check(
        re.search(r"readinessProbe.*?/ready", text, re.DOTALL) is not None,
        "readinessProbe points to /ready (depends on DB)",
        "readinessProbe path is not /ready  [rubric H]",
    )

    # resources.requests must be set
    _check(
        "requests:" in text,
        "resources.requests declared (required for HPA to function)",
        "resources.requests missing — HPA will show <unknown>/60% and never scale  [rubric H]",
    )


# ---------------------------------------------------------------------------
# CI/CD checks
# ---------------------------------------------------------------------------


def check_github_workflows() -> None:
    _section("§3.4 · GitHub Actions Workflows")

    workflows_dir = ROOT / ".github" / "workflows"
    _check(workflows_dir.exists(), ".github/workflows/ directory exists", ".github/workflows/ missing")

    for fname in ("ci.yml", "cd.yml", "release.yml"):
        path = workflows_dir / fname
        _check(path.exists(), f"{fname} present", f"{fname} MISSING  [rubric I]")

    ci = workflows_dir / "ci.yml"
    if ci.exists():
        text = _yaml_text(ci)
        for job in ("lint", "test", "build", "scan", "integration"):
            _check(
                job in text,
                f"ci.yml contains a '{job}' job",
                f"ci.yml is missing a '{job}' job  [rubric I]",
                warn=True,
            )
        _check(
            "TRIAGE_PROVIDER" in text and "simulated" in text,
            "ci.yml pins TRIAGE_PROVIDER=simulated for deterministic tests",
            "ci.yml does not set TRIAGE_PROVIDER=simulated — tests may be non-deterministic  [rubric F]",
        )
        _check(
            "trivy" in text.lower() or "scan" in text.lower(),
            "ci.yml includes an image scan step (Trivy)",
            "ci.yml missing image scan (Trivy)  [rubric I]",
            warn=True,
        )
        _check(
            "kubeconform" in text.lower() or "manifests" in text.lower(),
            "ci.yml validates k8s manifests (kubeconform/kustomize)",
            "ci.yml missing manifest validation step  [rubric I]",
            warn=True,
        )

    cd = workflows_dir / "cd.yml"
    if cd.exists():
        text = _yaml_text(cd)
        _check(
            "needs:" in text,
            "cd.yml uses 'needs:' to gate publishing/deploy jobs",
            "cd.yml is missing 'needs:' — publishing job not gated  [−8]",
        )
        _check(
            "github.sha" in text or "GITHUB_SHA" in text,
            "cd.yml deploys by commit SHA (not :latest)",
            "cd.yml does not reference github.sha — may be deploying :latest  [−8]",
        )
        _check(
            "packages: write" in text or "GITHUB_TOKEN" in text,
            "cd.yml uses GITHUB_TOKEN for GHCR (scoped token)",
            "cd.yml does not appear to use GITHUB_TOKEN for registry auth  [rubric I]",
            warn=True,
        )
        _check(
            "permissions:" in text,
            "cd.yml declares a permissions: block (least-privilege)",
            "cd.yml missing permissions: block — uses overly broad default  [rubric I]",
            warn=True,
        )

    # Check Actions are pinned to at least @vN (ideally commit SHA)
    for fname in ("ci.yml", "cd.yml"):
        path = workflows_dir / fname
        if not path.exists():
            continue
        text = _yaml_text(path)
        uses_latest = re.findall(r"uses:\s+\S+@latest", text)
        _check(
            not uses_latest,
            f"{fname}: no Action pinned to @latest",
            f"{fname}: Actions pinned to @latest: {uses_latest}  [rubric I]",
        )


# ---------------------------------------------------------------------------
# Backend structure checks
# ---------------------------------------------------------------------------


def check_backend_structure() -> None:
    _section("§2.2 · Backend — Four-Layer Architecture")

    app = ROOT / "backend" / "app"
    if not app.exists():
        _emit("FAIL", "backend/app/ directory not found")
        return

    for layer in ("routes", "services", "repositories", "providers"):
        path = app / (layer + ".py")
        path_dir = app / layer
        _check(
            path.exists() or path_dir.exists(),
            f"Layer '{layer}' exists (as module or package)",
            f"Layer '{layer}' missing — four-layer separation required  [rubric C]",
        )

    # Triage provider implementations
    triage_dir = app / "providers" / "triage"
    for impl in ("base.py", "llm.py", "rules.py", "simulated.py", "factory.py"):
        _check(
            (triage_dir / impl).exists(),
            f"providers/triage/{impl} exists",
            f"providers/triage/{impl} MISSING  [rubric F]",
        )

    # Check health.py or equivalent exists
    _check(
        (app / "health.py").exists() or _file_contains(app / "routes.py", "/health"),
        "health endpoints present (health.py or in routes.py)",
        "No health endpoint implementation found  [rubric C]",
        warn=True,
    )

    # Alembic
    alembic_dir = ROOT / "backend" / "alembic"
    _check(
        alembic_dir.exists() and (alembic_dir / "versions").exists(),
        "alembic/versions/ directory present (migrations managed properly)",
        "alembic/versions/ missing — schema DDL must use migrations  [rubric D]",
    )
    alembic_versions = list((alembic_dir / "versions").glob("*.py")) if alembic_dir.exists() else []
    _check(
        len(alembic_versions) >= 1,
        f"{len(alembic_versions)} Alembic migration(s) found",
        "No Alembic migration files found — you need at least the initial schema  [rubric D]",
    )

    # Check no CREATE TABLE in main.py / startup code
    main_py = app / "main.py"
    if main_py.exists():
        _check(
            "CREATE TABLE" not in main_py.read_text(encoding="utf-8", errors="replace").upper(),
            "main.py does not contain 'CREATE TABLE' (no DDL in startup code)",
            "main.py contains 'CREATE TABLE' — use Alembic migrations instead  [rubric D]",
        )

    # Seed command
    seed_py = app / "seed.py"
    backend_scripts = ROOT / "backend" / "scripts"
    _check(
        seed_py.exists() or (backend_scripts.exists() and any(backend_scripts.glob("seed*.py"))),
        "Seed script found (seed.py or scripts/seed*.py)",
        "No seed script found — §2.3 requires ≥30 idempotent complaints  [rubric D]",
    )


def check_backend_api_endpoints() -> None:
    _section("§2.2 · Backend — API Endpoint Contract")

    app_dir = ROOT / "backend" / "app"
    routes = app_dir / "routes.py"
    main_py = app_dir / "main.py"
    health_py = app_dir / "health.py"

    # Gather all backend Python source as one blob for pattern matching.
    # FastAPI uses APIRouter with a prefix, so "/complaints" in routes.py
    # becomes "/api/complaints" once registered in main.py — we check both.
    all_backend_src = ""
    for pyfile in app_dir.rglob("*.py"):
        try:
            all_backend_src += pyfile.read_text(encoding="utf-8", errors="replace") + "\n"
        except OSError:
            pass

    # Endpoint checks: (description, search terms to find in backend source)
    endpoint_checks = [
        ("POST /api/complaints", ["/complaints", "post"]),
        ("GET /api/complaints (list)", ["/complaints", "get"]),
        ("GET /api/complaints/{id}", ["complaints/{", "complaint_id"]),
        ("PATCH /api/complaints/{id}/status", ["status", "patch"]),
        ("GET /api/stats", ["/stats"]),
        ("GET /api/meta/providers", ["/meta/providers", "providers"]),
        ("GET /health (liveness)", ["/health"]),
        ("GET /ready (readiness)", ["/ready"]),
        ("GET /metrics", ["/metrics"]),
    ]

    for label, terms in endpoint_checks:
        found = all(
            re.search(re.escape(term), all_backend_src, re.IGNORECASE) for term in terms
        )
        _check(
            found,
            f"Endpoint {label} found in backend source",
            f"Endpoint {label} NOT found in backend source  [rubric C]",
        )

    # State machine check
    services = app_dir / "services.py"
    if services.exists():
        s_text = services.read_text(encoding="utf-8", errors="replace")
        _check(
            "in_progress" in s_text and "resolved" in s_text and "rejected" in s_text,
            "Status state machine transitions appear in services.py",
            "Status state machine (open/in_progress/resolved/rejected) not detected  [rubric C]",
        )
        _check(
            "409" in s_text or "HTTPException" in s_text,
            "services.py raises HTTPException/409 for invalid transitions",
            "No 409 logic detected for invalid status transitions  [rubric C]",
            warn=True,
        )


def check_backend_tests() -> None:
    _section("§3.4 · Backend Tests  (≥14 tests, ≥65% coverage)")

    tests_dir = ROOT / "backend" / "tests"
    if not tests_dir.exists():
        _emit("FAIL", "backend/tests/ directory not found")
        return

    test_files = list(tests_dir.glob("test_*.py"))
    _check(
        len(test_files) >= 5,
        f"Found {len(test_files)} test file(s) in backend/tests/",
        f"Only {len(test_files)} test file(s) — expected several covering routes, services, triage  [rubric C]",
        warn=(len(test_files) >= 3),
    )

    # Count test functions
    total_tests = 0
    for tf in test_files:
        text = tf.read_text(encoding="utf-8", errors="replace")
        total_tests += len(re.findall(r"^async def test_|^def test_", text, re.MULTILINE))
    _check(
        total_tests >= 14,
        f"Found ~{total_tests} test function(s) — meets ≥14 requirement",
        f"Found ~{total_tests} test function(s) — rubric requires ≥14  [rubric C]",
    )

    # Injection test
    all_test_text = "\n".join(
        tf.read_text(encoding="utf-8", errors="replace") for tf in test_files
    )
    _check(
        re.search(r"inject|ignore.{0,30}instruction|prompt.{0,20}inject", all_test_text, re.I) is not None,
        "Prompt-injection test detected",
        "No prompt-injection test found — required by rubric F  [rubric F]",
        warn=True,
    )

    # Fallback test
    _check(
        re.search(r"fallback|rules:fallback|triaged_by.*fallback", all_test_text, re.I) is not None,
        "Provider fallback test detected (provider raises → rules:fallback → 201)",
        "No fallback test found — this is the critical test (rubric F)  [rubric F]",
        warn=True,
    )


# ---------------------------------------------------------------------------
# Frontend checks
# ---------------------------------------------------------------------------


def check_frontend_structure() -> None:
    _section("§2.1 · Frontend Structure")

    fe = ROOT / "frontend"
    src = fe / "src"

    for sub in ("components", "pages", "api"):
        _check(
            (src / sub).exists(),
            f"frontend/src/{sub}/ directory exists",
            f"frontend/src/{sub}/ missing  [rubric B]",
            warn=True,
        )

    # No baked-in API URL (runtime config check)
    vite_config = fe / "vite.config.ts"
    env_example = ROOT / ".env.example"
    if vite_config.exists():
        text = vite_config.read_text(encoding="utf-8", errors="replace")
        _check(
            "proxy" in text or "VITE_API_URL" not in text,
            "vite.config.ts uses a proxy — no baked-in API URL (runtime config correct)",
            "vite.config.ts may bake in an API URL — use nginx proxy or runtime config.js  [rubric B]",
            warn=True,
        )

    # Frontend tests
    fe_tests = fe / "tests"
    fe_test_count = 0
    if fe_tests.exists():
        for tf in fe_tests.rglob("*.test.*"):
            text = tf.read_text(encoding="utf-8", errors="replace")
            fe_test_count += len(re.findall(r"\bit\(|\btest\(", text))
    _check(
        fe_test_count >= 5,
        f"Found ~{fe_test_count} frontend test(s) — meets ≥5 requirement",
        f"Found ~{fe_test_count} frontend test(s) — rubric requires ≥5  [rubric B]",
        warn=(fe_test_count >= 3),
    )

    # Multi-stage Dockerfile check
    fe_dockerfile = fe / "Dockerfile"
    if fe_dockerfile.exists():
        text = fe_dockerfile.read_text(encoding="utf-8", errors="replace")
        from_count = len(re.findall(r"^FROM\s+", text, re.MULTILINE))
        _check(
            from_count >= 2,
            f"Frontend Dockerfile has {from_count} stages (multi-stage build)",
            "Frontend Dockerfile is single-stage — Node toolchain will be in the final image  [rubric G]",
        )
        _check(
            "nginx" in text.lower(),
            "Frontend Dockerfile uses nginx to serve the built assets",
            "Frontend Dockerfile does not appear to use nginx  [rubric G]",
        )
        _check(
            "USER" in text,
            "Frontend Dockerfile sets a non-root USER",
            "Frontend Dockerfile does not set USER — container runs as root  [rubric G]",
            warn=True,
        )

    # Backend Dockerfile
    be_dockerfile = ROOT / "backend" / "Dockerfile"
    if be_dockerfile.exists():
        text = be_dockerfile.read_text(encoding="utf-8", errors="replace")
        from_count = len(re.findall(r"^FROM\s+", text, re.MULTILINE))
        _check(
            from_count >= 2,
            f"Backend Dockerfile has {from_count} stages (multi-stage build)",
            "Backend Dockerfile is single-stage  [rubric G]",
        )
        _check(
            "USER" in text,
            "Backend Dockerfile sets a non-root USER",
            "Backend Dockerfile does not set USER — runs as root  [rubric G]",
        )
        _check(
            "HEALTHCHECK" in text,
            "Backend Dockerfile declares HEALTHCHECK",
            "Backend Dockerfile missing HEALTHCHECK  [rubric G]",
            warn=True,
        )


# ---------------------------------------------------------------------------
# Documentation checks
# ---------------------------------------------------------------------------


def check_documentation() -> None:
    _section("§4-J · Documentation")

    docs = ROOT / "docs"
    _check(docs.exists(), "docs/ directory exists", "docs/ directory missing  [rubric J]")

    for fname in ("ENGINEERING-NOTES.md", "RUNBOOK.md", "AI-USAGE.md"):
        _check(
            (docs / fname).exists(),
            f"docs/{fname} present",
            f"docs/{fname} MISSING  [rubric J]",
        )

    adr_dir = docs / "adr"
    _check(adr_dir.exists(), "docs/adr/ directory exists", "docs/adr/ missing  [rubric J]")
    if adr_dir.exists():
        adrs = list(adr_dir.glob("*.md"))
        _check(
            len(adrs) >= 4,
            f"{len(adrs)} ADR(s) found (need ≥4)",
            f"Only {len(adrs)} ADR(s) found — need all 4 (provider, runtime-config, deploy-SHA, PII)  [rubric J]",
        )
        for slug in ("provider", "runtime", "sha", "pii"):
            _check(
                any(slug in adr.name.lower() or _file_contains(adr, slug) for adr in adrs),
                f"ADR covering '{slug}' found",
                f"No ADR covering '{slug}' — check docs/adr/  [rubric J]",
                warn=True,
            )

    evidence_dir = docs / "evidence"
    _check(
        evidence_dir.exists() and any(evidence_dir.iterdir()),
        "docs/evidence/ exists and contains files (screenshots/captures)",
        "docs/evidence/ is empty or missing — rubric A/H requires evidence files  [rubric A+H]",
        warn=True,
    )

    # README checks
    readme = ROOT / "README.md"
    _check(readme.exists(), "README.md present", "README.md MISSING")
    if readme.exists():
        text = readme.read_text(encoding="utf-8", errors="replace")
        for keyword in ("docker compose", "mermaid", "api", "screenshot"):
            _check(
                keyword.lower() in text.lower(),
                f"README.md mentions '{keyword}'",
                f"README.md does not mention '{keyword}'  [rubric J]",
                warn=True,
            )

    # Engineering notes — eight questions
    eng_notes = docs / "ENGINEERING-NOTES.md"
    if eng_notes.exists():
        text = eng_notes.read_text(encoding="utf-8", errors="replace")
        # Heuristic: look for numbered sections or keywords from the 8 questions
        keywords = ["Dockerfile", "CI/CD", "build-once", "probabilistic", "HPA", "VPA", "internal", "failure"]
        found = sum(1 for kw in keywords if kw.lower() in text.lower())
        _check(
            found >= 6,
            f"ENGINEERING-NOTES.md appears to address {found}/8 of the required questions",
            f"ENGINEERING-NOTES.md only addresses ~{found}/8 required questions  [rubric J]",
            warn=(found >= 4),
        )


# ---------------------------------------------------------------------------
# Git hygiene checks
# ---------------------------------------------------------------------------


def check_git_hygiene() -> None:
    _section("§4-A · Collaboration — Git Hygiene")

    try:
        result = subprocess.run(
            ["git", "shortlog", "-sn", "--all"],
            capture_output=True, text=True, cwd=ROOT,
        )
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        _check(
            len(lines) >= 2,
            f"{len(lines)} contributor(s) found in git shortlog (≥2 expected)",
            f"Only {len(lines)} contributor(s) — partner contributions not visible  [rubric A]",
            warn=True,
        )

        total_commits = sum(int(l.split()[0]) for l in lines if l)
        _check(
            total_commits >= 35,
            f"{total_commits} total commits — meets ≥35 requirement",
            f"Only {total_commits} commits — rubric A requires ≥35  [rubric A]",
        )

        # Check minimum 35% per author
        if total_commits > 0 and len(lines) >= 2:
            for line in lines:
                parts = line.split()
                count = int(parts[0])
                author = " ".join(parts[1:])
                pct = count / total_commits * 100
                _check(
                    pct >= 35,
                    f"  {author}: {count} commits ({pct:.0f}%) — above 35% floor",
                    f"  {author}: {count} commits ({pct:.0f}%) — below 35% floor  [rubric A]",
                    warn=(pct >= 25),
                )

    except FileNotFoundError:
        _emit("WARN", "git not found — cannot check commit counts")

    # Conventional commit prefixes
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-50"],
            capture_output=True, text=True, cwd=ROOT,
        )
        messages = result.stdout.splitlines()
        conventional = sum(
            1 for m in messages
            if re.match(r"[0-9a-f]+ (feat|fix|docs|chore|test|refactor|style|ci|build|perf)(\(.*?\))?: ", m)
        )
        _check(
            conventional >= len(messages) * 0.6,
            f"{conventional}/{len(messages)} recent commits use conventional prefixes",
            f"Only {conventional}/{len(messages)} recent commits use conventional prefixes  [rubric A]",
            warn=True,
        )
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# .env.example / .gitignore
# ---------------------------------------------------------------------------


def check_env_files() -> None:
    _section("§3.2 / §5.3 · Environment Configuration")

    _check(
        (ROOT / ".env.example").exists(),
        ".env.example committed",
        ".env.example missing  [rubric G]",
    )
    _check(
        not (ROOT / ".env").exists() or _file_contains(ROOT / ".gitignore", ".env"),
        ".env exists only locally (gitignored)",
        ".env present AND not gitignored — risk of accidental commit  [−20 risk]",
    )

    # Check .env.example has no real secrets (placeholder values)
    example = ROOT / ".env.example"
    if example.exists():
        text = example.read_text(encoding="utf-8", errors="replace")
        real_key = re.search(r"(GROQ|GEMINI|OPENAI)_API_KEY\s*=\s*[A-Za-z0-9_\-]{20,}", text)
        _check(
            real_key is None,
            ".env.example contains no real API key values",
            ".env.example appears to contain a real API key  [−20 risk]",
        )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def print_summary() -> None:
    total = len(_passes) + len(_warnings) + len(_failures)
    print(f"\n{'═' * 60}")
    print(f"{BOLD}  SUMMARY{RESET}")
    print(f"{'═' * 60}")
    print(f"  {GREEN}{BOLD}PASS{RESET}  {len(_passes)}")
    print(f"  {YELLOW}{BOLD}WARN{RESET}  {len(_warnings)}")
    print(f"  {RED}{BOLD}FAIL{RESET}  {len(_failures)}")
    print(f"  {'─' * 30}")
    print(f"  TOTAL {total} checks")

    if _failures:
        print(f"\n{RED}{BOLD}  ✗ Failing items (fix before submitting):{RESET}")
        for msg in _failures:
            print(f"    • {msg}")

    if not _failures and not _warnings:
        print(f"\n{GREEN}{BOLD}  ✓ All checks passed.{RESET}")
        print("  Remember: a clean run is necessary but not sufficient.")
        print("  The viva multiplies your mark — understand every line.")
    elif not _failures:
        print(f"\n{YELLOW}{BOLD}  ⚠  Warnings above are non-fatal but worth addressing.{RESET}")
    else:
        print(f"\n{RED}{BOLD}  ✗ Fix FAIL items before submitting.{RESET}")

    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    print(f"\n{BOLD}CivicPulse — Submission Checker{RESET}")
    print(f"Repository root: {ROOT}")
    print("(This is a lint, not a grader. See §5.8 of the assignment spec.)\n")

    check_no_secrets_in_git()
    check_images_pinned()
    check_env_files()
    check_compose_networks()
    check_compose_volumes()
    check_compose_healthchecks()
    check_localhost_references()
    check_k8s_structure()
    check_k8s_probes()
    check_github_workflows()
    check_backend_structure()
    check_backend_api_endpoints()
    check_backend_tests()
    check_frontend_structure()
    check_documentation()
    check_git_hygiene()

    print_summary()
    sys.exit(1 if _failures else 0)


if __name__ == "__main__":
    main()
