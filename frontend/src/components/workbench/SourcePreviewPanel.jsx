import { useState, useEffect, useCallback } from 'react'
import {
  X,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Download,
  Maximize2,
  Minimize2,
} from 'lucide-react'

import { XlsxGridRenderer } from './renderers/XlsxGridRenderer'
import { ContinuousDocumentRenderer } from './renderers/ContinuousDocumentRenderer'
import { MarkdownPreviewRenderer } from './renderers/MarkdownPreviewRenderer'
import { ImageViewerRenderer } from './renderers/ImageViewerRenderer'
import { TextViewerRenderer } from './renderers/TextViewerRenderer'
import { UnsupportedPreviewRenderer } from './renderers/UnsupportedPreviewRenderer'

export function SourcePreviewPanel({ file, isOpen, onClose }) {
  const [zoomLevel, setZoomLevel] = useState(100)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [pageInfo, setPageInfo] = useState({ current: 1, total: 1, label: '' })

  // Handle Escape Key to close panel or exit fullscreen
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        if (isFullscreen) {
          setIsFullscreen(false)
        } else {
          onClose()
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, isFullscreen, onClose])

  // Reset zoom & page info when file or visibility changes
  useEffect(() => {
    if (!isOpen || !file) {
      setZoomLevel(100)
      setIsFullscreen(false)
      setPageInfo({ current: 1, total: 1, label: '' })
    }
  }, [isOpen, file])

  // Helper to derive clean workspace-relative path identifier for API calls
  const getFilePath = (file) => {
    if (!file) return ''
    if (typeof file === 'string') return file
    if (file.relativePath) return file.relativePath
    if (file.corpus && file.relPath) {
      if (file.corpus === 'User Ingested Sources' || file.corpus === '07_User_Uploads') {
        return `MRPL_RAG_Test_Corpus/07_User_Uploads/${file.relPath}`
      }
      return `${file.corpus}/${file.relPath}`
    }
    return file.relPath || file.name || file.filename || ''
  }

  // Helper for human-readable logical location path
  const getLogicalLocation = (file) => {
    if (!file) return ''
    if (typeof file === 'string') return file
    const name = file.name || file.filename || ''
    const corpus = file.corpus || ''
    const relPath = (file.relPath || '').replace(/\\/g, '/')

    if (corpus && relPath) {
      if (relPath === name) return `${corpus} / ${name}`
      return `${corpus} / ${relPath.replace(/\//g, ' / ')}`
    }
    if (file.folder) return `${corpus ? `${corpus} / ` : ''}${file.folder} / ${name}`
    return corpus ? `${corpus} / ${name}` : name
  }

  const handleZoomIn = () => setZoomLevel((z) => Math.min(z + 25, 250))
  const handleZoomOut = () => setZoomLevel((z) => Math.max(z - 25, 50))
  const handleZoomReset = () => setZoomLevel(100)

  const handleDownload = () => {
    if (!file) return
    const filePath = getFilePath(file)
    const name = typeof file === 'string' ? file.split(/[/\\]/).pop() : (file.name || file.filename || 'download')
    const downloadUrl = `/api/sources/content?path=${encodeURIComponent(filePath)}`

    const a = document.createElement('a')
    a.href = downloadUrl
    a.download = name
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  const handlePageChange = useCallback((current, total, extraLabel = '') => {
    setPageInfo({ current, total, label: extraLabel })
  }, [])

  if (!isOpen || !file) return null

  const name = typeof file === 'string' ? file.split(/[/\\]/).pop() : (file.name || file.filename || 'Document')
  const ext = (file.extension || name.slice(name.lastIndexOf('.') + 1)).toLowerCase()
  const filePath = getFilePath(file)

  // Identify renderer category
  const isXlsx = ['xlsx', 'xls'].includes(ext)
  const isContinuousDoc = ['pdf', 'docx', 'doc', 'pptx', 'ppt'].includes(ext)
  const isMarkdown = ext === 'md'
  const isImage = ['png', 'jpg', 'jpeg', 'webp', 'svg'].includes(ext)
  const isText = ['txt', 'json', 'csv', 'log', 'py', 'js', 'css', 'html', 'xml', 'yaml', 'yml'].includes(ext)

  return (
    <div
      className={`h-full flex flex-col shadow-2xl border-l transition-all duration-200 select-none ${
        isFullscreen
          ? 'fixed inset-0 z-50 w-screen h-screen'
          : 'relative flex-shrink-0 z-20 w-[44vw] min-w-[340px] max-w-[850px]'
      }`}
      style={{
        background: 'var(--color-bg)',
        borderColor: 'var(--color-border)',
        color: 'var(--color-text)',
      }}
    >
      {/* ── Toolbar Header ────────────────────────────────────────────── */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b flex-shrink-0 gap-2"
        style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
      >
        {/* Left: Format Badge + File Name + Location */}
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div
            className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider flex-shrink-0"
            style={{ background: 'var(--color-overlay)', color: 'var(--color-accent)' }}
          >
            {ext}
          </div>
          <div className="flex flex-col min-w-0">
            <h2 className="text-xs sm:text-sm font-bold truncate leading-tight" style={{ color: 'var(--color-text)' }} title={name}>
              {name}
            </h2>
            <span className="text-[10px] font-mono truncate" style={{ color: 'var(--color-text-muted)' }}>
              {getLogicalLocation(file)}
            </span>
          </div>
        </div>

        {/* Middle: Live Page / Slide Counter */}
        {pageInfo.total > 1 && (
          <div
            className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-xs font-mono font-semibold flex-shrink-0"
            style={{ background: 'var(--color-bg)', borderColor: 'var(--color-border)' }}
          >
            {['pptx', 'ppt'].includes(ext) ? 'Slide' : 'Page'} {pageInfo.current} / {pageInfo.total}
            {pageInfo.label && <span className="text-muted text-[11px] ml-1">({pageInfo.label})</span>}
          </div>
        )}

        {/* Right Header Toolbar Actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Zoom Controls */}
          <div
            className="flex items-center gap-0.5 p-0.5 rounded-md border text-xs"
            style={{ background: 'var(--color-bg)', borderColor: 'var(--color-border)' }}
          >
            <button
              type="button"
              onClick={handleZoomOut}
              className="p-1 rounded hover:bg-[var(--color-overlay)] transition-fast cursor-pointer"
              title="Zoom Out (-)"
            >
              <ZoomOut size={13} />
            </button>
            <span className="text-[10px] font-mono px-1 font-semibold">{zoomLevel}%</span>
            <button
              type="button"
              onClick={handleZoomIn}
              className="p-1 rounded hover:bg-[var(--color-overlay)] transition-fast cursor-pointer"
              title="Zoom In (+)"
            >
              <ZoomIn size={13} />
            </button>
            <button
              type="button"
              onClick={handleZoomReset}
              className="p-1 rounded hover:bg-[var(--color-overlay)] transition-fast cursor-pointer"
              title="Reset Zoom (100%)"
            >
              <RotateCcw size={12} />
            </button>
          </div>

          {/* Download Button */}
          <button
            type="button"
            onClick={handleDownload}
            className="p-1.5 rounded-md border text-muted hover:text-[var(--color-text)] hover:bg-[var(--color-overlay)] transition-fast cursor-pointer"
            style={{ borderColor: 'var(--color-border)' }}
            title="Download file"
          >
            <Download size={14} />
          </button>

          {/* Expand / Minimize Fullscreen Toggle */}
          <button
            type="button"
            onClick={() => setIsFullscreen((prev) => !prev)}
            className="p-1.5 rounded-md border text-muted hover:text-[var(--color-text)] hover:bg-[var(--color-overlay)] transition-fast cursor-pointer"
            style={{ borderColor: 'var(--color-border)' }}
            title={isFullscreen ? 'Restore panel width' : 'Expand to full width'}
          >
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>

          {/* Close Panel Button */}
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-md border text-muted hover:text-red-400 hover:bg-red-500/10 transition-fast cursor-pointer"
            style={{ borderColor: 'var(--color-border)' }}
            title="Close panel (Esc)"
          >
            <X size={15} />
          </button>
        </div>
      </div>

      {/* ── Format-Specific Content Body ───────────────────────────── */}
      <div className="flex-1 min-h-0 relative flex flex-col overflow-hidden">
        {isXlsx && (
          <XlsxGridRenderer
            filePath={filePath}
            zoomLevel={zoomLevel}
            onSheetChange={(current, total, sheetName) => handlePageChange(current, total, sheetName)}
          />
        )}

        {isContinuousDoc && (
          <ContinuousDocumentRenderer
            filePath={filePath}
            ext={ext}
            zoomLevel={zoomLevel}
            onPageChange={(current, total) => handlePageChange(current, total)}
          />
        )}

        {isMarkdown && (
          <MarkdownPreviewRenderer
            filePath={filePath}
            zoomLevel={zoomLevel}
          />
        )}

        {isImage && (
          <ImageViewerRenderer
            filePath={filePath}
            name={name}
            zoomLevel={zoomLevel}
          />
        )}

        {isText && (
          <TextViewerRenderer
            filePath={filePath}
            zoomLevel={zoomLevel}
          />
        )}

        {!isXlsx && !isContinuousDoc && !isMarkdown && !isImage && !isText && (
          <UnsupportedPreviewRenderer
            file={file}
            ext={ext}
            onDownload={handleDownload}
          />
        )}
      </div>
    </div>
  )
}
