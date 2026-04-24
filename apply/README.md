# apply.cashrocketanaheim.com

Backend + frontend for the Cash Rocket Anaheim application funnel.
Fork of `cashinflash/cif-apply` main branch with:

- Frontend rebranded (navy + sunglow yellow, Cash Rocket Anaheim logo + copy).
- Backend hardcodes `source_site='cashrocket_anaheim'` on every `/submit`.
- Writes to the **same Firebase project** as cif-apply so all applications end
  up in the shared `app.cashinflash.com` dashboard, distinguishable by the
  Source Site column / filter.

## Shared vs. separate

| Component | Shared with cif-apply? | Notes |
|---|---|---|
| Code | No | Independent fork, its own Render service. Synced manually when cif-apply ships meaningful backend changes. |
| Firebase project | **Yes** | Same credentials → same DB. |
| Plaid app | **Yes** | Same `PLAID_CLIENT_ID` + `PLAID_SECRET`. |
| Anthropic API key | **Yes** | Same `ANTHROPIC_API_KEY`. |
| Domain | No | `apply.cashrocketanaheim.com` (independent of `apply.cashinflash.com`). |

## Deployment on Render

See the step-by-step in the marketing-site repo's README. Short version:

1. Create a new **Project** in Render called `Cash Rocket Anaheim`.
2. In that project, create a **Web Service** pointed at
   `cashinflash/CashRocketAnaheim` with **Root Directory** set to `apply`.
3. Copy env vars from your existing `cif-apply` service into the new service
   (use `.env.example` above as a checklist).
4. Deploy.
5. Add custom domain `apply.cashrocketanaheim.com` in Render's domain
   panel, point DNS at Render (Render will give you the exact CNAME), wait
   for SSL.

## Local run

```
pip install -r requirements.txt
export $(cat .env | xargs)   # populate your .env from .env.example first
python server.py
# → http://localhost:10000
```

## Keeping in sync with cif-apply

When you ship underwriting / decisioning fixes to `cif-apply`, mirror the
changes here:

- `server.py` (handlers outside the `/submit` tagging block)
- `decision_engine.py`
- `engine_v2/**`
- `tests/**`

The `/submit` tagging lines are Anaheim-specific and should NOT be
mirrored back into cif-apply.
