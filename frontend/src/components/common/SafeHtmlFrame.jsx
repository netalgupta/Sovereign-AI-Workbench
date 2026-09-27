/**
 * SafeHtmlFrame — renders untrusted HTML (a model's answer, an .html file)
 * so it can be SEEN but cannot reach anything.
 *
 *   sandbox="allow-scripts" without allow-same-origin: the page runs in an
 *     opaque origin -- it cannot read this app's storage, cookies or DOM.
 *   A Content-Security-Policy inside the document: default-src 'none', so
 *     no request leaves the machine -- no CDN script, no web font, no
 *     tracking pixel. Hard constraint #1 holds for previews too; images
 *     and fonts work only as data: URIs.
 */

import { useMemo } from 'react'

const CSP =
  "default-src 'none'; img-src data: blob:; media-src data: blob:; font-src data:; " +
  "style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'none'; base-uri 'none'"

export function SafeHtmlFrame({ html, title = 'HTML preview', height = 360, className = '', style }) {
  const srcDoc = useMemo(() => {
    const meta = `<meta http-equiv="Content-Security-Policy" content="${CSP}"><meta charset="utf-8">`
    const doc = String(html || '')
    // The policy must come first: inject it into <head> when there is one.
    if (/<head[^>]*>/i.test(doc)) return doc.replace(/<head[^>]*>/i, (m) => m + meta)
    if (/<html[^>]*>/i.test(doc)) return doc.replace(/<html[^>]*>/i, (m) => `${m}<head>${meta}</head>`)
    return `<!doctype html><html><head>${meta}<style>body{font-family:system-ui,sans-serif;margin:16px}</style></head><body>${doc}</body></html>`
  }, [html])

  return (
    <iframe
      title={title}
      sandbox="allow-scripts"
      referrerPolicy="no-referrer"
      srcDoc={srcDoc}
      className={className}
      style={{ width: '100%', height, border: 0, background: '#FFFFFF', display: 'block', ...style }}
    />
  )
}
