/**
 * Gehirn — 24/7 denkender Orchestrator für den Bot (Cloudflare Worker).
 *
 * Cron-Herzschlag (alle 4 Min): liest den Bot-Zustand aus KV, fragt Gemini
 * "was ist jetzt sinnvoll und warum?", loggt JEDEN Gedanken nach KV (auch
 * 'idle' → sichtbares Nachdenken) und löst nur bei echtem Handlungsbedarf
 * einen GitHub-Lauf aus. Harte Guardrails verhindern Quota-/Kostenausreißer.
 *
 * Der Bot-Code bleibt unangetastet: das Gehirn liest nur, schreibt eigene
 * brain:*-Keys und triggert workflow_dispatch.
 *
 * Bindings/Secrets:
 *   KV                 (binding)  dieselbe Namespace wie der Bot
 *   var    GH_REPO     "owner/repo"
 *   secret GH_DISPATCH_TOKEN   GitHub-PAT (repo+workflow)
 *   secret GEMINI_API_KEY      Google Gemini API-Key
 *   secret TICK_KEY            Schutz für den manuellen /tick-Endpoint
 */

const WORKFLOW = "bot.yml";
const BRAIN_STATE = "brain:state";
const BRAIN_LOG = "brain:log";
// Google-Modelle in Prioritätsreihenfolge (neuestes zuerst). Jedes hat eine
// eigene Free-Quota — erst wenn ALLE scheitern, übernimmt OpenRouter.
const GEMINI_MODELS = ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"];

const ACTIONS = ["research", "produce", "analytics", "ab_evaluate", "comments", "optimize", "idle"];

// Mindest-Abstände je Aktion (ms) — Guardrail gegen zu häufiges Auslösen.
const COOLDOWN = {
  research: 0.9 * 3600e3,
  produce: 4 * 3600e3,
  analytics: 6 * 3600e3,
  ab_evaluate: 6 * 3600e3,
  comments: 2 * 3600e3,
  optimize: 24 * 3600e3,
};
const MAX_PRODUCE_PER_DAY = 3;

// Quota-Sparmodus: Das LLM wird pro Tick nur befragt, wenn etwas ansteht
// (fälliger Task / Signal). Steht nichts an, wird höchstens 1x pro diesem
// Intervall "nachgedacht" (für die Insight-Analyse) — sonst günstiges Idle
// ohne LLM-Aufruf. So reicht das kostenlose Gemini-Tageskontingent dauerhaft.
const LLM_MIN_INTERVAL_MS = 3 * 60e3; // Mindestabstand fürs "Nachdenken" — unter
// dem Cron-Takt (4 Min), d.h. das Gehirn denkt praktisch JEDEN Tick (24/7 aktiv).
// Verhindert nur pathologische Doppel-Feuer; gespart wird über die Modell-Kette.

// ---------------------------------------------------------------- GitHub

async function dispatch(env, task) {
  const res = await fetch(
    `https://api.github.com/repos/${env.GH_REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: gh(env),
      body: JSON.stringify({ ref: "main", inputs: { task } }),
    }
  );
  console.log(`dispatch ${task} → HTTP ${res.status}`);
  return res.status;
}

async function isRunActive(env) {
  try {
    const res = await fetch(
      `https://api.github.com/repos/${env.GH_REPO}/actions/runs?per_page=5`,
      { headers: gh(env) }
    );
    if (!res.ok) return false;
    const body = await res.json();
    return (body.workflow_runs || []).some(
      (r) => r.status === "in_progress" || r.status === "queued"
    );
  } catch {
    return false;
  }
}

function gh(env) {
  return {
    "Authorization": `Bearer ${env.GH_DISPATCH_TOKEN}`,
    "Accept": "application/vnd.github+json",
    "User-Agent": "animal-shorts-brain",
    "Content-Type": "application/json",
  };
}

// ---------------------------------------------------------------- KV state

async function readJson(env, key) {
  try { return await env.KV.get(key, { type: "json" }); } catch { return null; }
}

async function readPrefix(env, prefix, cap) {
  const out = [];
  let cursor;
  do {
    const l = await env.KV.list({ prefix, cursor, limit: 1000 });
    for (const k of l.keys) { if (out.length >= cap) break; const v = await env.KV.get(k.name, { type: "json" }); if (v) out.push(v); }
    cursor = l.list_complete ? null : l.cursor;
  } while (cursor && out.length < cap);
  return out;
}

async function loadState(env) {
  const s = (await readJson(env, BRAIN_STATE)) || {};
  s.produces_today = s.produces_today || { date: "", count: 0 };
  s.last_dispatch = s.last_dispatch || {};
  return s;
}

function todayUTC() { return new Date().toISOString().slice(0, 10); }

async function logThought(env, state, entry) {
  entry.t = new Date().toISOString();
  state.updated_at = entry.t;
  state.last_action = entry.action;
  state.last_reasoning = entry.reasoning;
  state.last_confidence = entry.confidence;
  state.dispatched = entry.dispatched || null;
  const log = (await readJson(env, BRAIN_LOG)) || [];
  log.unshift(entry);
  await env.KV.put(BRAIN_LOG, JSON.stringify(log.slice(0, 50)));
  await env.KV.put(BRAIN_STATE, JSON.stringify(state));
}

// ---------------------------------------------------------------- decision

async function summarize(env, state) {
  const [best, strat, research] = await Promise.all([
    readJson(env, "patterns:best"),
    readJson(env, "strategy:current"),
    readJson(env, "research:latest"),
  ]);
  const videos = await readPrefix(env, "video:", 60);
  const abtests = await readPrefix(env, "abtest:", 40);
  const now = Date.now();
  const ageHnum = (iso) => (iso ? (now - Date.parse(iso)) / 3600e3 : null);
  const ageH = (iso) => { const h = ageHnum(iso); return h == null ? "nie" : h.toFixed(1) + "h"; };

  const dated = videos.filter((v) => v.uploaded_at).sort((a, b) => (b.uploaded_at || "").localeCompare(a.uploaded_at || ""));
  const recent = dated.slice(0, 5).map((v) => ({
    animal: v.animal, views: v.views || 0, perf: v.performance || null,
    age_h: Math.round(ageHnum(v.uploaded_at) || 0), retention: Math.round(v.avg_view_percentage || 0),
  }));
  const freshUnder48 = dated.filter((v) => { const h = ageHnum(v.uploaded_at); return h != null && h < 48; }).length;
  // ECHTE Tagesproduktion = heute hochgeladene Videos (uploaded_at wird nur bei
  // erfolgreichem Upload gesetzt). Gescheiterte produce-Läufe (z.B. HF-Quota)
  // zählen NICHT — sonst verbrennt ein Fehlschlag einen der 3 Tages-Slots.
  const uploadedToday = dated.filter((v) => (v.uploaded_at || "").slice(0, 10) === todayUTC()).length;
  const abDue = abtests.filter((a) => a.status === "running" && a.started_at && (ageHnum(a.started_at) || 0) > 48).length;
  const r = research || {};

  return {
    utc: new Date().toISOString(),
    weekday_utc: new Date().getUTCDay(),
    videos_total: videos.length,
    fresh_videos_under_48h: freshUnder48,
    recent_videos: recent,
    ab_running_due: abDue,
    viral_count: (best || {}).viral_count ?? 0,
    best_animal: (best || {}).best_animal || null,
    best_hook: (best || {}).best_hook_style || null,
    research: { age: ageH(r.saved_at), top_animals: (r.top_animals || []).slice(0, 3), emerging: r.emerging_trend || null, confidence: r.confidence ?? null, best_post_times_utc: r.best_post_times_utc || null },
    strategy_planned: ((strat || {}).videos || []).length,
    produces_today: uploadedToday,
    last_dispatch_age: Object.fromEntries(ACTIONS.filter((a) => a !== "idle").map((a) => [a, ageH(state.last_dispatch[a])])),
  };
}

async function decide(env, ctx) {
  const prompt = `Du bist das autonome, mitdenkende Gehirn eines YouTube-Shorts-Kanals für Tiervideos.
Du entscheidest datengetrieben, welcher EINE Schritt als Nächstes sinnvoll ist – oder ob gerade nichts zu tun ist – und reagierst dabei auf konkrete Signale.

Aktuelle Lage (UTC):
${JSON.stringify(ctx, null, 2)}

Erlaubte Aktionen:
- research: Trends sammeln/analysieren. Sinnvoll wenn research.age alt (>1h) — der Kanal soll Trends sehr früh erkennen.
- produce: 1 Video planen, bauen, hochladen. produces_today = heute bereits ERFOLGREICH hochgeladene Videos; Ziel sind ${MAX_PRODUCE_PER_DAY}/Tag. Die Läufe sollen zu den vom Research empfohlenen Posting-Zeiten laufen: research.best_post_times_utc (UTC, "HH:MM"). Wähle produce, wenn produces_today < ${MAX_PRODUCE_PER_DAY} UND die aktuelle UTC-Zeit nahe (±15 Min) an einer Posting-Zeit liegt — sonst auf das nächste Fenster warten. (Ein gescheiterter Lauf erhöht produces_today nicht, wird also automatisch erneut versucht.)
- analytics: Performance vorhandener Videos aktualisieren (~1x/Tag, wenn Videos existieren).
- ab_evaluate: laufende A/B-Tests auswerten.
- comments: Kommentare der letzten Videos beantworten (nur wenn Videos existieren).
- optimize: wöchentliche Strategie-Optimierung (sonntags).
- idle: nichts tun.

Reaktive Heuristik (nutze die Signale!):
- ab_running_due > 0  → ab_evaluate ist überfällig.
- fresh_videos_under_48h > 0 und comments-Cooldown vorbei → comments (Engagement der frischen Videos nutzen).
- recent_videos mit hohen/steigenden views → analytics (Daten sichern), ggf. comments (Reichweite mitnehmen).
- UTC-Zeit nahe einem research.best_post_times_utc-Fenster UND produces_today < ${MAX_PRODUCE_PER_DAY} → produce (zur empfohlenen Zeit posten).
- research veraltet → research.
- sonst → idle. Sei sparsam, löse nichts ohne Grund aus.

Antworte NUR als JSON:
{"action":"<aktion>","reasoning":"<1-2 Sätze, warum jetzt – nenne das konkrete Signal>","confidence":<0..1>,"insight":"<2-3 Sätze strategische Analyse auf Deutsch: gewichte EIGENE Erfahrung (was bei uns funktioniert hat) höher als externe Trends; nenne konkret Tier/Winkel/Setting/Hook/Hashtag-Richtung, auf die als Nächstes gesetzt werden sollte, und was zu vermeiden ist>"}`;

  const text = await askLLM(env, prompt);
  const out = JSON.parse(text);
  if (!ACTIONS.includes(out.action)) out.action = "idle";
  out.confidence = typeof out.confidence === "number" ? out.confidence : 0.5;
  out.reasoning = out.reasoning || "(keine Begründung)";
  out.insight = out.insight || null;
  return out;
}

// LLM-Aufruf mit Fallback: Gemini zuerst, bei Fehler OpenRouter. Gibt JSON-Text
// zurück. Damit denkt das Gehirn auch weiter, wenn Geminis Quota erschöpft ist.
async function askLLM(env, prompt) {
  // Google-Modelle der Reihe nach (neuestes zuerst), jedes mit eigener Free-Quota.
  for (const model of GEMINI_MODELS) {
    try {
      return await geminiJson(env, model, prompt);
    } catch (e) {
      console.log("Gemini " + model + " fehlgeschlagen (" + e.message + ") → nächstes Modell");
    }
  }
  // Erst wenn ALLE Google-Modelle ausfallen: OpenRouter.
  if (!env.OPENROUTER_API_KEY) throw new Error("alle Gemini-Modelle fehlgeschlagen, kein OpenRouter-Key");
  console.log("Alle Google-Modelle nicht verfügbar → OpenRouter-Fallback");
  return await openrouterJson(env, prompt);
}

async function geminiJson(env, model, prompt) {
  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${env.GEMINI_API_KEY}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: { responseMimeType: "application/json", temperature: 0.4 },
      }),
    }
  );
  if (!res.ok) throw new Error("gemini HTTP " + res.status);
  const body = await res.json();
  return body?.candidates?.[0]?.content?.parts?.[0]?.text || "{}";
}

async function openrouterJson(env, prompt) {
  const model = env.OPENROUTER_MODEL || "google/gemini-2.5-flash";
  const res = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: {
      "Authorization": "Bearer " + env.OPENROUTER_API_KEY,
      "Content-Type": "application/json",
      "HTTP-Referer": "https://github.com/gio27-cmd/youtube-shorts-bot",
      "X-Title": "Animal Shorts Brain",
    },
    body: JSON.stringify({
      model,
      messages: [{ role: "user", content: prompt }],
      response_format: { type: "json_object" },
      temperature: 0.4,
      // Deckel: sonst reserviert OpenRouter das volle Output-Budget → 402 bei wenig Guthaben.
      max_tokens: 2048,
    }),
  });
  if (!res.ok) throw new Error("openrouter HTTP " + res.status);
  const body = await res.json();
  return body?.choices?.[0]?.message?.content || "{}";
}

// ---------------------------------------------------------------- guardrails

function guard(action, state, runActive, uploadedToday) {
  if (action === "idle") return { ok: false, reason: "idle" };
  if (runActive) return { ok: false, reason: "Lauf bereits aktiv – warte" };
  if (action === "produce") {
    // Limit zählt ERFOLGREICHE Uploads heute, nicht Dispatches. So wird ein
    // gescheiterter Lauf (HF-Quota) am nächsten Posting-Fenster neu versucht,
    // statt einen Slot zu verbrennen. Der 4h-Cooldown verhindert Hämmern.
    if ((uploadedToday || 0) >= MAX_PRODUCE_PER_DAY) return { ok: false, reason: `Tageslimit ${MAX_PRODUCE_PER_DAY} Uploads erreicht` };
  }
  const last = state.last_dispatch[action];
  if (last && Date.now() - Date.parse(last) < (COOLDOWN[action] || 0)) {
    return { ok: false, reason: `Cooldown für ${action} aktiv` };
  }
  return { ok: true, reason: "" };
}

// Sicherheitsnetz: garantiert kritische Tasks zeitnah, falls Gemini zu zögerlich
// ist oder ausfällt. Liefert die fällige Aktion oder null.
function safetyNet(state, ctxData) {
  const d = new Date(), H = d.getUTCHours(), M = d.getUTCMinutes(), W = d.getUTCDay();
  const slot = M < 15 ? 0 : 30;
  const cand = [];
  // produce zu den vom Research empfohlenen Posting-Zeiten (Fallback: feste
  // Slots, falls noch kein Research vorliegt). guard() begrenzt auf
  // MAX_PRODUCE_PER_DAY + Cooldown. Fenster = 15 Min ab der empfohlenen Zeit,
  // damit ein 4-Min-Tick es sicher trifft.
  const postTimes = (ctxData && ctxData.research && ctxData.research.best_post_times_utc)
    || ["02:30", "10:30", "18:30"];
  const nowMin = H * 60 + M;
  for (const t of postTimes) {
    const m = /^(\d{1,2}):(\d{2})$/.exec(String(t).trim());
    if (!m) continue;
    const tm = (+m[1]) * 60 + (+m[2]);
    if (nowMin >= tm && nowMin < tm + 15) { cand.push("produce"); break; }
  }
  if (slot === 0) cand.push("research");   // stündlich
  if (H === 10 && slot === 0) cand.push("analytics");
  if (H === 12 && slot === 0) cand.push("ab_evaluate");
  if ((H === 9 || H === 15 || H === 21) && slot === 0) cand.push("comments");
  if (W === 0 && H === 23 && slot === 0) cand.push("optimize");
  for (const a of cand) {
    const last = state.last_dispatch[a];
    if (!last || Date.now() - Date.parse(last) > (COOLDOWN[a] || 0)) return a;
  }
  return null;
}

// ---------------------------------------------------------------- core cycle

async function cycle(env, ctx) {
  const state = await loadState(env);
  const runActive = await isRunActive(env);
  let decision, source = "gemini", ctxData = null;

  // Kontext (KV + GitHub-API) ist günstig und kostet kein LLM-Kontingent.
  try { ctxData = await summarize(env, state); } catch (e) { ctxData = null; }

  // Quota-Sparmodus: Das LLM nur befragen, wenn wirklich etwas ansteht —
  // ein planmäßig fälliger Task, ein konkretes Signal, oder höchstens ~1x/Std
  // fürs strategische Nachdenken. Sonst günstiges Idle ohne LLM-Aufruf.
  const due = safetyNet(state, ctxData);
  const hasSignal = !!ctxData && (ctxData.ab_running_due > 0 || ctxData.fresh_videos_under_48h > 0);
  const sinceLLM = state.last_llm_at ? Date.now() - Date.parse(state.last_llm_at) : Infinity;
  const insightDue = sinceLLM > LLM_MIN_INTERVAL_MS;
  const askLLM = !runActive && !!ctxData && (due || hasSignal || insightDue);

  if (askLLM) {
    try {
      decision = await decide(env, ctxData);
      state.last_llm_at = new Date().toISOString();
    } catch (e) {
      source = "fallback";
      decision = { action: due || "idle", reasoning: "LLM nicht erreichbar → Zeitplan-Fallback (" + e.message + ")", confidence: 0.3 };
    }
  } else {
    source = "sparmodus";
    const reason = runActive ? "Lauf aktiv – warte"
                 : !ctxData ? "Kontext nicht verfügbar – warte"
                 : "nichts fällig – spare LLM-Quota";
    decision = { action: "idle", reasoning: reason, confidence: 0.4, insight: state.insight || null };
  }

  // Tageslimit zählt erfolgreiche Uploads. Ohne Kontext (KV nicht lesbar) blocken
  // wir produce vorsichtshalber (so als ob das Limit erreicht wäre).
  const uploadedToday = ctxData ? ctxData.produces_today : MAX_PRODUCE_PER_DAY;
  let g = guard(decision.action, state, runActive, uploadedToday);

  // Sicherheitsnetz: wenn Gemini idle wählt, aber ein kritischer Task fällig ist.
  if (!g.ok && decision.action === "idle") {
    const net = safetyNet(state, ctxData);
    if (net) {
      const ng = guard(net, state, runActive, uploadedToday);
      if (ng.ok) { decision = { action: net, reasoning: "Sicherheitsnetz: planmäßiger " + net + " fällig.", confidence: 0.6 }; g = ng; source = source + "+net"; }
    }
  }

  let dispatched = null;
  if (g.ok) {
    const status = await dispatch(env, decision.action);
    if (status === 204) {
      dispatched = decision.action;
      state.last_dispatch[decision.action] = new Date().toISOString();
      if (decision.action === "produce") {
        // Reiner Dispatch-Trace (wie oft heute ausgelöst). Das Tageslimit zählt
        // erfolgreiche Uploads (guard via uploadedToday), NICHT diesen Zähler.
        const today = todayUTC();
        if (state.produces_today.date !== today) state.produces_today = { date: today, count: 0 };
        state.produces_today.count += 1;
      }
    } else {
      g.reason = "dispatch fehlgeschlagen (HTTP " + status + ")";
    }
  }

  state.insight = decision.insight || state.insight || null;
  if (ctxData) {
    state.observed = {
      trend: ctxData.research.emerging || (ctxData.research.top_animals[0] || null),
      research_age: ctxData.research.age,
      fresh_videos_48h: ctxData.fresh_videos_under_48h,
      ab_due: ctxData.ab_running_due,
      videos_total: ctxData.videos_total,
      top_recent: ctxData.recent_videos[0] || null,
      produces_today: ctxData.produces_today,
      post_times: ctxData.research.best_post_times_utc || null,
    };
  }

  await logThought(env, state, {
    action: decision.action,
    reasoning: decision.reasoning,
    confidence: decision.confidence,
    insight: decision.insight || null,
    source,
    blocked: g.ok ? null : g.reason,
    dispatched,
  });

  return { decision, dispatched, blocked: g.ok ? null : g.reason, source };
}

// ---------------------------------------------------------------- handlers

export default {
  async scheduled(event, env, ctx) {
    if (!env.GH_DISPATCH_TOKEN || !env.GEMINI_API_KEY) {
      console.log("Secrets fehlen — Zyklus übersprungen");
      return;
    }
    ctx.waitUntil(cycle(env, ctx));
  },

  async fetch(req, env, ctx) {
    const url = new URL(req.url);

    // Manueller Einzelzyklus zum Verifizieren (durch TICK_KEY geschützt).
    if (url.pathname === "/tick") {
      if (!env.TICK_KEY || url.searchParams.get("key") !== env.TICK_KEY) {
        return new Response("forbidden", { status: 403 });
      }
      const result = await cycle(env, ctx);
      return json(result);
    }

    const state = await loadState(env);
    return json({
      service: "animal-shorts-brain",
      utc: new Date().toISOString(),
      repo: env.GH_REPO || null,
      gemini_set: !!env.GEMINI_API_KEY,
      token_set: !!env.GH_DISPATCH_TOKEN,
      last_action: state.last_action || null,
      last_reasoning: state.last_reasoning || null,
      updated_at: state.updated_at || null,
    });
  },
};

function json(obj) {
  return new Response(JSON.stringify(obj, null, 2), {
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}
