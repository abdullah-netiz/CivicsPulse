# ADR 0002: Frontend Runtime Configuration via nginx `/api` Proxy

## Status

Accepted.

## Context

The frontend is a React 18 + Vite + TypeScript single-page app built by Node
and served by nginx:alpine from a multi-stage image. Vite resolves
`import.meta.env.VITE_*` values **at build time** and inlines them as literals
into the emitted JavaScript bundle. If the backend URL were supplied that way,
the built `dist/` would embed one specific API host.

That has two bad consequences:

1. The image becomes environment-specific. Promoting the same artefact from
   staging to production would require a rebuild, destroying
   build-once-deploy-many.
2. It forces the browser to call an absolute backend origin, which reopens
   cross-origin concerns and an origin that is "not localhost" (a stated goal
   of the assignment's frontend piece).

## Decision

The frontend never knows the backend's address. `frontend/src/api.ts` issues
relative requests to `/api/...`, and `frontend/nginx.conf` proxies them:

```
location /api/ { proxy_pass http://backend:8000/api/; ... }
```

The service name `backend` is resolved by Docker's embedded DNS at request
time, not baked into JavaScript at build time. The same built image therefore
runs unchanged behind `localhost:8080`, a Compose network, or a Kubernetes
Ingress.

## Consequences

- **Positive:** one image runs in every environment; the browser only ever
  talks to its own origin, so no CORS preflight is needed for the `/api` path
  and no backend URL leaks into public JavaScript; configuration lives in
  nginx and Compose/Kubernetes, which is where operators already look.
- **Negative:** the frontend is coupled to nginx as its ingress path — a
  different web server must reproduce the `/api` proxy rule. Ops must be aware
  that the API is reached through the frontend origin, not directly.
- **Alternative considered:** generating `/config.js` at container start from
  environment variables. Rejected as unnecessary here because the proxy already
  satisfies build-once-deploy-many with fewer moving parts; it remains a valid
  option if the API must ever be called cross-origin from the browser.