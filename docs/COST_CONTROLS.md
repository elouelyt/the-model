# Cost Controls — Tennis AI Data Platform

## Philosophy
This is a portfolio project. Target monthly spend is near $0. Two threat vectors are guarded against:
1. **Runaway errors** — a bug causing repeated expensive API calls or Cloud Run loops
2. **Traffic attacks** — someone hammering the public API Gateway endpoint

---

## Budget Alert

**Billing account:** `0182BF-B75C4D-52B4C3`
**Budget name:** `$10,000 Monthly Budget Alert`
**Budget ID:** `48d1ccfa-9124-4b9e-bb39-40b16e120043`
**Amount:** 10,000 COP/month (~$2.50 USD) — intentionally strict
**Scope:** Project `tennis-data-487809` only
**Reset:** Monthly (calendar period)

### Thresholds

| Threshold | What it means |
|---|---|
| **50%** (~5,000 COP) | Early warning — something unusual is happening |
| **90%** (~9,000 COP) | Near limit — investigate immediately |
| **100%** (~10,000 COP) | Budget exceeded — act now |
| **150%** (~15,000 COP) | Significantly over — escalate, consider disabling services |

All thresholds use `CURRENT_SPEND` basis (actual spend, not forecasted).

### Notification
Alerts fire to `mateo@grisalogic.com` via Cloud Monitoring notification channel:
`projects/tennis-data-487809/notificationChannels/14755856984491073698`

---

## Cloud Run — Max Instances Cap

**Service:** `tennis-api` (`us-central1`)
**Max instances:** `3`

Prevents unbounded horizontal scaling under a traffic attack. At portfolio traffic levels, 1 instance handles all load. The cap of 3 gives headroom for legitimate bursts while limiting blast radius from attacks.

To verify:
```bash
gcloud run services describe tennis-api --region=us-central1 --format="value(spec.template.metadata.annotations)"
```

To update:
```bash
gcloud run services update tennis-api --region=us-central1 --max-instances=N
```

---

## Architecture-Level Cost Controls

These are structural decisions that keep costs low regardless of alerts:

| Control | Detail |
|---|---|
| **Cloud Run scales to zero** | No traffic = no running containers = no cost |
| **API Gateway as front door** | Rejects unauthenticated requests before they hit Cloud Run compute |
| **No Compute Engine VMs** | No instances running 24/7 |
| **BigQuery free tier** | Dataset is well within 10GB storage / 1TB query free tier |
| **GCS minimal storage** | Only raw JSON files, negligible storage cost |

---

## How to Restore These Settings on a New Machine

```bash
# 1. Enable the Billing Budget API
gcloud services enable billingbudgets.googleapis.com --project=tennis-data-487809

# 2. Recreate email notification channel
gcloud beta monitoring channels create \
  --channel-content='{"type":"email","displayName":"Mateo Cost Alerts","labels":{"email_address":"mateo@grisalogic.com"}}' \
  --project=tennis-data-487809

# 3. Update budget (replace CHANNEL_ID with output from step 2)
gcloud billing budgets update billingAccounts/0182BF-B75C4D-52B4C3/budgets/48d1ccfa-9124-4b9e-bb39-40b16e120043 \
  --billing-account=0182BF-B75C4D-52B4C3 \
  --filter-projects=projects/tennis-data-487809 \
  --add-threshold-rule=percent=0.5,basis=current-spend \
  --add-threshold-rule=percent=0.9,basis=current-spend \
  --add-threshold-rule=percent=1.0,basis=current-spend \
  --add-threshold-rule=percent=1.5,basis=current-spend \
  --notifications-rule-monitoring-notification-channels=projects/tennis-data-487809/notificationChannels/CHANNEL_ID

# 4. Cap Cloud Run max instances
gcloud run services update tennis-api --region=us-central1 --max-instances=3
```

---

## Planned: Weekly Cost Review Agent (Story 5)
A scheduled Claude Code agent will run weekly to check current spend vs budget,
Cloud Run request counts, error rates, and active instances — flagging anomalies
with specific `gcloud` remediation commands.

---

## Future: Automated Cost Kill Switch

**Pattern:** Budget alert → Pub/Sub topic → Cloud Function → `gcloud run services update tennis-api --max-instances=0`

When a spend threshold is crossed, the Cloud Function automatically sets Cloud Run max instances to 0 — killing all traffic until manually re-enabled.

**Why not implemented yet:**
- Budget data has up to 1 hour lag — not instant protection
- Kills legitimate users too — requires manual re-enable after investigation
- Current protections are sufficient for portfolio traffic:
  - `X-API-Key` auth blocks unauthenticated requests
  - 3 max instances caps blast radius
  - Email alerts reach billing admin fast enough to act manually

**When to implement:** When the app has real users and real revenue at risk.
