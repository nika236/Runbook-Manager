# Project Context — Settled at Generation Time

This file is the **authoritative record** of the choices made when this project was generated. Treat every value below as a fact about the project, not a preference to be re-litigated.

**You MUST NOT** ask the user to confirm, expand, or re-choose any of these. If a feature genuinely cannot be served by the wired connections or tech stack, say so explicitly and stop — do not improvise an alternative.

## Project

- **Name:** Runbook Manager
- **Tool:** Cursor
- **Environment:** Windows

## Tech Stack

- Python 3.12 (Flask + Gunicorn)
- React 18 (Vite + Tailwind CSS)
- Security level: credentials

## Security Posture

- credentials

## Connections (Data Sources)

_No external connections were selected. The project is self-contained — do not propose adding third-party data sources unless the user explicitly asks._

## Where the Detailed Rules Live

- Always-applied rules: `.cursor/rules/*.mdc`
- On-demand deep guidance per connection: `.cursor/skills/<connection>/SKILL.md`
- Project constitution / principles: `.specify/memory/constitution.md`
- Infra contract: `infra-manifest.json`

When a connection-specific question comes up, **load the matching skill before writing code**.
