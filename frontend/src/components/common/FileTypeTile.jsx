import React from 'react'
import {
  FileText,
  Image as ImageIcon,
  Database,
  Plug,
  FileCode,
  FileSpreadsheet,
  Check,
  Loader2,
} from 'lucide-react'

/**
 * Standard file-type theme tokens — consistent across Sources Rail, Sources Page,
 * Modals, and Citations.
 */
export function getFileTypeInfo(name = '', type = '', category = '') {
  let ext = ''
  const dotIdx = name.lastIndexOf('.')
  if (dotIdx !== -1) {
    ext = name.slice(dotIdx + 1).toUpperCase()
  } else if (type) {
    ext = String(type).toUpperCase()
  }

  let label = ext || 'FILE'
  let IconComponent = FileText
  let color = '#94a3b8'
  let bg = 'rgba(148, 163, 184, 0.12)'
  let border = 'rgba(148, 163, 184, 0.25)'

  if (label === 'DOCX' || label === 'DOC') {
    label = 'DOCX'
    IconComponent = FileText
    color = '#60a5fa' // soft sky blue
    bg = 'rgba(96, 165, 250, 0.12)'
    border = 'rgba(96, 165, 250, 0.28)'
  } else if (label === 'PDF') {
    IconComponent = FileText
    color = '#f87171' // soft coral red
    bg = 'rgba(248, 113, 113, 0.12)'
    border = 'rgba(248, 113, 113, 0.28)'
  } else if (label === 'XLSX' || label === 'XLS') {
    label = 'XLSX'
    IconComponent = FileSpreadsheet
    color = '#34d399' // soft emerald green
    bg = 'rgba(52, 211, 153, 0.12)'
    border = 'rgba(52, 211, 153, 0.28)'
  } else if (label === 'CSV' || category === 'data') {
    label = ext === 'CSV' ? 'CSV' : 'DATA'
    IconComponent = Database
    color = '#34d399'
    bg = 'rgba(52, 211, 153, 0.12)'
    border = 'rgba(52, 211, 153, 0.28)'
  } else if (label === 'PNG' || label === 'JPG' || label === 'JPEG' || category === 'charts') {
    if (name.toLowerCase().includes('checklist')) label = 'SCAN'
    else if (name.toLowerCase().includes('pid')) label = 'P&ID'
    else label = ext || 'PNG'
    IconComponent = ImageIcon
    color = label === 'P&ID' ? '#fbbf24' : '#c084fc' // amber or lavender
    bg = label === 'P&ID' ? 'rgba(251, 191, 36, 0.12)' : 'rgba(192, 132, 252, 0.12)'
    border = label === 'P&ID' ? 'rgba(251, 191, 36, 0.28)' : 'rgba(192, 132, 252, 0.28)'
  } else if (label === 'JSON') {
    IconComponent = FileCode
    color = '#fb923c' // soft orange
    bg = 'rgba(251, 146, 60, 0.12)'
    border = 'rgba(251, 146, 60, 0.28)'
  } else if (label === 'API' || category === 'apis' || name.includes('API')) {
    label = 'API'
    IconComponent = Plug
    color = '#38bdf8' // soft cyan
    bg = 'rgba(56, 189, 248, 0.12)'
    border = 'rgba(56, 189, 248, 0.28)'
  } else if (label === 'MD' || label === 'MARKDOWN' || label === 'TXT') {
    label = ext || 'TXT'
    IconComponent = FileText
    color = '#cbd5e1'
    bg = 'rgba(203, 213, 225, 0.12)'
    border = 'rgba(203, 213, 225, 0.25)'
  }

  return { label, IconComponent, color, bg, border }
}

/**
 * Standardized square file icon tile with consistent padding, radius, and elevation.
 * Sizes:
 * - 'xs': 20x20px, rounded (citations)
 * - 'sm': 24x24px, rounded-md (sources tree rows, list items)
 * - 'md': 32x32px, rounded-lg (modals, compact cards)
 * - 'lg': 44x44px, rounded-xl (Sources page detail header)
 */
export function FileTypeTile({
  name = '',
  type = '',
  category = '',
  size = 'sm',
  isProcessing = false,
  isIndexed = false,
  showLabelOnLarge = true,
  className = '',
}) {
  const { label, IconComponent, color, bg, border } = getFileTypeInfo(name, type, category)

  // Size mapping
  let dimensions = 'w-6 h-6 rounded-md'
  let iconSize = 12

  if (size === 'xs') {
    dimensions = 'w-5 h-5 rounded'
    iconSize = 11
  } else if (size === 'md') {
    dimensions = 'w-8 h-8 rounded-lg'
    iconSize = 16
  } else if (size === 'lg') {
    dimensions = 'w-11 h-11 rounded-xl'
    iconSize = 20
  }

  if (isProcessing) {
    return (
      <div
        className={`${dimensions} flex items-center justify-center flex-shrink-0 transition-fast shadow-xs animate-pulse ${className}`}
        style={{
          background: 'var(--color-accent-tint)',
          color: 'var(--color-accent)',
          border: '1px solid var(--color-accent-border)',
        }}
        title="Processing document..."
      >
        <Loader2 size={iconSize} className="animate-spin" />
      </div>
    )
  }

  if (isIndexed) {
    return (
      <div
        className={`${dimensions} flex items-center justify-center flex-shrink-0 transition-all duration-300 shadow-xs animate-fade-in ${className}`}
        style={{
          background: 'rgba(52, 211, 153, 0.15)',
          color: '#10b981',
          border: '1px solid rgba(52, 211, 153, 0.35)',
        }}
        title="Indexed into vector space"
      >
        <Check size={iconSize} strokeWidth={2.6} />
      </div>
    )
  }

  return (
    <div
      className={`${dimensions} flex flex-col items-center justify-center flex-shrink-0 transition-fast shadow-xs select-none ${className}`}
      style={{
        background: bg,
        color: color,
        border: `1px solid ${border}`,
      }}
      title={`${name || label} (${label})`}
    >
      <IconComponent size={size === 'lg' ? 18 : iconSize} strokeWidth={1.9} />
      {size === 'lg' && showLabelOnLarge && (
        <span className="text-[8.5px] font-mono font-bold tracking-tight uppercase leading-none mt-0.5">
          {label.slice(0, 4)}
        </span>
      )}
    </div>
  )
}
