# CivicPulse Operations Runbook

## Deploy

CI deploys `main` to an ephemeral validation cluster and publishes both images
under the immutable commit SHA. For a local cluster, install an ingress
controller and the metrics-server, then run:

```bash
kubectl apply -k k8s/overlays/prod
kubectl rollout status deployment/backend -n civicpulse
kubectl rollout status deployment/frontend -n civicpulse
```

Replace the placeholder Secret before exposing the service. Never commit the
replacement manifest.

## Roll Back

For an urgent rollback, use the recorded Deployment revision:

```bash
kubectl rollout undo deployment/backend -n civicpulse
kubectl rollout status deployment/backend -n civicpulse
```

For an auditable rollback, check out the previous commit, set both production
images to that SHA with `kustomize edit set image`, and apply the overlay again.

## Logs and Health

```bash
kubectl logs -n civicpulse deployment/backend --all-containers --prefix
kubectl get pods -n civicpulse
kubectl get hpa,vpa,pdb -n civicpulse
```

`/health` is liveness-only. `/ready` checks PostgreSQL and Redis and is the
endpoint to investigate when the backend is removed from the Service.

## Triage Failures

The backend falls back to `rules:fallback` when the hosted provider times out,
returns a retryable error, or produces invalid structured output. Inspect the
JSON logs and `/api/meta/providers` first. If failures persist, switch
`TRIAGE_PROVIDER` to `simulated` or `rules` in the ConfigMap, apply the overlay,
and roll out the backend before investigating provider credentials and quotas.
