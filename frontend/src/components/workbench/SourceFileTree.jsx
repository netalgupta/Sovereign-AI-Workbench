import { useState } from 'react'
import {
  ChevronRight,
  ChevronDown,
  Folder,
  FolderOpen,
  FileText,
  Image as ImageIcon,
  Database,
  Plug,
  FileCode,
  HardDrive,
} from 'lucide-react'

function getFileIcon(type, category, ext) {
  if (type === 'API' || ext === 'API') return <Plug size={12} strokeWidth={1.8} />
  if (
    type === 'PNG' ||
    type === 'SCAN' ||
    type === 'P&ID' ||
    category === 'charts' ||
    ext === 'PNG' ||
    ext === 'JPG' ||
    ext === 'SCAN' ||
    ext === 'P&ID'
  ) {
    return <ImageIcon size={12} strokeWidth={1.8} />
  }
  if (type === 'JSON' || ext === 'JSON') return <FileCode size={12} strokeWidth={1.8} />
  if (category === 'data' || type === 'XLSX' || ext === 'XLSX' || ext === 'CSV') {
    return <Database size={12} strokeWidth={1.8} />
  }
  return <FileText size={12} strokeWidth={1.8} />
}

function getFileTypeLabel(node) {
  if (node.id?.includes('API') || node.category === 'apis') return 'API'
  const name = node.name || ''
  const dotIdx = name.lastIndexOf('.')
  if (dotIdx !== -1) {
    const rawExt = name.slice(dotIdx + 1).toUpperCase()
    if (rawExt === 'DOCX' || rawExt === 'DOC') return 'DOCX'
    if (rawExt === 'PDF') return 'PDF'
    if (rawExt === 'XLSX' || rawExt === 'XLS') return 'XLSX'
    if (rawExt === 'CSV') return 'CSV'
    if (rawExt === 'PNG' || rawExt === 'JPG' || rawExt === 'JPEG') {
      if (name.toLowerCase().includes('checklist')) return 'SCAN'
      if (name.toLowerCase().includes('pid')) return 'P&ID'
      return 'PNG'
    }
    if (rawExt === 'JSON') return 'JSON'
    if (rawExt === 'MD') return 'MARKDOWN'
    return rawExt
  }
  return node.iconText || node.fileType || 'FILE'
}

function getFileTypeTheme(ext, category) {
  switch (ext) {
    case 'DOCX':
    case 'DOC':
      return {
        color: '#60a5fa', // soft sky / cornflower blue
        bg: 'rgba(96, 165, 250, 0.12)',
        border: 'rgba(96, 165, 250, 0.25)',
      }
    case 'PDF':
      return {
        color: '#f87171', // soft coral red
        bg: 'rgba(248, 113, 113, 0.12)',
        border: 'rgba(248, 113, 113, 0.25)',
      }
    case 'XLSX':
    case 'XLS':
    case 'CSV':
      return {
        color: '#34d399', // soft sage / emerald green
        bg: 'rgba(52, 211, 153, 0.12)',
        border: 'rgba(52, 211, 153, 0.25)',
      }
    case 'PNG':
    case 'JPG':
    case 'JPEG':
    case 'SCAN':
      return {
        color: '#c084fc', // soft lavender purple
        bg: 'rgba(192, 132, 252, 0.12)',
        border: 'rgba(192, 132, 252, 0.25)',
      }
    case 'P&ID':
      return {
        color: '#fbbf24', // soft warm amber
        bg: 'rgba(251, 191, 36, 0.12)',
        border: 'rgba(251, 191, 36, 0.25)',
      }
    case 'JSON':
      return {
        color: '#fb923c', // soft orange
        bg: 'rgba(251, 146, 60, 0.12)',
        border: 'rgba(251, 146, 60, 0.25)',
      }
    case 'API':
      return {
        color: '#38bdf8', // soft cyan
        bg: 'rgba(56, 189, 248, 0.12)',
        border: 'rgba(56, 189, 248, 0.25)',
      }
    case 'MARKDOWN':
    case 'MD':
      return {
        color: '#cbd5e1', // soft neutral slate
        bg: 'rgba(203, 213, 225, 0.12)',
        border: 'rgba(203, 213, 225, 0.22)',
      }
    default:
      if (category === 'data') {
        return {
          color: '#34d399',
          bg: 'rgba(52, 211, 153, 0.12)',
          border: 'rgba(52, 211, 153, 0.25)',
        }
      }
      return {
        color: '#94a3b8',
        bg: 'rgba(148, 163, 184, 0.12)',
        border: 'rgba(148, 163, 184, 0.22)',
      }
  }
}

export function SourceFileTree({
  tree = [],
  filterCategory = 'all',
  searchQuery = '',
  selectedId = null,
  onSelectSource,
  onToggleSource,
  compact = false,
}) {
  // Store expanded folder IDs
  const [expandedFolders, setExpandedFolders] = useState(() => {
    const initial = new Set()
    tree.forEach((root) => {
      initial.add(root.id)
      if (root.children) {
        root.children.forEach((c) => {
          if (c.type === 'directory') initial.add(c.id)
        })
      }
    })
    return initial
  })

  const toggleFolder = (folderId) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev)
      if (next.has(folderId)) {
        next.delete(folderId)
      } else {
        next.add(folderId)
      }
      return next
    })
  }

  // Recursive tree renderer
  const renderNode = (node, depth = 0) => {
    const isDir = node.type === 'directory'
    const isExpanded = expandedFolders.has(node.id) || !!searchQuery.trim()

    // Filtering logic
    if (!isDir) {
      if (filterCategory !== 'all') {
        if (filterCategory === 'documents' && node.category !== 'documents') return null
        if (filterCategory === 'data' && node.category !== 'data') return null
        if (filterCategory === 'charts' && node.category !== 'charts') return null
        if (filterCategory === 'apis' && node.category !== 'apis') return null
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        if (
          !node.name.toLowerCase().includes(q) &&
          !node.badge?.toLowerCase().includes(q) &&
          !node.corpus?.toLowerCase().includes(q)
        ) {
          return null
        }
      }
    }

    if (isDir) {
      // Check if folder has visible children under current filter
      const children = (node.children || [])
        .map((c) => renderNode(c, depth + 1))
        .filter(Boolean)

      // If search/category filter active and no matching children, hide folder
      if ((filterCategory !== 'all' || searchQuery.trim()) && children.length === 0) {
        return null
      }

      return (
        <div key={node.id} className="flex flex-col select-none">
          {/* Folder header row */}
          <div
            onClick={() => toggleFolder(node.id)}
            className="flex items-center justify-between py-1 px-1.5 rounded hover:bg-[var(--color-surface-hover)] transition-fast cursor-pointer group"
            style={{
              paddingLeft: `${depth * 12 + 6}px`,
              background: depth === 0 ? 'var(--color-overlay)' : 'transparent',
              marginTop: depth === 0 ? 3 : 0,
              marginBottom: 1,
            }}
          >
            <div className="flex items-center gap-1.5 min-w-0 flex-1 pr-2">
              <span className="text-[var(--color-text-muted)] group-hover:text-[var(--color-text)] transition-fast">
                {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              </span>

              {depth === 0 ? (
                <HardDrive
                  size={13}
                  className="flex-shrink-0"
                  style={{ color: 'var(--color-accent)' }}
                />
              ) : isExpanded ? (
                <FolderOpen
                  size={13}
                  className="flex-shrink-0"
                  style={{ color: 'var(--color-accent)' }}
                />
              ) : (
                <Folder
                  size={13}
                  className="flex-shrink-0"
                  style={{ color: 'var(--color-text-muted)' }}
                />
              )}

              <span
                className={`truncate font-sans ${
                  depth === 0 ? 'text-[12px] font-semibold tracking-tight' : 'text-[11.5px] font-medium'
                }`}
                style={{ color: 'var(--color-text)' }}
                title={node.name}
              >
                {node.name}
              </span>
            </div>

            <div className="flex items-center gap-1.5 flex-shrink-0">
              <span
                className="text-[10px] font-sans px-1.5 py-0.5 rounded font-medium"
                style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-muted)',
                }}
              >
                {node.fileCount}
              </span>
              {node.sizeDisplay && node.sizeDisplay !== 'Live Data' && (
                <span className="text-[10px] font-sans hidden sm:inline" style={{ color: 'var(--color-text-faint)' }}>
                  {node.sizeDisplay}
                </span>
              )}
            </div>
          </div>

          {/* Children container */}
          {isExpanded && <div className="flex flex-col">{children}</div>}
        </div>
      )
    }

    // File Node
    const isSelected = selectedId === node.id
    const isEnabled = node.enabled !== false
    const fileType = getFileTypeLabel(node)
    const theme = getFileTypeTheme(fileType, node.category)

    return (
      <div
        key={node.id}
        onClick={() => onSelectSource && onSelectSource(node)}
        className="flex items-center justify-between py-1.5 px-2 rounded-md transition-fast group cursor-pointer"
        style={{
          paddingLeft: `${depth * 12 + 16}px`,
          background: isSelected ? 'var(--color-surface-hover)' : 'transparent',
          borderLeft: isSelected ? '2px solid var(--color-accent)' : '2px solid transparent',
          opacity: isEnabled ? 1 : 0.55,
        }}
        title={`${node.name} • ${fileType} • ${node.size || ''}`}
      >
        <div className="flex items-center gap-2 min-w-0 flex-1 pr-2">
          {/* Subtle colored File Icon to differentiate types */}
          <div
            className="w-5 h-5 rounded flex items-center justify-center flex-shrink-0 transition-fast"
            style={{
              background: theme.bg,
              color: theme.color,
              border: `1px solid ${theme.border}`,
            }}
          >
            {getFileIcon(node.type, node.category, fileType)}
          </div>

          <div className="flex flex-col min-w-0 flex-1 justify-center">
            {/* Clean File Name — Not AI generated or monospace */}
            <span
              className={`truncate font-sans leading-snug tracking-tight ${
                compact ? 'text-[11px]' : 'text-[11.5px]'
              } ${isSelected ? 'font-semibold text-[var(--color-text)]' : 'font-normal text-[var(--color-text)]'}`}
            >
              {node.name}
            </span>

            {/* Faint file type and size — NO RED TEXT, NO CLUTTER */}
            {!compact && (
              <div className="flex items-center gap-1.5 text-[10px] font-sans mt-0.5 leading-none whitespace-nowrap overflow-hidden">
                <span
                  className="font-medium text-[9px] uppercase tracking-wider px-1 py-0.2 rounded"
                  style={{
                    color: theme.color,
                    background: theme.bg,
                    border: `1px solid ${theme.border}`,
                  }}
                >
                  {fileType}
                </span>
                {node.size && (
                  <>
                    <span className="text-[9px] text-[var(--color-text-faint)] opacity-40">·</span>
                    <span className="text-[10px] text-[var(--color-text-faint)]">
                      {node.size}
                    </span>
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Toggle Switch */}
        {onToggleSource && (
          <button
            type="button"
            role="switch"
            aria-checked={isEnabled}
            onClick={(e) => {
              e.stopPropagation()
              onToggleSource(node.id)
            }}
            className="rounded-full transition-base relative flex-shrink-0 cursor-pointer"
            style={{
              width: 24,
              height: 13,
              background: isEnabled ? 'var(--color-accent)' : 'var(--color-border-strong)',
            }}
            title={isEnabled ? 'Included in retrieval scope' : 'Excluded from retrieval scope'}
          >
            <span
              className="absolute top-[1.5px] w-2 h-2 rounded-full bg-white transition-fast shadow-xs"
              style={{
                left: isEnabled ? 13 : 2,
              }}
            />
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-0.5 py-1">
      {tree.map((rootNode) => renderNode(rootNode, 0))}
    </div>
  )
}
