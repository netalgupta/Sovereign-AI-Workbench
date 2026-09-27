/**
 * promptHistory.js — Up / Down in the composer walks through past prompts,
 * as a terminal does. Pure, so it is tested in Node (promptHistory.test.js).
 *
 * Order: this chat's prompts, newest first, then earlier chats' (newest
 * chat first). Duplicates appear once, at their most recent position. The
 * "Attached: x.pdf" note under a prompt (and the older "[Temporary
 * Attachment: x]" marker) is not part of what was typed, so it is dropped.
 */

export function cleanPrompt(content) {
  if (typeof content !== 'string') return ''
  return content
    .replace(/\[Temporary Attachment:[^\]]*\]/g, '')
    .split('\n')
    .filter((line) => !/^Attached: /.test(line.trim()))
    .join('\n')
    .trim()
}

/**
 * @param {Array} currentMessages  this chat's messages, oldest first
 * @param {Array<Array>} otherChats earlier chats' messages, newest chat first
 * @returns {string[]} newest first
 */
export function collectPrompts(currentMessages = [], otherChats = []) {
  const seen = new Set()
  const out = []
  const take = (messages) => {
    for (let i = (messages || []).length - 1; i >= 0; i--) {
      const m = messages[i]
      if (m?.role !== 'user') continue
      const text = cleanPrompt(m.content)
      if (!text || seen.has(text)) continue
      seen.add(text)
      out.push(text)
    }
  }
  take(currentMessages)
  otherChats.forEach(take)
  return out
}

/**
 * The next state for an Up / Down press, or null when the key should move
 * the caret instead: Up only from the first line, Down only from the last,
 * so editing a multi-line prompt is never hijacked.
 *
 * state: { index: -1 (not browsing) | n, saved: the draft before browsing }
 */
export function stepHistory({ key, draft, caretStart, caretEnd, history, state }) {
  const onFirstLine = !draft.slice(0, caretStart).includes('\n')
  const onLastLine = !draft.slice(caretEnd).includes('\n')
  if (key === 'ArrowUp') {
    if (!onFirstLine || state.index >= history.length - 1) return null
    const index = state.index + 1
    return { index, saved: state.index === -1 ? draft : state.saved, draft: history[index] }
  }
  if (key === 'ArrowDown') {
    if (!onLastLine || state.index < 0) return null
    const index = state.index - 1
    return { index, saved: state.saved, draft: index === -1 ? state.saved : history[index] }
  }
  return null
}
