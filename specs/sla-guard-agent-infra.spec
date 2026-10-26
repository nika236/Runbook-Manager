# Incident AI SLA Guard Agent — Infrastructure Spec

## Overview

Fully automated job: monitors NOC Action Items in Jira, tracks SLA ETA, and
proactively sends Microsoft Teams Adaptive Cards to the ticket owner — no
human in the loop once deployed. This document covers *where it runs* and
*what it needs*, not the SLA/notification business logic (already defined
in the two agent prompts this spec was derived from).

---

## Phase 1: Placement

- [ ] Built as a separate **Azure Container App Job** (cron-triggered), not
      bundled into the existing `runbook-manager` web Container App
      - Reason: the web app can scale to multiple replicas with no leader
        election; an in-process scheduler risks duplicate card sends.
        A Job guarantees single execution per trigger.
- [ ] Same image as the web app, different entrypoint/command:
      `python -m app.sla_guard.run` (not `gunicorn`)
- [ ] Schedule: cron trigger, run **daily** at a fixed time (confirm time
      with NOC — must be well before the 2-day warning window matters)
- [ ] Manual trigger supported for testing: `az containerapp job start`
      and/or a local `--dry-run` flag that logs intended sends without
      calling the Teams API

---

## Phase 2: Code layout

```
app/sla_guard/
  jira_client.py     # fetch Action Items, read/write SLA + tracking fields
  teams_client.py     # Graph app-only auth, resolve owner -> AAD user, send card
  sla_engine.py       # warning/breach decision logic, "at most once" enforcement
  run.py               # Container App Job entrypoint
```

- [ ] No changes to `app/api/*` required for the job itself; optionally add
      `POST /api/sla-guard/run?dry_run=true` behind existing auth for
      manual testing from the web app during rollout

---

## Phase 3: Required secrets (Key Vault)

All as Key Vault secret references on the Container App Job — never
plaintext env vars, per existing `infra-manifest.json` convention.

### Jira
- [ ] `JIRA_BASE_URL`
- [ ] `JIRA_EMAIL`
- [ ] `JIRA_API_TOKEN` (scoped separately from `CONFLUENCE_API_TOKEN` even
      if same Atlassian account, for independent rotation/revocation)
- [ ] `JIRA_NOC_PROJECT_KEY`
- [ ] `JIRA_NOCOPS_PROJECT_KEY`

### Microsoft Teams / Graph (app-only, proactive messaging)
- [ ] `GRAPH_TENANT_ID`
- [ ] `GRAPH_CLIENT_ID`
- [ ] `GRAPH_CLIENT_SECRET`
- [ ] Confirm app registration already has (or request) application
      permissions: `Chat.Create`, `ChatMessage.Send`, `User.Read.All`
      (for resolving assignee email -> AAD object ID)

### infra-manifest.json
- [ ] Add a `scheduledJob` resource entry documenting the new Container
      App Job and its reason, matching the existing `keyvault` entry style

---

## Phase 4: Pre-build verification (must happen before any code/notification logic)

Carried over from the setup-agent prompt — do not skip:

- [ ] Pull one real NOC Action Item via Jira API; confirm field IDs for
      SLA ETA Date, SLA ETA Sprint, assignee, reporter, and the
      "relates to" link target resolve as expected
- [ ] Confirm whether an existing Jira field/label already tracks
      "warning sent" / "breach sent" state; if none exists, propose one
      and get explicit confirmation before creating it
- [ ] Confirm the Graph app registration can send a 1:1 chat message to
      an arbitrary user it has no prior conversation with (app-only
      `POST /chats` + `POST /chats/{id}/messages`), and that Jira
      assignee email reliably matches the user's Azure AD UPN
- [ ] Confirm calendar-day vs business-day SLA countdown
- [ ] Confirm escalation target when no assignee (falls back to Reporter
      per spec — confirm this is still correct)

---

## Phase 5: Observability & safety

- [ ] Job logs to stdout, captured by the existing Log Analytics workspace
- [ ] Every run logs: tickets evaluated, cards sent (ticket key, recipient,
      card type), and tickets skipped with reason
- [ ] First production run should be `--dry-run` for at least one full
      cycle before enabling real sends
- [ ] Alert path if the job fails to run (Container App Job failure ->
      existing Log Analytics / alerting, not a new system)

---

## Sign-off

| Item | Status |
|------|--------|
| Jira field IDs confirmed via API | [ ] |
| Tracking field/label confirmed or created | [ ] |
| Graph app-only proactive messaging confirmed | [ ] |
| Dry-run completed, reviewed | [ ] |
| Production enabled | [ ] |
