# Local Development and Migrations Spec

## Objective

Ensure every AI-generated project can run locally without Azure resources and automatically applies database schema migrations on first production startup.

Local development must use lightweight substitutes (SQLite, in-memory fallbacks) so that non-technical users can develop without provisioning cloud infrastructure. Production deployments must apply migrations before the app starts serving traffic.

---

## Functional Requirements

### 1. Environment Variable Contract

- [ ] Application code reads all configuration from environment variables only
- [ ] Application code does not import `@azure/keyvault-secrets`, `SecretClient`, or any Azure Key Vault SDK
- [ ] Application code does not call any Azure SDK to fetch secrets at runtime
- [ ] `DATABASE_URL`, `REDIS_URL`, and `AZURE_KV_URL` are the only infrastructure-related env var names used
- [ ] No credentials, connection strings, or secret values are hardcoded in source code

### 2. Environment File Management

- [ ] `.env.example` exists at the repository root
- [ ] `.env.example` documents every environment variable the app reads
- [ ] `.env.example` contains placeholder values and comments — no real secrets
- [ ] `.env.example` includes `DATABASE_URL`, `DB_PROVIDER`, and comments explaining local vs production values
- [ ] `.env.example` includes `REDIS_URL` with a comment that it can be left empty locally
- [ ] `.env.example` includes `AZURE_KV_URL` with a comment that it is not needed locally
- [ ] `.env.example` is committed to the repository
- [ ] `.env.example` is updated in the same change when env vars are added, renamed, or removed
- [ ] `.gitignore` excludes `.env`, `.env.local`, `.env*.local`, and `*.env`
- [ ] `.gitignore` excludes local database files (`dev.db`, `dev.db-journal`)
- [ ] No `.env.local` or file containing real secrets is committed to the repository

### 3. Local Database

- [ ] When `db` is enabled in `infra-manifest.json`, the app uses SQLite for local development
- [ ] The Prisma schema uses `provider = "sqlite"` — the entrypoint swaps it for production
- [ ] The Prisma schema does **not** use `provider = env("DB_PROVIDER")` — Prisma does not support `env()` for the provider field
- [ ] The connection string is always read from `DATABASE_URL` via `env("DATABASE_URL")`
- [ ] The local database can be initialized with a single command (e.g. `npx prisma db push`)
- [ ] No migration files are required — `entrypoint.sh` uses `prisma db push` to apply the schema declaratively
- [ ] Schema types are compatible with both SQLite and SQL Server
- [ ] Primary keys use `String @id @default(cuid())` or equivalent portable strategy
- [ ] The app starts and functions correctly with a local SQLite database
- [ ] No `dev.db`, `*.db`, or `*.db-journal` files are committed to the repository

### 4. Local Redis

- [ ] When `redis` is enabled in `infra-manifest.json`, the app starts without Redis available
- [ ] The app checks whether `REDIS_URL` is set before initializing a Redis client
- [ ] If `REDIS_URL` is not set, Redis-dependent features are skipped gracefully
- [ ] The app does not crash or throw unhandled exceptions when Redis is unavailable
- [ ] No mock Redis libraries are added as production dependencies
- [ ] A clear log warning is emitted when Redis is unavailable and features are degraded

### 5. Database Schema Application — `entrypoint.sh`

- [ ] When `db` is enabled in `infra-manifest.json`, `entrypoint.sh` exists at the repository root
- [ ] `entrypoint.sh` swaps the Prisma provider from `sqlite` to `sqlserver` when `DB_PROVIDER=sqlserver` is set
- [ ] `entrypoint.sh` runs `npx prisma db push --accept-data-loss --skip-generate` to apply the schema
- [ ] `entrypoint.sh` uses `set -e` to fail fast on errors
- [ ] `entrypoint.sh` ends with `exec` to replace the shell process with the app process
- [ ] The schema push is idempotent (safe to run on every deployment)
- [ ] When `db` is not enabled, `entrypoint.sh` does not exist and the Dockerfile uses the standard `CMD`

### 6. Dockerfile Integration

- [ ] When `db` is enabled, the Dockerfile `CMD` is `["./entrypoint.sh"]` instead of the direct start command
- [ ] `entrypoint.sh` is copied into the runner stage of the Dockerfile
- [ ] `entrypoint.sh` is made executable with `chmod +x`
- [ ] `entrypoint.sh` runs as the non-root user — not as root
- [ ] When `db` is not enabled, the Dockerfile uses the standard `CMD` from the Azure Container Apps Standards rule

### 7. README Local Development Section

- [ ] `README.md` contains a "Local Development" section
- [ ] The section lists prerequisites (runtime version, Git)
- [ ] The section explains how to copy `.env.example` to `.env.local`
- [ ] The section explains how to install dependencies
- [ ] The section explains how to initialize the local database (when applicable)
- [ ] The section explains how to start the app
- [ ] The section states that the production database schema is applied automatically on first deploy
- [ ] The section states that `DATABASE_URL`, `REDIS_URL`, and `AZURE_KV_URL` are set automatically by the platform on deploy
- [ ] The section explicitly says Azure access is not needed for local development
- [ ] The instructions are written for non-technical users

---

## Validation Conditions

- [ ] The app starts locally with only `.env.local` values (no Azure resources)
- [ ] The app connects to a local SQLite database and serves requests correctly
- [ ] The app starts without Redis and all non-Redis features work
- [ ] The Prisma schema uses `provider = "sqlite"` and `url = env("DATABASE_URL")`
- [ ] After first deploy, `entrypoint.sh` swaps the provider and applies the schema automatically
- [ ] On subsequent deploys, `entrypoint.sh` re-applies the schema idempotently (no-op if unchanged)
- [ ] No secrets, connection strings, or database files appear in committed files
