/**
 * Cloudflare Worker — Cron Trigger
 * Sendet HTTP-Requests zum VPS um Agenten zu triggern.
 *
 * ALTERNATIV: Wenn kein Cloudflare gewünscht, läuft main.py
 * direkt auf Oracle Free Tier VPS mit eigenem schedule-Loop.
 */

export default {
  async scheduled(event, env, ctx) {
    const hour    = new Date().getUTCHours();
    const minute  = new Date().getUTCMinutes();
    const weekday = new Date().getDay(); // 0=Sonntag

    // Researcher alle 6h
    if (hour % 6 === 0 && minute < 2) {
      await triggerAgent(env, "researcher");
    }

    // Strategy täglich 06:00 UTC
    if (hour === 6 && minute < 2) {
      await triggerAgent(env, "strategy");
    }

    // Produktion täglich 02:00 UTC (Nachts → WAN 2.2 Queue leer)
    if (hour === 2 && minute < 2) {
      await triggerAgent(env, "production");
    }

    // Analytics täglich 10:00 UTC
    if (hour === 10 && minute < 2) {
      await triggerAgent(env, "analytics");
    }

    // A/B Test Evaluation täglich 12:00 UTC
    if (hour === 12 && minute < 2) {
      await triggerAgent(env, "ab_evaluate");
    }

    // Optimizer jeden Sonntag 23:00 UTC
    if (weekday === 0 && hour === 23 && minute < 2) {
      await triggerAgent(env, "optimize");
    }
  }
};

async function triggerAgent(env, agentName) {
  try {
    const response = await fetch(
      `${env.BOT_SERVER_URL}/run/${agentName}`,
      {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${env.BOT_API_TOKEN}`,
          "Content-Type": "application/json"
        }
      }
    );
    console.log(`Triggered ${agentName}: ${response.status}`);
  } catch (err) {
    console.error(`Failed to trigger ${agentName}: ${err}`);
  }
}
