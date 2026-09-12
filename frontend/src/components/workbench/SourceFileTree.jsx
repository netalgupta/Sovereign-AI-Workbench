import { useState, useEffect } from 'react'
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
  Trash2,
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
  onDeleteSource,
  compact = false,
}) {
  // Helper to gather all directory IDs recursively
  const getAllDirectoryIds = (nodes) => {
    const ids = new Set()
    function walk(list) {
      if (!Array.isArray(list)) return
      for (const n of list) {
        if (n.type === 'directory') {
          ids.add(n.id)
          if (n.children) walk(n.children)
        }
      }
    }
    walk(nodes)
    return ids
  }

  // Store expanded folder IDs — expanded by default so files are never hidden
  const [expandedFolders, setExpandedFolders] = useState(() => getAllDirectoryIds(tree))

  // Local set of disabled node IDs for immediate instantaneous feedback
  const [disabledNodeIds, setDisabledNodeIds] = useState(() => {
    const disabled = new Set()
    const scan = (nodes) => {
      if (!Array.isArray(nodes)) return
      for (const n of nodes) {
        if (n.enabled === false) disabled.add(n.id)
        if (n.children) scan(n.children)
      }
    }
    scan(tree)
    return disabled
  })

  // Auto-expand all folders whenever tree updates (e.g. newly added folder or file)
  useEffect(() => {
    if (tree && tree.length > 0) {
      setExpandedFolders((prev) => {
        const all = getAllDirectoryIds(tree)
        // Merge with existing so user manual closes can be respected or all open
        return new Set([...prev, ...all])
      })
      // Synchronize disabled state if provided in tree nodes
      setDisabledNodeIds((prev) => {
        const next = new Set(prev)
        const scan = (nodes) => {
          if (!Array.isArray(nodes)) return
          for (const n of nodes) {
            if (n.enabled === false) next.add(n.id)
            if (n.children) scan(n.children)
          }
        }
        scan(tree)
        return next
      })
    }
  }, [tree])

  const handleToggle = (e, node) => {
    e.stopPropagation()
    const currentlyDisabled = disabledNodeIds.has(node.id) || node.enabled === false
    const willBeEnabled = currentlyDisabled

    setDisabledNodeIds((prev) => {
      const next = new Set(prev)
      if (willBeEnabled) {
        next.delete(node.id)
      } else {
        next.add(node.id)
      }
      return next
    })

    if (onToggleSource) {
      onToggleSource(node.id, willBeEnabled, node)
    }
  }

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

  const expandAll = () => setExpandedFolders(getAllDirectoryIds(tree))
  const collapseAll = () => setExpandedFolders(new Set())

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

      const isCustomOrUploaded = !node.isPreset || node.name === '07_User_Uploads' || node.id === 'user_uploads_corpus' || node.id === 'user_ingested_files_root'
      const isRootSection = depth === 0

      return (
        <div key={node.id} className="flex flex-col select-none">
          {/* Folder header row */}
          <div
            onClick={() => toggleFolder(node.id)}
            className={`flex items-center justify-between transition-fast cursor-pointer group ${
              isRootSection
                ? 'py-1.5 px-2 rounded-lg my-0.5 border shadow-xs'
                : 'py-1 px-1.5 rounded-md my-0.5 hover:bg-[var(--color-surface-hover)]'
            }`}
            style={{
              background: isRootSection
                ? isExpanded
                  ? 'var(--color-surface)'
                  : 'var(--color-bg)'
                : 'transparent',
              borderColor: isRootSection ? 'var(--color-border)' : 'transparent',
              paddingLeft: isRootSection ? '8px' : `${depth * 6 + 4}px`,
            }}
          >
            <div className="flex items-center gap-2 min-w-0 flex-1 pr-2">
              <span className="text-[var(--color-text-muted)] group-hover:text-[var(--color-text)] transition-fast flex-shrink-0">
                {isExpanded ? <ChevronDown size={12} strokeWidth={2.2} /> : <ChevronRight size={12} strokeWidth={2.2} />}
              </span>

              {isRootSection ? (
                <div
                  className="w-5 h-5 rounded flex items-center justify-center flex-shrink-0"
                  style={{
                    background: 'var(--color-accent-tint)',
                    color: 'var(--color-accent)',
                    border: '1px solid var(--color-accent-border)',
                  }}
                >
                  <HardDrive size={11} strokeWidth={2.2} />
                </div>
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
                  isRootSection
                    ? 'text-[11px] font-bold tracking-wider uppercase'
                    : 'text-[11.5px] font-semibold tracking-tight'
                }`}
                style={{ color: 'var(--color-text)' }}
                title={node.name}
              >
                {node.name}
              </span>
            </div>

            <div className="flex items-center gap-1.5 flex-shrink-0">
              <span
                className="text-[10px] font-mono px-2 py-0.2 rounded-full font-semibold border"
                style={{
                  background: 'var(--color-overlay)',
                  borderColor: 'var(--color-border)',
                  color: 'var(--color-text-muted)',
                }}
              >
                {node.fileCount}
              </span>

              {/* Optional Delete Folder Button */}
              {onDeleteSource && isCustomOrUploaded && node.id !== 'user_ingested_files_root' && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    onDeleteSource(node)
                  }}
                  className="p-1 rounded text-[var(--color-text-muted)] hover:text-red-500 hover:bg-red-500/10 transition-fast cursor-pointer opacity-0 group-hover:opacity-100"
                  title={`Remove folder "${node.name}" from sources`}
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          </div>

          {/* Children container with subtle vertical connector line */}
          {isExpanded && (
            <div
              className="flex flex-col relative my-0.5 transition-base"
              style={{
                marginLeft: isRootSection ? '15px' : '11px',
                paddingLeft: '10px',
                borderLeft: '1px solid var(--color-border)',
              }}
            >
              {children.length > 0 ? (
                children
              ) : (
                <div
                  className="text-[10px] italic py-1 opacity-70"
                  style={{ paddingLeft: '8px', color: 'var(--color-text-muted)' }}
                >
                  (No matching documents in folder)
                </div>
              )}
            </div>
          )}
        </div>
      )
    }

    // File Node
    const isSelected = selectedId === node.id
    const isEnabled = !disabledNodeIds.has(node.id) && node.enabled !== false
    const fileType = getFileTypeLabel(node)
    const theme = getFileTypeTheme(fileType, node.category)

    return (
      <div
        key={node.id}
        onClick={() => onSelectSource && onSelectSource(node)}
        className="flex items-center justify-between py-1.5 px-2 rounded-md transition-fast group cursor-pointer my-0.5 hover:bg-[var(--color-surface-hover)]"
        style={{
          background: isSelected ? 'var(--color-surface-hover)' : 'transparent',
          borderLeft: isSelected ? '2px solid var(--color-accent)' : '2px solid transparent',
          opacity: isEnabled ? 1 : 0.55,
        }}
        title={`${node.name} • ${fileType} • ${node.size || ''} • ${node.fullPath || ''}`}
      >
        <div className="flex items-center gap-2 min-w-0 flex-1 pr-2">
          {/* Colored File Icon container matching token system */}
          <div
            className="w-5 h-5 rounded flex items-center justify-center flex-shrink-0 transition-fast shadow-xs"
            style={{
              background: theme.bg,
              color: theme.color,
              border: `1px solid ${theme.border}`,
            }}
          >
            {getFileIcon(node.type, node.category, fileType)}
          </div>

          <div className="flex flex-col min-w-0 flex-1 justify-center">
            {/* Clean File Name */}
            <span
              className={`truncate font-sans leading-snug tracking-tight ${
                compact ? 'text-[11px]' : 'text-[11.5px]'
              } ${isSelected ? 'font-semibold text-[var(--color-text)]' : 'font-medium text-[var(--color-text)]'}`}
            >
              {node.name}
            </span>

            {/* Faint file type badge and size */}
            {!compact && (
              <div className="flex items-center gap-1.5 text-[10px] font-sans mt-0.5 leading-none whitespace-nowrap overflow-hidden">
                <span
                  className="font-mono font-semibold text-[9px] uppercase tracking-wider px-1.5 py-0.2 rounded border shadow-xs"
                  style={{
                    color: theme.color,
                    background: theme.bg,
                    borderColor: theme.border,
                  }}
                >
                  {fileType}
                </span>
                {node.size && (
                  <>
                    <span className="text-[9px] text-[var(--color-text-faint)] opacity-40">·</span>
                    <span className="font-mono text-[10px] text-[var(--color-text-faint)]">
                      {node.size}
                    </span>
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Action Buttons: Delete & Scope Toggle Switch */}
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {onDeleteSource && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                onDeleteSource(node)
              }}
              className="p-1 rounded text-[var(--color-text-muted)] hover:text-red-500 hover:bg-red-500/10 transition-fast cursor-pointer opacity-70 hover:opacity-100 group-hover:opacity-100"
              title={`Delete "${node.name}" from knowledge base`}
            >
              <Trash2 size={12} />
            </button>
          )}

          {/* Polished Toggle Switch */}
          {onToggleSource && (
            <button
              type="button"
              role="switch"
              aria-checked={isEnabled}
              onClick={(e) => handleToggle(e, node)}
              className="w-7 h-4 rounded-full relative transition-all duration-200 cursor-pointer flex-shrink-0 focus:outline-none"
              style={{
                background: isEnabled ? 'var(--color-accent)' : 'var(--color-border-strong)',
                boxShadow: isEnabled ? '0 0 6px rgba(181, 101, 74, 0.25)' : 'none',
              }}
              title={isEnabled ? 'Included in retrieval scope' : 'Excluded from retrieval scope'}
            >
              <span
                className="absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all duration-200 shadow-xs pointer-events-none"
                style={{
                  left: isEnabled ? '14px' : '2px',
                }}
              />
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-0.5 py-1">
      {/* Quick Expand / Collapse All bar if multiple roots */}
      {tree.length > 0 && !compact && (
        <div className="flex items-center justify-between px-2 py-1 mb-1 text-[10px] text-[var(--color-text-muted)] border-b border-[var(--color-border)]">
          <span className="font-semibold uppercase tracking-wider text-[9px]">Corpus Structure</span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={expandAll}
              className="hover:text-[var(--color-text)] transition-fast cursor-pointer hover:underline"
            >
              Expand all
            </button>
            <span>•</span>
            <button
              type="button"
              onClick={collapseAll}
              className="hover:text-[var(--color-text)] transition-fast cursor-pointer hover:underline"
            >
              Collapse all
            </button>
          </div>
        </div>
      )}
      {tree.map((rootNode) => renderNode(rootNode, 0))}
    </div>
  )
}

