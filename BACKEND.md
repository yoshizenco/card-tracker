# Backend choices

The app supports two cross-device sync backends. Pick one (or skip and run device-only).

## Option A — Cloudflare Worker (currently active)

What you already deployed yesterday. One-time setup of a free Worker + KV namespace via `wrangler`. Already working at `https://card-tracker-state.yoshi-0d5.workers.dev`. See `worker/README.md`.

**Pros:** Already set up. Endpoint URL is unguessable but unauthenticated. Blast radius if someone finds the URL: the 3 profiles' state.

**Cons:** Needs a Cloudflare account and a CLI install.

Config file: `backend-url.txt` — single line, the worker URL.

## Option B — GitHub Gist

Store the 3 profile JSONs as files inside a single gist. The app reads via `https://api.github.com/gists/{id}` (no auth needed) and writes with `PATCH` using a personal access token.

**Pros:** No CLI. No separate service. You already have a GitHub account. Data visible/editable directly via the GitHub web UI for debug.

**Cons:** The PAT must be embedded in the deployed JS. GitHub does not allow scoping a fine-grained PAT to a single gist — the minimum scope is **All Gists: Read and write**. If someone grabs that token from the deployed page source, they can read/modify every gist on your account, not just this one. Mitigation: create a **dedicated GitHub account** just for this token, or accept the risk for a small trusted group.

### One-time setup

1. **Create the gist:**
   - Visit https://gist.github.com → New gist
   - Description: `Card-tracker shared state`
   - Filename 1: `Rachel.json`, content: `{}`
   - Filename 2: `Chris.json`, content: `{}` (use "Add file")
   - Filename 3: `Roy.json`, content: `{}`
   - Click **Create secret gist** (or public — either works)
   - Copy the gist ID from the URL: `https://gist.github.com/yourname/<this-32-char-id>`

2. **Create a fine-grained PAT:**
   - Visit https://github.com/settings/personal-access-tokens/new
   - Token name: `card-tracker-gist`
   - Expiration: pick a long one (max 1 year)
   - Repository access: doesn't matter — you only need Gists
   - **Account permissions** → **Gists** → **Read and write**
   - Generate. Copy the token (starts with `github_pat_…`).

3. **Add the config:**
   - Create `gist-config.json` in this repo root with:
     ```json
     { "gist_id": "<paste-id>", "pat": "github_pat_..." }
     ```
   - `gist-config.json` is in `.gitignore` so the PAT does NOT get committed (it gets baked into index.html at build time and pushed there).
   - **However:** because index.html is committed and served publicly, the PAT *is* effectively public. See cons above.

4. **Build and push:**
   ```bash
   python3 build.py        # picks up gist-config.json automatically
   git add -A && git commit -m "switch to gist backend" && git push
   ```

5. **(Optional) migrate existing Cloudflare data:**
   - Pull each profile's state from the worker:
     ```bash
     curl -A "Mozilla/5.0" https://card-tracker-state.yoshi-0d5.workers.dev/state/Rachel > Rachel.json
     curl -A "Mozilla/5.0" https://card-tracker-state.yoshi-0d5.workers.dev/state/Chris > Chris.json
     curl -A "Mozilla/5.0" https://card-tracker-state.yoshi-0d5.workers.dev/state/Roy > Roy.json
     ```
   - Edit your gist via the web UI, replace each file's `{}` with the contents.

The page picks the gist adapter automatically when `gist-config.json` exists. Otherwise it falls back to the Cloudflare worker (via `backend-url.txt`).

## Switching back

Delete `gist-config.json`, run `python3 build.py`, commit and push. The app reverts to the Cloudflare worker. (Data is not auto-migrated; keep both backends populated during the cutover if you want a safety net.)
