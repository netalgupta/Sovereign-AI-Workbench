/**
 * CodeFilesBar — "these N files, as one zip", under an answer whose code
 * spans several named files (lib/codeFiles.js). Built in the browser
 * (lib/zip.js): nothing is written on the server, so it needs no approval,
 * and nothing leaves the machine.
 */

import { useMemo } from 'react'
import { FileArchive, FileCode } from 'lucide-react'
import { extractCodeFiles } from '../../lib/codeFiles'
import { makeZip } from '../../lib/zip'

function zipName(files) {
  const top = files.map((f) => f.name.split('/')[0])
  const shared = top.every((t) => t === top[0]) && files.every((f) => f.name.includes('/'))
  return `${shared ? top[0] : 'code-files'}.zip`
}

export function CodeFilesBar({ content }) {
  const files = useMemo(() => extractCodeFiles(content), [content])
  if (files.length < 2) return null

  const download = () => {
    const blob = new Blob([makeZip(files)], { type: 'application/zip' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = zipName(files)
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 2000)
  }

  return (
    <div
      className="flex flex-wrap items-center gap-2 rounded-xl border px-3 py-2.5 max-w-2xl"
      style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
    >
      <FileArchive size={16} style={{ color: 'var(--color-accent)' }} />
      <span className="text-[12px] font-semibold" style={{ color: 'var(--color-text)' }}>
        {files.length} files
      </span>
      <div className="flex flex-wrap gap-1.5 min-w-0 flex-1">
        {files.map((f) => (
          <span
            key={f.name}
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-mono border select-text"
            style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}
          >
            <FileCode size={11} /> {f.name}
          </span>
        ))}
      </div>
      <button
        type="button"
        onClick={download}
        className="px-3 py-1.5 rounded-lg text-[12px] font-semibold text-white cursor-pointer hover:brightness-110"
        style={{ background: 'var(--color-accent)' }}
        title={`Download ${zipName(files)}`}
      >
        Download all (.zip)
      </button>
    </div>
  )
}
