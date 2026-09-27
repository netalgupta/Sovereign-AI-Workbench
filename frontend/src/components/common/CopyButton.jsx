/**
 * CopyButton — one copy control for the whole app.
 *
 * `text` may be a string or a function returning one (computed on click,
 * so a large table or answer is only serialised when actually copied).
 * The icon turns into a check for 1.5 s; a failure says so in the title
 * rather than pretending. Works in the browser and in the Electron shell
 * (127.0.0.1 is a secure context; the textarea fallback covers the rest).
 */

import { useEffect, useRef, useState } from 'react'
import { Check, Copy } from 'lucide-react'

async function writeClipboard(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // fall through to the textarea path
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

export function CopyButton({ text, label, title = 'Copy', size = 13, className = '', style }) {
  const [state, setState] = useState('idle') // idle | copied | failed
  const timer = useRef(null)
  useEffect(() => () => clearTimeout(timer.current), [])

  const onClick = async (e) => {
    e.stopPropagation()
    const value = typeof text === 'function' ? text() : text
    const ok = await writeClipboard(String(value ?? ''))
    setState(ok ? 'copied' : 'failed')
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setState('idle'), 1500)
  }

  const Icon = state === 'copied' ? Check : Copy
  return (
    <button
      type="button"
      onClick={onClick}
      title={state === 'failed' ? 'Could not copy -- the clipboard is unavailable' : state === 'copied' ? 'Copied' : title}
      aria-label={title}
      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] font-medium cursor-pointer transition-colors hover:bg-[var(--color-overlay)] ${className}`}
      style={{
        background: 'transparent',
        border: 'none',
        color: state === 'copied' ? 'var(--color-success, #22c55e)' : state === 'failed' ? 'var(--color-danger, #ef4444)' : 'var(--color-text-muted)',
        ...style,
      }}
    >
      <Icon size={size} strokeWidth={2} />
      {label && <span>{state === 'copied' ? 'Copied' : label}</span>}
    </button>
  )
}
