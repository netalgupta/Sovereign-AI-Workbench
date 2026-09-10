/**
 * api.js — The ONLY file that knows this is mocked.
 *
 * Every component calls sendMessage / checkBackendHealth exactly as if
 * they were real network calls. When Aditya's real FastAPI endpoint is
 * ready, only this file changes — no component or store modifications needed.
 *
 * Contract (self-owned, Day 1-2):
 *   POST /api/chat
 *   Body:     { message: string, session_id: string }
 *   Response: { reply: string, session_id: string }
 */

const MOCK_LATENCY_MS = 600

export async function checkBackendHealth() {
  // Always "online" — this IS the backend for now, by design, not a fallback.
  return { ok: true }
}

export async function sendMessage(message, sessionId) {
  await new Promise((r) => setTimeout(r, MOCK_LATENCY_MS))
  return {
    reply: `Mock response to: "${message}"`,
    session_id: sessionId,
  }
}
