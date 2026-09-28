# Engineering Notes

Answers to the eight questions in §5.2 of the assignment brief, plus the
required index justification and the graceful-shutdown decision, all with
references to files in this repository.

---

## 1. Three things that differ between a laptop and a CI runner, and the line that freezes each

1. **Installed toolchain / OS packages.** A laptop may have a different Python
   or Node patch level than the runner. Frozen by the pinned base images:
   `backend/Dockerfile:1` (`FROM python:3.12-slim AS builder`) and
   `frontend/Dockerfile:1` (`FROM node:22-alpine AS build`). Both CI and the
   laptop build the *same* base layer.

2. **Third-party library versions.** A developer's global `pip`/`npm` cache can
   resolve newer versions than a teammate's. Frozen by exact pins in
   `backend/pyproject.toml:7-15` (e.g. `"fastapi==0.115.6"`,
   `"sqlalchemy==2.0.37"`) and by `package.json`, which pins `react`, `vite`
   etc. exactly (no `^`/`~`).

3. **Which triage provider is live.** On a laptop a developer may export a real
   `GROQ_API_KEY` and set `TRIAGE_PROVIDER=llm`; a CI runner must never depend
   on a paid/rate-limited third party. Frozen by
   `backend/tests/conftest.py:16` (`os.environ["TRIAGE_PROVIDER"] = "simulated"`)
   so the suite always runs the deterministic provider, and by the default in
   `backend/app/config.py:11` (`triage_provider: str = "simulated"`).

## 2. Position on the CI/CD maturity ladder

Honest current state: the repository sits at the **"Continuous Integration"
rung, partially built**. Source, tests, and container definitions exist and the
test suite is runnable and deterministic by design (`conftest.py:16`), but the
automated workflow files are **not yet committed** — `.github/workflows/` does
not exist in this revision, so nothing runs on push yet.

The next rung is **Continuous Delivery**: a `ci.yml` that runs lint/type-check,
the backend and frontend suites, Trivy, and a kubeconform manifest check on
every PR, plus a gated `cd.yml` (`needs:` on every publishing job) that pushes
SHA-tagged images to GHCR and deploys them to an ephemeral cluster. That rung
buys exactly what this project cannot yet claim: a red check that blocks a
merge, and an artefact that is proven deployable because it was built, scanned,
and smoke-tested by the pipeline rather than by hand.

## 3. The line guaranteeing build-once-deploy-many

The guarantee is the nginx proxy in `frontend/nginx.conf:5`:

```
location /api/ { proxy_pass http://backend:8000/api/; ... }
```

The frontend requests the relative path `/api/...` (`frontend/src/api.ts:41`,
`64`, `72`, `88`); it never learns an absolute backend URL. Because the backend
address is resolved at *request* time by Docker DNS (or by a Kubernetes
Service/Ingress), the same built image runs behind `localhost:8080`, the Compose
network, or an Ingress without a rebuild. See ADR 0002.

**What breaks without it:** if the API URL were injected via
`import.meta.env.VITE_API_URL`, Vite would inline it into the JavaScript at
build time. The image would then be environment-specific — promoting it from
staging to production would require a rebuild, which is precisely the
build-once-deploy-many property the split is meant to provide. It would also
reintroduce an absolute origin and CORS.

## 4. What "correct" means for a probabilistic component, and how CI stays deterministic

With `TRIAGE_PROVIDER=llm` the provider is a third-party model: the same input
can yield different output. So "correct" cannot mean "returns this exact
category". For the `TriageProvider` contract
(`backend/app/providers/triage/base.py:29-32`) "correct" means:

- the return value is a **valid `TriageResult`** — `category` and `priority`
  are members of the enums, `summary` is 1–140 chars, `confidence` is in
  `[0.0, 1.0]` (`base.py:22-26`);
- the call is **bounded** (10 s timeout) and **recoverable** — on failure the
  service falls back to `RuleBasedTriage` and records `triaged_by =
  "rules:fallback"` (`backend/app/services.py:76-95`);
- the endpoint still returns **201**, never a 500, when the model is
  rate-limited or wrong (`tests/test_services.py:40-64`).

CI stays deterministic by never calling a real model. `conftest.py:16` forces
`TRIAGE_PROVIDER=simulated`; `SimulatedTriage`
(`backend/app/providers/triage/simulated.py`) is seeded, offline, and can inject
failure (`should_fail=True`). Malformed output is exercised by injecting a fake
provider, not by hoping the model misbehaves
(`tests/test_services.py:68-100`). No test sleeps or retries for a pass.

## 5 & 6. HPA lag and VPA in Off mode

**Not measurable yet — Kubernetes is not implemented in this revision.** There
is no `k8s/` directory and no HPA/VPA objects, so there are no real
`kubectl get hpa -w` numbers to report. Stating invented figures would be
dishonest. The design intent, from the brief's own explanation, is:

- **HPA lag (Q5):** the delay between offered load rising and replicas rising is
  the sum of the metrics-server sampling interval, the HPA control-loop interval
  (~15 s), and pod scheduling + container start (including the `readinessProbe`
  on `/ready`). The fix is a correct `resources.requests.cpu` (the HPA divides
  usage by the request — without it the HPA reads `<unknown>/60%`) and, on the
  behaviour block, `scaleUp.stabilizationWindowSeconds: 0`. This lag is exactly
  why autoscaling does not replace capacity planning: users wait during it.

- **VPA Off mode (Q6):** VPA runs with `updateMode: "Off"` so it *recommends*
  but never evicts. Running VPA in `Auto` alongside a CPU-based HPA makes the
  two controllers fight over the same signal: VPA raises the CPU request →
  computed utilisation falls → HPA scales in → per-pod load rises → VPA raises
  the request again. The result is oscillation. Recommender mode plus a human
  deciding the final request is the correct pairing.

When the `k8s/` tree is added these will be filled in with captured output.

## 7. `internal: true` blocks outbound traffic — where does the hosted-LLM call live?

In `compose.yaml` the `internal` network is declared with `internal: true`
(`compose.yaml:86`), so containers attached only to `internal` have no route to
the internet. The Groq/Gemini provider needs outbound HTTPS, so it cannot live
on a service that is `internal`-only.

The resolution is the network topology: **the backend joins both networks**
(`compose.yaml:58`, `networks: [edge, internal]`). It is the only service that
bridges `edge` (which has outbound access) and `internal` (Postgres + Redis).
`postgres` and `redis` are `internal`-only (`compose.yaml:12`, `24`) and
therefore cannot reach the internet, and the `frontend` is `edge`-only
(`compose.yaml:72`) so it cannot reach the database. The outbound LLM call is
made from the backend, which is the deliberately chosen bridge — the trade-off
the brief asks us to notice and document.

## 8. The failure that cost more than an hour

**Symptom.** The `frontend` container reported **`unhealthy`** in
`docker compose ps` even though the site loaded correctly in a browser. Because
the backend `depends_on` nothing on the frontend and vice-versa, the stack still
came up, so the failure was easy to ignore — until a later step (Kubernetes
probes, which reuse the same command) would have turned it into a restart loop.

**What I wrongly believed first.** That nginx was failing to start, or that the
page genuinely wasn't served — i.e. a real application fault. I was reading the
*status* ("unhealthy") as a verdict on the application rather than on the probe
itself.

**The command that revealed the truth.** Running the exact healthcheck command
by hand inside the container:

```
docker compose exec frontend sh -c "wget -qO- http://localhost/ ; echo exit=$?"
```

returned `wget: can't connect to remote host: Connection refused`, and the
container's health log showed the same line ninety times in a row:

```
docker inspect --format '{{json .State.Health}}' $(docker compose ps -q frontend)
```

That output is the key: nginx was *running*, yet the connection was refused.
Probing the IPv4 loopback directly succeeded:

```
docker compose exec frontend sh -c "wget -qO- http://127.0.0.1/ >/dev/null; echo $?"
```

and `/etc/hosts` explained why -- `getent hosts localhost` returned `::1`
(IPv6) first, then `127.0.0.1`:

```
::1             localhost
127.0.0.1       localhost
```

nginx was listening on IPv4 `0.0.0.0:80` only, so a probe to `localhost`
resolved to `::1`, where nothing was listening, and was refused. The tool
(`wget`) was present and fine -- my first belief (a missing binary) was wrong;
the fault was name resolution, not the probe utility.

**The fix.** Probe `127.0.0.1` explicitly instead of `localhost`, in
`frontend/Dockerfile` (the `HEALTHCHECK` line), `compose.yaml` (frontend
healthcheck) and `compose.prod.yaml` (frontend healthcheck). The lesson: a
failing probe is a statement about the probe and its environment, not
necessarily about the application -- and `localhost` inside a container is not
a synonym for "the port I bound". Every healthcheck here is now run by hand
once before its status is trusted.

---

## Required: index justification (two indexes, each by a named query)

Both indexes are declared in `backend/app/models.py:25` and created in
`backend/alembic/versions/0001_create_complaints.py:34-35`.

- **`ix_complaints_status_priority`** — serves the dashboard's
  `?status=&priority=` filter queries and the stats aggregation path, e.g.
  `ComplaintRepository.list_complaints` (`backend/app/repositories.py:44-46`)
  and the `GROUP BY category/priority` counts in `get_stats`
  (`repositories.py:64-66`). It lets Postgres satisfy the filter without a
  sequential scan as the table grows.

- **`ix_complaints_created_at`** — serves the `ORDER BY created_at DESC` in the
  paginated list query (`repositories.py:51`), which is the dashboard's default
  ordering. Without it, every page request sorts the whole table.

An unexplained index is cargo cult; these two are tied to concrete queries.

---

## Graceful shutdown decision (SIGTERM)

No custom `SIGTERM` handler is installed, and that is deliberate. Uvicorn
already implements the sequence the brief requires — stop accepting new
connections, let in-flight requests finish, then exit — when it receives
`SIGTERM`. Overriding it with a hand-rolled handler risks *skipping* the drain
(an earlier revision did exactly that and dropped live requests on shutdown).
The decision and reasoning are recorded in code at
`backend/app/main.py:71-76`, inside the `lifespan` context manager, so the
choice is stated rather than left ambiguous. Combined with a Kubernetes
`preStop` sleep + `terminationGracePeriodSeconds` (planned with the `k8s/`
tree), this is the defensible production configuration.