# Evidence

Screenshots and transcripts that back the collaboration, CI/CD and Kubernetes
claims in the README and the assignment rubric. Store binary screenshots as
`.png` and paste terminal output into Markdown files alongside them.

## Expected contents

### Part A — Collaboration and version control
- `branch-protection.png` — GitHub branch protection rule on `main`
  (require PR, 1 approval, required status checks).
- `direct-push-blocked.png` — (optional) proof a direct push to `main` is rejected.
- `pr-review-examples.png` — merged PRs showing linked Issues and a substantive
  review comment from the other partner.
- `git-shortlog.png` — `git shortlog -sne` showing both partners' contribution split.
- `merge-conflict.md` — the deliberate merge conflict on real code: markers,
  resolution, merge commit hash, and 2-4 sentences on why the resolution won.

### Part H — Kubernetes / autoscaling
- `k8s-autoscaling.txt` — **captured.** `kubectl get pods/svc/hpa/vpa` plus
  `kubectl top pods/nodes` on the live `kind` cluster (`kind-civicpulse`,
  namespace `civicpulse`). Shows the HPA reading `cpu: 10%/60%` from
  metrics-server, the VPA reporting `PROVIDED=True`, and per-pod CPU/memory.
  Regenerate with `scripts/capture_evidence.ps1`.
- `vpa-recommendations.txt` — **captured.** `kubectl describe vpa backend-vpa`
  showing `RecommendationProvided=True` with target `cpu: 143m / memory: 250Mi`
  and the lower/upper confidence bounds. Mode is `Off` (recommendation-only),
  so the VPA admission webhook is intentionally scaled to 0 — see ADRs.
- `hpa-watch.txt` — captured `kubectl get hpa -w` output during a load test.
- `replicas-vs-load.png` — chart of replicas against offered load.

### Docker Compose functional demo
- `compose-functional.txt` — **captured.** `/health`, `/ready`, `/metrics`
  through the frontend origin (proves the nginx proxy), plus two consecutive
  `/api/stats` calls showing the Redis cache go `MISS` → `HIT`.

### Part I — CI/CD
- `ci-red-blocked-merge.png` — a failing check blocking the merge button.
- `ci-green.png` — the same PR once fixed, all checks green.

<!-- Files are added as each item is completed. Do not commit secrets or real API keys. -->