# Azure Container Apps Deployment Checklist

## Overview

This checklist ensures every application meets ITOPS-Architect hosting standards before it is deployed to Azure Container Apps. Complete every section before requesting a production deployment.

---

## Phase 1: Repository Readiness

### Dockerfile

- [ ] `Dockerfile` exists at the repository root
- [ ] Uses a **multi-stage build** (separate `builder` and `runner` stages)
- [ ] Base image is a pinned LTS version (`node:20-alpine`, not `latest`)
- [ ] Production stage runs as a **non-root user** (e.g. `nextjs` / `nodejs`)
- [ ] `EXPOSE 3000` is declared and app binds to `0.0.0.0`
- [ ] For Next.js: `next.config.js` sets `output: "standalone"`
- [ ] Build succeeds locally: `docker build -t smoke-test . && docker image rm smoke-test`

### .dockerignore

- [ ] `.dockerignore` exists at the repository root
- [ ] Excludes: `node_modules`, `.next`, `.env`, `.env.*`, `*.env`, `.git`, `dist`, `coverage`
- [ ] No secrets or credentials are included in the image context

### Health Endpoint

- [ ] `/api/health` (or `/health`) GET endpoint returns HTTP 200 with `{ "status": "ok" }`
- [ ] Endpoint has no authentication requirement (probes must reach it without a token)
- [ ] Validated locally: `curl -s http://localhost:3000/api/health`

### Secret Hygiene

- [ ] No secrets, connection strings, or passwords appear in `Dockerfile` `ENV` or `ARG` instructions
- [ ] No `.env` files committed to the repository
- [ ] `git log --all -- '*.env'` shows no accidentally committed env files

---

## Phase 2: Azure Infrastructure Provisioning

### Azure Container Registry (ACR)

- [ ] ACR instance exists and is accessible
- [ ] The Container App's **managed identity** has `AcrPull` role on the ACR
- [ ] Image naming convention agreed: `<acr>.azurecr.io/<app-name>:<git-sha>`

### Container Apps Environment

- [ ] Container Apps Environment exists in the correct resource group and region
- [ ] Environment is connected to the appropriate VNet / subnet (if required)
- [ ] Log Analytics workspace is attached for diagnostics

### Container App Configuration

- [ ] Container App created with **system-assigned managed identity** enabled
- [ ] Ingress set to **External**, target port `3000`
- [ ] Revision mode: `Single` (or `Multiple` with traffic weights for blue/green)
- [ ] Min replicas: `1` (production) — not `0` to avoid cold starts
- [ ] Max replicas: agreed with ITOPS (default `10`)
- [ ] CPU: `0.5` cores minimum; Memory: `1Gi` minimum
- [ ] Readiness probe: `GET /api/health`, period 10s, failure threshold 3
- [ ] Liveness probe: `GET /api/health`, period 30s, failure threshold 5

### Key Vault & Secrets

- [ ] Key Vault exists and contains all required secrets (e.g. `database-url`, `nextauth-secret`)
- [ ] Container App's managed identity has `Key Vault Secrets User` role on the Key Vault
- [ ] All secrets are configured as **Key Vault secret references** on the Container App (not plaintext env vars)
- [ ] Plaintext env vars confirmed to contain only non-sensitive config (`NODE_ENV`, `PORT`, `NEXTAUTH_URL`, `AZURE_KV_URL`)

---

## Phase 3: Pre-Deployment Build Validation

- [ ] Run `npm run build` locally — zero errors
- [ ] Run `npm run lint` — zero new errors
- [ ] Run `npx tsc --noEmit` — zero type errors (for TypeScript projects)
- [ ] Build and run the Docker image locally, verify the app starts:
  ```bash
  docker run --rm -p 3000:3000 \
    -e NODE_ENV=production \
    -e DATABASE_URL="<dummy>" \
    <acr>/<app>:<git-sha>
  curl -s http://localhost:3000/api/health
  ```
- [ ] No secrets appear in `docker history <image>` or `docker inspect <image>` output

---

## Phase 4: Deployment

- [ ] Image built via `az acr build` using the git SHA as the tag
- [ ] Container App updated: `az containerapp update --image <acr>/<app>:<git-sha>`
- [ ] New revision reaches `healthState: Healthy` within 5 minutes
- [ ] All replicas are running (check `az containerapp revision list`)

---

## Phase 5: Post-Deployment Validation

- [ ] Health endpoint reachable and returns 200:
  ```bash
  curl -sf https://<app-fqdn>/api/health
  ```
- [ ] Application loads correctly in browser (login flow, main pages)
- [ ] No errors in Container Apps system logs:
  ```bash
  az containerapp logs show --name <app> --resource-group <rg> --type system --tail 50
  ```
- [ ] Database connectivity confirmed (relevant pages load without DB errors)
- [ ] Auth flow works end-to-end (login, session, protected routes)

---

## Phase 6: Rollback Readiness

- [ ] Previous image tag (git SHA) is still available in ACR
- [ ] Rollback procedure has been tested or reviewed with the team:
  ```bash
  az containerapp revision activate --name <app> --resource-group <rg> --revision <prev-revision>
  ```
- [ ] At least 3 recent image tags retained in ACR (for rollback coverage)

---

## Sign-Off

| Role | Name | Date | Status |
|------|------|------|--------|
| Developer | | | [ ] Approved |
| ITOPS-Architect | | | [ ] Approved |
| Security Review | | | [ ] Approved (if PII/credentials involved) |
