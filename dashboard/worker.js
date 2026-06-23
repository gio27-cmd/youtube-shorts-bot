/**
 * Dashboard Worker — READ ONLY.
 *
 * Liest dieselbe Cloudflare-KV-Namespace wie der Bot (Binding "KV") und die
 * GitHub-Actions-API. Schreibt NICHTS. Der Bot-Code wird nicht angefasst.
 *
 * Routen:
 *   GET  /            → App (oder Login, wenn kein gültiges Cookie)
 *   POST /auth        → PIN prüfen, Session-Cookie setzen
 *   GET  /logout      → Cookie löschen
 *   GET  /api/state   → aggregiertes JSON (KV + GitHub), gecached
 *
 * Auth: 4-stelliges PIN (env.DASHBOARD_PIN, Default 0369) wird SERVERSEITIG
 * geprüft. Das PIN steht nie im ausgelieferten HTML/JS.
 */

import HTML from "./index.html";
import icon180 from "./icon-180.png";
import icon192 from "./icon-192.png";
import icon512 from "./icon-512.png";
import iconMask from "./icon-maskable-512.png";

const MANIFEST = JSON.stringify({
  name: "Animal Shorts",
  short_name: "Shorts",
  start_url: "/",
  display: "standalone",
  background_color: "#0e1014",
  theme_color: "#0e1014",
  icons: [
    { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
    { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
    { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
  ],
});

const ICONS = {
  "/icon-180.png": icon180,
  "/icon-192.png": icon192,
  "/icon-512.png": icon512,
  "/icon-maskable-512.png": iconMask,
};

const COOKIE = "sbsess";
const KV_TTL_MS = 120000; // KV-Aggregation max. alle 120s neu lesen (schont Free Tier)
const GH_TTL_MS = 30000;  // GitHub-Runs alle 30s

// Persistiert innerhalb eines Worker-Isolates über Requests hinweg.
let cache = { kv: null, kvAt: 0, gh: null, ghAt: 0 };

export default {
  async fetch(req, env) {
    const url = new URL(req.url);

    // Öffentlich (auch ohne Login): App-Icon + PWA-Manifest, sonst kann iOS
    // beim "Zum Home-Bildschirm" das Icon nicht laden.
    if (url.pathname === "/manifest.webmanifest") {
      return new Response(MANIFEST, {
        headers: { "content-type": "application/manifest+json; charset=utf-8", "cache-control": "public, max-age=3600" },
      });
    }
    if (ICONS[url.pathname]) {
      return new Response(ICONS[url.pathname], {
        headers: { "content-type": "image/png", "cache-control": "public, max-age=86400" },
      });
    }

    const pin = (env.DASHBOARD_PIN || "0369").toString();
    const secret = env.AUTH_SECRET || "sb-" + pin + "-dashboard";

    if (url.pathname === "/auth" && req.method === "POST") {
      const form = await req.formData();
      const got = (form.get("pin") || "").toString().trim();
      if (got === pin) {
        const token = await sign({ exp: Date.now() + 7 * 864e5 }, secret);
        return new Response(null, {
          status: 302,
          headers: {
            "Location": "/",
            "Set-Cookie": `${COOKIE}=${token}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=${7 * 86400}`,
          },
        });
      }
      return html(loginPage(true), 401);
    }

    if (url.pathname === "/logout") {
      return new Response(null, {
        status: 302,
        headers: {
          "Location": "/",
          "Set-Cookie": `${COOKIE}=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0`,
        },
      });
    }

    const authed = await verify(cookieVal(req, COOKIE), secret);

    if (!authed) {
      if (url.pathname.startsWith("/api/")) return json({ error: "unauthorized" }, 401);
      return html(loginPage(false), 200);
    }

    if (url.pathname === "/api/state") {
      const state = await buildState(env);
      return json(state, 200, { "cache-control": "no-store" });
    }

    return html(HTML, 200);
  },
};

// ---------------------------------------------------------------- state

async function buildState(env) {
  const kv = await getKv(env);
  const gh = await getGh(env);

  const events = buildEvents(kv, gh.runs);
  const running = gh.runs.find((r) => r.status === "in_progress" || r.status === "queued") || null;

  return {
    ...kv,
    runs: gh.runs,
    events,
    now: {
      running: running
        ? {
            event: running.event,
            status: running.status,
            started_at: running.run_started_at || running.created_at,
            url: running.html_url,
          }
        : null,
      ghConfigured: gh.configured,
    },
    generatedAt: new Date().toISOString(),
  };
}

async function getKv(env) {
  if (cache.kv && Date.now() - cache.kvAt < KV_TTL_MS) return cache.kv;

  const videos = await readPrefix(env, "video:", 800);
  const abtests = await readPrefix(env, "abtest:", 200);
  const [best, worst, strategy, research, weekly, brainState, brainLog] = await Promise.all([
    readJson(env, "patterns:best"),
    readJson(env, "patterns:worst"),
    readJson(env, "strategy:current"),
    readJson(env, "research:latest"),
    readJson(env, "weekly:report"),
    readJson(env, "brain:state"),
    readJson(env, "brain:log"),
  ]);

  const data = {
    videos,
    abtests,
    patterns: { best: best || {}, worst: worst || {} },
    strategy: strategy || {},
    research: research || {},
    weekly: weekly || {},
    brain: { state: brainState || {}, log: brainLog || [] },
  };
  cache.kv = data;
  cache.kvAt = Date.now();
  return data;
}

async function getGh(env) {
  const repo = env.GH_REPO;
  const token = env.GH_TOKEN;
  if (!repo || !token) return { runs: [], configured: false };
  if (cache.gh && Date.now() - cache.ghAt < GH_TTL_MS) return cache.gh;

  try {
    const res = await fetch(
      `https://api.github.com/repos/${repo}/actions/runs?per_page=20`,
      {
        headers: {
          "Authorization": `Bearer ${token}`,
          "Accept": "application/vnd.github+json",
          "User-Agent": "shorts-bot-dashboard",
        },
      }
    );
    if (!res.ok) return { runs: [], configured: true };
    const body = await res.json();
    const runs = (body.workflow_runs || []).map((r) => ({
      id: r.id,
      event: r.event,
      status: r.status,
      conclusion: r.conclusion,
      created_at: r.created_at,
      run_started_at: r.run_started_at,
      updated_at: r.updated_at,
      html_url: r.html_url,
      title: r.display_title || r.name,
    }));
    cache.gh = { runs, configured: true };
    cache.ghAt = Date.now();
    return cache.gh;
  } catch (e) {
    return { runs: [], configured: true };
  }
}

function buildEvents(kv, runs) {
  const ev = [];
  const vids = (kv.videos || []).filter((v) => v.uploaded_at);
  vids
    .slice()
    .sort((a, b) => (b.uploaded_at || "").localeCompare(a.uploaded_at || ""))
    .slice(0, 12)
    .forEach((v) => ev.push({ kind: "upload", t: v.uploaded_at, v }));

  (kv.abtests || [])
    .filter((a) => a.status === "completed" && a.evaluated_at)
    .forEach((a) => ev.push({ kind: "ab", t: a.evaluated_at, a }));

  if (kv.research && kv.research.saved_at) {
    ev.push({ kind: "research", t: kv.research.saved_at, r: kv.research });
  }

  (runs || []).slice(0, 12).forEach((r) =>
    ev.push({ kind: "run", t: r.run_started_at || r.created_at, run: r })
  );

  // Nach echtem Zeitpunkt sortieren (neueste zuerst). Die Bot-Zeitstempel
  // (uploaded_at etc.) sind naive UTC OHNE "Z", GitHub-Zeiten haben "Z" — daher
  // vor dem Vergleich auf echte Epoch-ms normalisieren, sonst stimmt die
  // Reihenfolge bei gemischten Quellen nicht.
  const tms = (s) => Date.parse(/Z|[+-]\d\d:?\d\d$/.test(s || "") ? s : (s || "") + "Z") || 0;
  return ev
    .filter((e) => e.t)
    .sort((a, b) => tms(b.t) - tms(a.t))
    .slice(0, 25);
}

// ---------------------------------------------------------------- KV helpers

async function readJson(env, key) {
  try {
    return await env.KV.get(key, { type: "json" });
  } catch {
    return null;
  }
}

async function readPrefix(env, prefix, cap) {
  const out = [];
  let cursor;
  do {
    const list = await env.KV.list({ prefix, cursor, limit: 1000 });
    for (const k of list.keys) {
      if (out.length >= cap) break;
      const v = await env.KV.get(k.name, { type: "json" });
      if (v) out.push(v);
    }
    cursor = list.list_complete ? null : list.cursor;
  } while (cursor && out.length < cap);
  return out;
}

// ---------------------------------------------------------------- auth/crypto

async function hmacHex(secret, msg) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(msg));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function sign(payload, secret) {
  const p = btoa(JSON.stringify(payload));
  return p + "." + (await hmacHex(secret, p));
}

async function verify(token, secret) {
  if (!token || !token.includes(".")) return false;
  const [p, sig] = token.split(".");
  if ((await hmacHex(secret, p)) !== sig) return false;
  try {
    return JSON.parse(atob(p)).exp > Date.now();
  } catch {
    return false;
  }
}

function cookieVal(req, name) {
  const c = req.headers.get("Cookie") || "";
  const m = c.match(new RegExp("(?:^|; )" + name + "=([^;]+)"));
  return m ? m[1] : null;
}

// ---------------------------------------------------------------- responses

function json(obj, status = 200, extra = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...extra },
  });
}

function html(body, status = 200) {
  return new Response(body, {
    status,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

function loginPage(error) {
  return `<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Animal Shorts</title>
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/icon-180.png">
<link rel="icon" type="image/png" href="/icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Animal Shorts">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
:root{--bg:#fff;--surface:#fafafa;--text:#16181d;--text3:#9aa0ab;--border:rgba(0,0,0,.12);--blue:#2f6fed;--blue-bg:#eaf1fe;--danger:#d23f3f}
@media(prefers-color-scheme:dark){:root{--bg:#0e1014;--surface:#16191f;--text:#e8eaed;--text3:#6b7280;--border:rgba(255,255,255,.14);--blue:#5b8def;--blue-bg:#16243f;--danger:#e06a6a}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:var(--bg);color:var(--text);font-family:'Inter',system-ui,sans-serif}
.box{width:280px;text-align:center}
.logo{width:46px;height:46px;border-radius:12px;background:var(--blue-bg);color:var(--blue);display:flex;align-items:center;justify-content:center;margin:0 auto 18px;font-size:22px;font-weight:600}
h1{font-size:16px;font-weight:600;margin:0 0 2px}
p{font-size:12px;color:var(--text3);margin:0 0 22px}
input{width:100%;height:52px;text-align:center;font-family:'JetBrains Mono',monospace;font-size:26px;letter-spacing:14px;border:1px solid var(--border);background:var(--surface);color:var(--text);border-radius:12px;outline:none;padding-left:14px}
input:focus{border-color:var(--blue)}
button{width:100%;height:44px;margin-top:12px;border:0;border-radius:12px;background:var(--blue);color:#fff;font-family:inherit;font-size:14px;font-weight:500;cursor:pointer}
.err{color:var(--danger);font-size:12px;margin-top:12px;${error ? "" : "display:none"}}
</style></head><body>
<form class="box" method="POST" action="/auth">
<div class="logo">A</div>
<h1>Animal Shorts</h1><p>Operations Console</p>
<input name="pin" type="password" inputmode="numeric" maxlength="4" autocomplete="off" autofocus placeholder="····">
<button type="submit">Entsperren</button>
<div class="err">Falsches PIN</div>
</form></body></html>`;
}
