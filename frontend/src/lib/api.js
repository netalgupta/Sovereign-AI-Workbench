/**
 * api.js — The ONLY file that knows this is mocked.
 *
 * Every component calls sendMessage / checkBackendHealth exactly as if
 * they were real network calls. When Aditya's real FastAPI endpoint is
 * ready, only this file changes — no component or store modifications needed.
 *
 * Contract (FRONTEND.md §3.1, §3.2):
 *   POST /api/chat
 *   Body:     { message: string, session_id: string }
 *   Response: {
 *     reply:      string,          — full markdown body
 *     citations:  Citation[],      — see /src/integrations/citations/contract.js
 *     session_id: string,
 *   }
 */


// ---------------------------------------------------------------------------
// Mock citation data — matches the Citation contract shape exactly.
// When Aditya's backend returns real retrieval passages, this constant is
// replaced by the live API response body. No other file changes.
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Mock citation data — grounded directly in the actual MRPL_RAG_Test_Corpus.
// Matches the Citation contract shape exactly.
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Rich markdown reply used when the user sends a new message.
// Exercises every §3.1-3.3 feature: headings, bold, code block (Python),
// inline citations [1][2], and a markdown table.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Mock plan steps — matches AGENTS_SPEC.md PlanStep schema exactly:
// { id, step_id, description, assigned_agent, status, depends_on, tool_call_event_id }
// Includes a fork: step-2 and step-3 both depend on step-1 in parallel.
// tool_call_event_id strings match the DOM IDs in ChatPane.jsx string-for-string.
// ---------------------------------------------------------------------------
/**
 * Detects if a message expresses an explicit intent to ACT (commanding a critical
 * parameter change or setpoint adjustment) versus an intent to ASK/inquire.
 *
 * Strict requirements:
 * - Questions (ending in '?' or starting with interrogatives like 'What', 'Can you', 'Should we')
 *   MUST NOT trigger approval.
 * - Only imperative verbs indicating a requested change ('increase', 'set', 'change', 'raise',
 *   'adjust', 'modify', 'ramp up') directed at feed rate trigger the gate.
 *
 * @param {string} msg
 * @returns {boolean}
 */

export async function checkBackendHealth() {
  try {
    const res = await fetch('/api/health')
    if (res.ok) {
      const data = await res.json()
      return { ok: true, live: true, ...data }
    }
  } catch {}
  return { ok: true, live: false }
}

/**
 * Send operator decision (Confirm or Cancel) to the safety approval gate.
 */
export async function resolveApproval(requestId, confirmed = true, operator = 'operator') {
  try {
    const res = await fetch('/api/approvals/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request_id: requestId, confirmed, operator }),
    })
    if (res.ok) {
      const data = await res.json()
      return { ok: true, status: data.status || (confirmed ? 'approved' : 'refused'), ...data }
    }
    const errData = await res.json().catch(() => ({}))
    const errorMsg = errData.detail || errData.message || `Backend returned HTTP ${res.status}`
    return { ok: false, status: 'error', error: errorMsg }
  } catch (err) {
    console.warn('[API] /api/approvals/resolve error:', err)
    return { ok: false, status: 'error', error: err?.message || 'Network error reaching /api/approvals/resolve' }
  }
}

/**
 * Fetch live hardware zero-egress telemetry from backend.
 */
export async function getNetworkStatus() {
  try {
    const res = await fetch('/api/network/status')
    if (res.ok) return await res.json()
  } catch {}
  return null
}

/**
 * Read a native File as base64 for the upload endpoint.
 * @param {File} file
 * @returns {Promise<string>} base64 payload (no data: prefix)
 */
export function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '')
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

/**
 * Upload files to the corpus (POST /api/sources/upload). The backend writes
 * them into MRPL_RAG_Test_Corpus/07_User_Uploads, then chunks + embeds them
 * into FAISS so later grounded answers can cite them.
 *
 * @param {Array<{ name: string, file?: File, size?: number }>} files
 * @returns {Promise<object>} { success, count, total_chunks, details, saved, message }
 */
export async function uploadFilesToCorpus(files) {
  const items = []
  for (const f of files) {
    const contentBase64 = await fileToBase64(f.file || f)
    items.push({ name: f.name, contentBase64, sizeBytes: f.size })
  }
  const res = await fetch('/api/sources/upload', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ files: items }),
  })
  if (!res.ok) throw new Error(`Upload failed: HTTP ${res.status}`)
  return res.json()
}

/**
 * Call a registered tool (POST /api/tools/call). Returns the tool's result,
 * already unwrapped from the `{ result }` envelope.
 * @param {string} name
 * @param {object} args
 */
export async function callTool(name, args) {
  const res = await fetch('/api/tools/call', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, arguments: args }),
  })
  if (!res.ok) throw new Error(`Tool ${name} failed: HTTP ${res.status}`)
  const data = await res.json()
  return data.result
}

// name -> { is_estimate, category } fetched once from /api/tools and cached.
// Used to visibly label any tool output that is a model estimate (the vision
// chart reader, measured doses of fabricated values — CHART_STRESS_REPORT.md).
let cachedToolsMeta = null
export async function getToolsMetadata() {
  if (cachedToolsMeta) return cachedToolsMeta
  try {
    const res = await fetch('/api/tools')
    if (res.ok) {
      const data = await res.json()
      cachedToolsMeta = Object.fromEntries(
        (data.tools || []).map((t) => [
          t.name,
          { is_estimate: Boolean(t.is_estimate), category: t.category },
        ])
      )
    }
  } catch {}
  return cachedToolsMeta || {}
}

/**
 * Route an uploaded attachment through the OCR/transcription pipeline.
 * Images -> detect_defects (row 7, DESCOPED: OCR text-region overlay
 * boxes only — never defect findings; fully offline). Audio ->
 * transcribe_voice_note. Other types (PDF/DOCX/XLSX) are handled solely
 * by corpus ingestion, so no tool call is needed.
 *
 * @param {{ name: string }} item
 * @param {string} savedPath - server-side path returned by the upload
 * @returns {Promise<object|null>} tool result, or null when no vision read applies
 */
export async function analyseAttachment(item, savedPath) {
  const ext = (item.name || '').toLowerCase().split('.').pop()
  const isImage = ['png', 'jpg', 'jpeg', 'tiff', 'bmp', 'webp'].includes(ext)
  const isAudio = ['wav', 'mp3', 'm4a', 'ogg', 'flac'].includes(ext)
  if (isImage) return callTool('detect_defects', { image_path: savedPath })
  if (isAudio) return callTool('transcribe_voice_note', { audio_path: savedPath })
  return null
}

// A full agent turn on this hardware is retrieval + a 14B reasoning
// generation + a verification pass, all CPU-bound. Measured end to end
// on the dev box: 69 seconds for a short question, and longer once
// generation is genuinely grounded rather than templated.
//
// This was 60000. The backend took 69s. So the abort ALWAYS fired
// before the reply arrived, every live answer was discarded unread, and
// every message silently became the offline simulation below - which
// renders identically to a real answer. The product appeared to work
// perfectly while never once showing backend output.
//
// A timeout shorter than the operation it guards does not protect
// anything; it just guarantees the fallback path.
const LIVE_TURN_TIMEOUT_MS = 300000 // 5 min

/**
 * Is the backend process actually there?
 *
 * This distinction decides whether falling back to a simulation is
 * honest. Backend absent (dev machine, frontend-only work) -> a clearly
 * labelled simulation is useful. Backend PRESENT but slow or erroring ->
 * a simulation is a lie about a system that is right there and
 * answering, so the failure is reported instead.
 */
async function backendIsReachable() {
  try {
    const ctl = new AbortController()
    const t = setTimeout(() => ctl.abort(), 2500)
    const res = await fetch('/api/health', { signal: ctl.signal })
    clearTimeout(t)
    return res.ok
  } catch {
    return false
  }
}

/**
 * Stream a chat turn from the backend via real SSE (POST /api/chat/stream).
 * Interleaves narration tokens, tool call events, step updates, and approval gates.
 *
 * Falls back to labelled offline simulation only if the backend is genuinely unreachable.
 */
export async function sendMessageStream(message, sessionId, callbacks = {}, options = {}) {
  const {
    onStart,
    onPlan,
    onRoute,
    onMemory,
    onToolCall,
    onToolResult,
    onThought,
    onTextDelta,
    onDeckJob,
    onApprovalRequired,
    onDone,
    onError,
  } = callbacks

  // Defaulting to [] here would tell the backend "every source is
  // switched off" for any caller that does not pass the option at all.
  // null is the only safe default: no filter.
  const { activeDocuments = null } = options

  let liveError = null
  let receivedAnyEvent = false

  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), LIVE_TURN_TIMEOUT_MS)

    const res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        session_id: sessionId || 'default',
        // Sent only when it is a real answer. null is omitted so the
        // backend applies no filter, rather than being told the user
        // deselected everything.
        active_documents: Array.isArray(activeDocuments) ? activeDocuments : null,
      }),
      signal: controller.signal,
    })

    if (res.ok && res.body) {
      clearTimeout(timeout)
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split('\n\n')
        buffer = blocks.pop() // keep unparsed remainder

        for (const block of blocks) {
          const lines = block.split('\n')
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const rawJson = line.slice(6).trim()
              if (!rawJson) continue
              // Only the PARSE is guarded. A handler that throws used to be
              // caught here too and logged as a "JSON parse error": the
              // deck_job case called onDeckJob on an object that did not exist, so
              // every deck, report and spreadsheet started from the chat
              // got no progress card and no Review button, silently.
              let event
              try {
                event = JSON.parse(rawJson)
              } catch (parseErr) {
                console.warn('[SSE] JSON parse error:', parseErr, rawJson)
                continue
              }
              receivedAnyEvent = true
              {
                switch (event.type) {
                  case 'start':
                    onStart?.(event)
                    break
                  case 'plan':
                    onPlan?.(event)
                    break
                  case 'route':
                    onRoute?.(event)
                    break
                  case 'memory':
                    onMemory?.(event)
                    break
                  case 'tool_call':
                    onToolCall?.(event)
                    break
                  case 'tool_result':
                    onToolResult?.(event)
                    break
                  case 'thought':
                    onThought?.(event)
                    break
                  case 'text_delta':
                    onTextDelta?.(event.text || '')
                    break
                  case 'deck_job':
                    onDeckJob?.(event)
                    break
                  case 'approval_required':
                    onApprovalRequired?.(event)
                    break
                  case 'done':
                    onDone?.(event)
                    return { ok: true, ...event }
                  case 'error':
                    onError?.(event.message || 'Stream error occurred')
                    return { ok: false, error: event.message }
                  default:
                    break
                }
              }
            }
          }
        }
      }

      return { ok: true }
    } else {
      liveError = `The backend returned HTTP ${res.status}.`
    }
  } catch (err) {
    liveError =
      err?.name === 'AbortError'
        ? `The agent turn exceeded ${LIVE_TURN_TIMEOUT_MS / 1000}s and was cancelled.`
        : `Could not reach /api/chat/stream: ${err?.message || err}`
    console.warn('[API] Live /api/chat/stream failed:', err)
  }

  // If stream dropped mid-turn after starting
  if (receivedAnyEvent) {
    const streamErr = `Stream connection interrupted: ${liveError}`
    onError?.(streamErr)
    return { ok: false, error: streamErr }
  }

  // 2. The backend is reachable and it failed. Report failure honestly without faking data.
  if (await backendIsReachable()) {
    const failureMsg =
      `**The backend could not complete this turn.**\n\n` +
      `${liveError}\n\n` +
      `No simulated answer is being shown in its place: the backend is running, ` +
      `so anything displayed here would be mistaken for its output. ` +
      `Check the server log for the failing step.`
    onError?.(failureMsg)
    return { ok: false, error: failureMsg }
  }

  // 3. THE BACKEND IS NOT RUNNING. Say so; simulate nothing.
  //
  // What used to be here was a local simulation of a whole turn: a fake
  // route event, a fake search_documents tool call with a fake result,
  // fabricated citations, and -- for anything that looked like an
  // action request -- an invented safety scenario reading
  //
  //     Changing reactor feed rate from 100% (1,450 m3/h) to
  //     115% (1,667 m3/h) exceeds the continuous design basis...
  //     DCS controller FFC-201
  //
  // It was clearly labelled SIMULATED, and the label is the only reason
  // it survived this long. It still has to go, for three reasons:
  //
  //   - Those exact figures are the fabricated approval payload that
  //     has now been removed from this codebase THREE times (the
  //     frontend modal's || fallbacks, the backend's chat handler, and
  //     the streaming path after a branch merge). Every removal left a
  //     copy somewhere else. This is the last one.
  //
  //   - A demo with the backend accidentally down would show a
  //     confident refinery safety interlock over numbers nobody
  //     measured. A viewer who misses one grey line reads it as the
  //     product working.
  //
  //   - It buys nothing. A real demo needs the backend running. The
  //     honest failure state is more useful than a fake success: it
  //     tells you what to fix.
  const offlineMsg =
    '**The backend is not running.**\n\n' +
    'Nothing is being simulated in its place — a simulated answer here ' +
    'would be indistinguishable from a real one at a glance, and this ' +
    'workbench exists to make that distinction impossible to miss.\n\n' +
    'Start it with:\n\n' +
    '```\npy -3 -m backend.main\n```'
  onError?.(offlineMsg)
  return { ok: false, error: offlineMsg, offline: true }
}

/**
 * Backwards-compatible single-shot wrapper around sendMessageStream.
 */
export async function sendMessage(message, sessionId) {
  let reply = ''
  let citations = []
  let plan = []
  let tool_call_events = []
  let awaiting_human_approval = false
  let approval_action = null
  let deck_job = null
  let isLive = true

  const res = await sendMessageStream(message, sessionId, {
    onRoute: () => {},
    onToolCall: (call) => {
      tool_call_events.push({
        id: call.id,
        tool_name: call.name,
        input_params: call.arguments,
        status: 'running',
      })
    },
    onToolResult: (resEv) => {
      const idx = tool_call_events.findIndex((e) => e.id === resEv.id)
      if (idx >= 0) {
        tool_call_events[idx] = {
          ...tool_call_events[idx],
          output: resEv.output,
          status: resEv.status,
          seconds: resEv.seconds,
        }
      }
    },
    onTextDelta: (delta) => {
      reply += delta
    },
    onApprovalRequired: (appEv) => {
      awaiting_human_approval = true
      // NO INVENTED LABELS. This fallback used to title every approval
      // "Confirm Critical Parameter Modification" with action_type
      // DCS_SETPOINT_WRITE -- so a request to write a Word document was
      // shown to the operator as a setpoint change on the one screen where
      // they sign off. Only what the backend actually sent.
      approval_action = appEv.action || {
        id: appEv.id,
        title: 'Confirm action',
        action_type: appEv.name || 'operator action',
        description: appEv.effect || '',
        arguments: appEv.arguments,
      }
    },
    onDeckJob: (jobEv) => {
      deck_job = jobEv.job || null
    },
    onDone: (doneEv) => {
      if (doneEv.citations) citations = doneEv.citations
      if (doneEv.plan) plan = doneEv.plan
      if (doneEv.awaiting_approval !== undefined) awaiting_human_approval = doneEv.awaiting_approval
      if (doneEv.approval_action) approval_action = doneEv.approval_action
      if (doneEv.deck_job) deck_job = doneEv.deck_job
      if (doneEv.simulated) isLive = false
    },
    onError: (err) => {
      reply = err
    },
  })

  if (res?.simulated) isLive = false

  return {
    reply,
    citations,
    plan,
    tool_call_events,
    session_id: sessionId,
    awaiting_human_approval,
    approval_action,
    deck_job,
    live: isLive,
    error: !res?.ok,
  }
}

