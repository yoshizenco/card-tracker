# Card-Tracker Backend (Cloudflare Worker)

Tiny worker that backs the shared profile state for the card tracker.

## What it does

Exposes two endpoints, both CORS-open and unauthenticated:

- `GET  /ping` — health check, returns `{ ok: true }`
- `GET  /state/{profile}` — returns the saved JSON state for a profile (or `{}` if none)
- `PUT  /state/{profile}` — overwrites the saved JSON state

Allowed profiles: **Rachel**, **Chris**, **Roy**. Anyone with the worker URL can read or write any of these three. There's no auth — this matches the "small trusted group" model the app is designed for.

## Free tier capacity

- Workers: 100 000 requests/day
- KV: 100 000 reads/day, 1 000 writes/day, 1 GB storage

Three users tracking cards burns well under 100 writes/day combined. The free tier is plenty.

## One-time deploy (≈3 minutes)

```bash
# 1. Install wrangler if you don't have it
npm install -g wrangler

# 2. Authenticate (opens a browser to Cloudflare's free signup/login)
wrangler login

# 3. Create the KV namespace and copy the printed `id` into wrangler.toml
cd worker
wrangler kv namespace create STATE
# Edit wrangler.toml and uncomment the [[kv_namespaces]] block, paste the id.

# 4. Deploy
wrangler deploy
```

Wrangler will print the worker URL (e.g. `https://card-tracker-state.<your-subdomain>.workers.dev`). **Send that URL to the dev** — it gets baked into the static site in one line.

## Local dev (optional)

```bash
wrangler dev
# Then in another shell:
curl http://127.0.0.1:8787/ping
curl http://127.0.0.1:8787/state/Rachel
curl -X PUT http://127.0.0.1:8787/state/Rachel -d '{"hello":"world"}' -H "Content-Type: application/json"
```
