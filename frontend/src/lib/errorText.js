/**
 * errorText.js — a backend error body, as a sentence a person can read.
 *
 * FastAPI's 422 puts a LIST of objects in `detail`. That list went straight
 * into `approvalError`, React was asked to render an object, and the whole
 * app went blank the moment an approval failed -- the one screen where the
 * operator most needs to see what went wrong.
 */
export function errorText(body, fallback) {
  const detail = body?.detail ?? body?.message
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d) => {
        if (typeof d === 'string') return d
        const where = Array.isArray(d?.loc) ? d.loc.filter((p) => p !== 'body').join('.') : ''
        return [where, d?.msg].filter(Boolean).join(': ') || JSON.stringify(d)
      })
      .join('; ')
  }
  if (detail && typeof detail === 'object') return JSON.stringify(detail)
  return fallback
}
