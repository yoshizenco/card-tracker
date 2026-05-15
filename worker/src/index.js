// Card-tracker shared backend.
// Tiny worker that proxies a KV store, exposing public GET/PUT for each profile.
// No auth — security model is "anyone with the URL can read/write any of the 3 profiles."
// Three profiles are whitelisted: Rachel, Chris, Roy.

const ALLOWED_PROFILES = ["Rachel", "Chris", "Roy"];

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, PUT, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Max-Age": "86400",
};

function json(data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS, ...extra },
  });
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: CORS_HEADERS });
    }

    const url = new URL(request.url);
    const parts = url.pathname.split("/").filter(Boolean);

    // Health check
    if (parts[0] === "ping") {
      return json({ ok: true, ts: Date.now() });
    }

    // /state/<profile>
    if (parts[0] === "state" && parts[1]) {
      const profile = decodeURIComponent(parts[1]);
      if (!ALLOWED_PROFILES.includes(profile)) {
        return json({ error: "Unknown profile" }, 404);
      }

      const key = `state:${profile}`;

      if (request.method === "GET") {
        const data = await env.STATE.get(key, { type: "json" });
        if (data == null) return json({}, 200);
        return json(data, 200);
      }

      if (request.method === "PUT") {
        let body;
        try { body = await request.json(); }
        catch { return json({ error: "Invalid JSON" }, 400); }
        // Size sanity check: 1 MB is plenty for any reasonable collection.
        const serialized = JSON.stringify(body);
        if (serialized.length > 1_000_000) {
          return json({ error: "Payload too large" }, 413);
        }
        await env.STATE.put(key, serialized);
        return json({ ok: true, savedAt: Date.now() });
      }

      return json({ error: "Method not allowed" }, 405);
    }

    return json({ error: "Not found", routes: ["/ping", "/state/{profile}"] }, 404);
  },
};
