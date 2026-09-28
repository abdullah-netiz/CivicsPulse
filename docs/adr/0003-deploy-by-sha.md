# ADR 0003: Deploy by Immutable Commit SHA, Never `:latest`

## Status

Accepted.

## Context

Both container images are published to a registry (GHCR). A tag is a mutable
pointer: `:latest` can be reassigned to a different image at any time, and two
pods started minutes apart can silently run different code while reporting the
same version. When something breaks in production, "what is deployed?" must
have an answer that does not depend on when the question is asked.

The assignment's non-negotiables (§3.4) require deploy by immutable reference:
"`:latest` may be pushed; it may never be deployed."

## Decision

`compose.prod.yaml` references images by an immutable tag supplied through
`IMAGE_TAG`, which carries the git commit SHA:

```
image: ${REGISTRY}/civicpulse-backend:${IMAGE_TAG:?IMAGE_TAG must be set (use the git commit SHA)}
```

`IMAGE_TAG` is required (the `:?` form fails the deploy if it is unset, so a
bare `:latest` can never sneak in). The pipeline tags every push with
`${github.sha}` in addition to `latest`, and deployment always uses the SHA.
The same rule is intended for the Kubernetes overlay (`kustomize edit set
image ... :${SHA}`).

## Consequences

- **Reproducibility:** the exact running artefact is identified by a value that
  maps one-to-one to a commit; rebuilding the same SHA yields the same source.
- **One-command truth:** `docker compose -f compose.prod.yaml images` (or, on
  Kubernetes, `kubectl get deploy -o jsonpath='{..image}'`) answers "what is in
  production" and the SHA can be pasted straight into `git show`.
- **Safe rollback:** rollback is re-applying the previous overlay/SHA
  (declarative, auditable) — or `kubectl rollout undo` for the fast 3 a.m. fix.
- **No untested code:** because deployment is pinned to a SHA that already
  passed CI, `:latest` drifting ahead cannot reach production by accident.
- **Cost:** one extra variable (`IMAGE_TAG`) to supply, and `:latest` is
  retained only for human convenience, never as a deploy target.