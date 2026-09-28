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
- `hpa-watch.txt` — captured `kubectl get hpa -w` output during a load test.
- `replicas-vs-load.png` — chart of replicas against offered load.
- `vpa-recommendations.txt` — `kubectl describe vpa backend-vpa` output.

### Part I — CI/CD
- `ci-red-blocked-merge.png` — a failing check blocking the merge button.
- `ci-green.png` — the same PR once fixed, all checks green.

<!-- Files are added as each item is completed. Do not commit secrets or real API keys. -->