/**
 * MarkdownBody.jsx — Full markdown renderer for assistant messages.
 *
 * Features:
 *  1. react-markdown + remark-gfm: headings, bold, italic, tables, task lists
 *  2. Syntax highlighting: react-syntax-highlighter Prism, theme-aware
 *  3. Interactive Citation Chips: turns [1], [2], etc. into interactive expandable
 *     evidence cards beneath the sentence.
 */

import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { plainMath } from '../../lib/plainMath'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneLight, oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { CitationChip } from '../../integrations/citations/CitationChip'
import { CopyButton } from '../common/CopyButton'
import { SafeHtmlFrame } from '../common/SafeHtmlFrame'

function isDarkMode() {
  if (typeof document === 'undefined') return false
  return document.documentElement.dataset.theme === 'dark'
}

function processChildrenForCitations(children, citationsMap) {
  if (typeof children === 'string') {
    const parts = children.split(/(\[\d+\])/g)
    if (parts.length === 1) return children
    return parts.map((part, idx) => {
      const match = part.match(/^\[(\d+)\]$/)
      if (match) {
        const id = parseInt(match[1], 10)
        const cit = citationsMap[id]
        // A marker with no citation behind it stays plain text. It used to
        // become a chip for "Corpus Source [n]" with an invented passage.
        if (!cit) return part
        return <CitationChip key={idx} citation={cit} inlineIndex={id} />
      }
      return part
    })
  }

  if (Array.isArray(children)) {
    return children.map((child, i) => (
      <React.Fragment key={i}>
        {processChildrenForCitations(child, citationsMap)}
      </React.Fragment>
    ))
  }

  if (React.isValidElement(children) && children.props?.children) {
    return React.cloneElement(children, {
      children: processChildrenForCitations(children.props.children, citationsMap),
    })
  }

  return children
}

// A table copies as tab-separated rows: it pastes into Excel as cells.
function tableAsTsv(table) {
  if (!table) return ''
  return [...table.querySelectorAll('tr')]
    .map((tr) => [...tr.querySelectorAll('th,td')].map((c) => c.innerText.replace(/\s+/g, ' ').trim()).join('\t'))
    .join('\n')
}

// Languages a browser can show as a page. Previewed in SafeHtmlFrame: no
// network, no access to this app.
const PREVIEWABLE = new Set(['html', 'htm', 'svg', 'xhtml'])

function CodeBlock({ language, source, dark, props }) {
  const canPreview = PREVIEWABLE.has(language.toLowerCase())
  const [view, setView] = React.useState('code')
  return (
    <div className="group relative" style={{ margin: '16px 0' }}>
      <div
        className="flex items-center justify-between gap-2 px-3 py-1 text-[10.5px] font-mono uppercase tracking-wider"
        style={{
          color: 'var(--color-text-muted)',
          background: dark ? '#221e1a' : 'var(--color-overlay)',
          border: '1px solid var(--color-code-border)',
          borderBottom: 'none',
          borderRadius: 'var(--radius-lg) var(--radius-lg) 0 0',
        }}
      >
        <span>{language === 'text' ? 'plain text' : language}</span>
        <span className="flex items-center gap-1">
          {canPreview && (
            <span className="inline-flex rounded-md overflow-hidden border normal-case tracking-normal" style={{ borderColor: 'var(--color-border)' }}>
              {[['preview', 'Preview'], ['code', 'Code']].map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setView(id)}
                  aria-pressed={view === id}
                  className="px-2 py-0.5 text-[11px] font-medium cursor-pointer"
                  style={{
                    background: view === id ? 'var(--color-accent-tint)' : 'transparent',
                    color: view === id ? 'var(--color-accent)' : 'var(--color-text-muted)',
                  }}
                >
                  {label}
                </button>
              ))}
            </span>
          )}
          <CopyButton text={source} label="Copy" title="Copy code" size={12} />
        </span>
      </div>
      {canPreview && view === 'preview' ? (
        <div
          className="overflow-hidden"
          style={{ border: '1px solid var(--color-code-border)', borderRadius: '0 0 var(--radius-lg) var(--radius-lg)', resize: 'vertical', height: 380, minHeight: 160 }}
        >
          <SafeHtmlFrame
            html={language.toLowerCase() === 'svg' && !/<html/i.test(source) ? `<body style="margin:0;display:grid;place-items:center;min-height:100vh">${source}</body>` : source}
            title="Preview of the HTML in this answer"
            height="100%"
          />
        </div>
      ) : (
      <SyntaxHighlighter
        style={dark ? oneDark : oneLight}
        language={language}
        PreTag="div"
        customStyle={{
          margin: 0,
          borderRadius: '0 0 var(--radius-lg) var(--radius-lg)',
          fontSize: '12px',
          border: '1px solid var(--color-code-border)',
          background: dark ? '#1a1714' : 'var(--color-code-bg)',
          padding: '16px 18px',
          lineHeight: 1.68,
          boxShadow: dark ? '0 2px 8px -2px rgba(0,0,0,0.5)' : '0 1px 4px -1px rgba(42,39,36,0.08)',
        }}
        codeTagProps={{ style: { fontFamily: 'var(--font-mono)' } }}
        {...props}
      >
        {source}
      </SyntaxHighlighter>
      )}
    </div>
  )
}

function TableWrapper({ children }) {
  const ref = React.useRef(null)
  return (
  <div className="group relative" style={{ margin: '16px 0' }}>
    <div className="absolute -top-3 right-1 z-10 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
      <CopyButton text={() => tableAsTsv(ref.current)} label="Copy table" title="Copy as rows and columns (pastes into Excel)"
        style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }} />
    </div>
  <div style={{ overflowX: 'auto' }}>
    <table
      ref={ref}
      style={{
        width: '100%',
        borderCollapse: 'collapse',
        fontSize: '12.5px',
        lineHeight: 1.6,
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden',
        border: '1px solid var(--color-border)',
      }}
    >
      {children}
    </table>
  </div>
  </div>
  )
}

const Th = ({ children }) => (
  <th
    style={{
      padding: '9px 16px',
      textAlign: 'left',
      fontWeight: 600,
      fontSize: '11.5px',
      letterSpacing: '0.02em',
      background: 'var(--color-surface)',
      color: 'var(--color-text)',
      borderBottom: '1px solid var(--color-border)',
      whiteSpace: 'nowrap',
    }}
  >
    {children}
  </th>
)

const Td = ({ children }) => (
  <td
    style={{
      padding: '8px 16px',
      color: 'var(--color-text)',
      borderBottom: '1px solid var(--color-border)',
      verticalAlign: 'top',
    }}
  >
    {children}
  </td>
)

const Tr = ({ children, ...props }) => (
  <tr
    {...props}
    style={{
      background: 'transparent',
      transition: 'background var(--transition-fast)',
    }}
    onMouseEnter={(e) => {
      e.currentTarget.style.background = 'var(--color-surface-hover)'
    }}
    onMouseLeave={(e) => {
      e.currentTarget.style.background = 'transparent'
    }}
  >
    {children}
  </tr>
)

/**
 * @param {object} props
 * @param {string} props.content — full markdown string to render
 * @param {Array}  [props.citations] — optional list of citation objects
 */
export function MarkdownBody({ content, citations = [] }) {
  const dark = isDarkMode()

  // Map citations by 1-based index or id. Keyed on the content, not the
  // array: callers pass `message.citations || []`, a new array every render.
  const citationsKey = JSON.stringify(Array.isArray(citations) ? citations : [])
  const citationsMap = React.useMemo(() => {
    const map = {}
    JSON.parse(citationsKey).forEach((c, idx) => {
      map[c.id ?? idx + 1] = c
    })
    return map
  }, [citationsKey])
  const components = useMarkdownComponents(citationsMap, dark)

  return (
    <div
      className="markdown-body text-[13.5px] leading-[1.72] tracking-[-0.005em] select-text"
      style={{ color: 'var(--color-text)' }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={components}
      >
        {plainMath(content)}
      </ReactMarkdown>
    </div>
  )
}

// Built inline, this map made every paragraph a NEW component type on each
// render, so React remounted it -- and a citation chip lost its open state
// the moment the chat re-rendered (a timer ticking was enough): clicking
// [1] appeared to do nothing. Memoised on what it actually depends on.
function useMarkdownComponents(citationsMap, dark) {
  return React.useMemo(() => ({
          h1: ({ children }) => (
            <h1 className="text-lg font-bold mt-5 mb-2.5 leading-snug" style={{ color: 'var(--color-text)' }}>
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-base font-bold mt-4 mb-2 leading-snug" style={{ color: 'var(--color-text)' }}>
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3
              className="text-xs font-bold mt-3.5 mb-1.5 uppercase tracking-wider leading-snug"
              style={{ color: 'var(--color-text)', letterSpacing: '0.04em' }}
            >
              {children}
            </h3>
          ),

          // Paragraph rendered as div to allow block-level citation expansion cards
          p: ({ children }) => (
            <div className="mb-3.5 last:mb-0 leading-[1.72]">
              {processChildrenForCitations(children, citationsMap)}
            </div>
          ),

          strong: ({ children }) => (
            <strong className="font-semibold" style={{ color: 'var(--color-text)' }}>
              {children}
            </strong>
          ),
          em: ({ children }) => (
            <em style={{ color: 'var(--color-text-muted)', fontStyle: 'italic' }}>{children}</em>
          ),

          blockquote: ({ children }) => (
            <blockquote
              className="my-3.5 pl-4 py-2.5 text-[13px] leading-relaxed"
              style={{
                borderLeft: '3px solid var(--color-accent)',
                color: 'var(--color-text-muted)',
                background: 'var(--color-surface)',
                borderRadius: '0 var(--radius-md) var(--radius-md) 0',
                boxShadow: 'var(--shadow-xs)',
              }}
            >
              {children}
            </blockquote>
          ),

          hr: () => (
            <hr
              className="my-4"
              style={{ border: 'none', borderTop: '1px solid var(--color-border)' }}
            />
          ),

          ul: ({ children }) => (
            <ul className="mb-3.5 pl-5 flex flex-col gap-2" style={{ listStyleType: 'disc' }}>
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="mb-3.5 pl-5 flex flex-col gap-2" style={{ listStyleType: 'decimal' }}>
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="leading-[1.72] text-[13.5px]" style={{ color: 'var(--color-text)' }}>
              {processChildrenForCitations(children, citationsMap)}
            </li>
          ),

          code({ className, children, node, ...props }) {
            const match = /language-(\w+)/.exec(className || '')
            const source = String(children).replace(/\n$/, '')
            // A fenced block WITHOUT a language used to fall through to the
            // inline style below -- a flat, cramped box. Multi-line content
            // is a block, whatever its language.
            const isBlock = Boolean(match) || source.includes('\n')
            const language = match ? match[1] : isBlock ? 'text' : null

            if (language) {
              return <CodeBlock language={language} source={source} dark={dark} props={props} />
            }

            return (
              <code
                className="font-mono text-xs px-1.5 py-0.5 rounded"
                style={{
                  background: 'var(--color-overlay)',
                  color: 'var(--color-accent)',
                  border: '1px solid var(--color-border)',
                  fontFamily: 'var(--font-mono)',
                }}
                {...props}
              >
                {children}
              </code>
            )
          },

          table: ({ children }) => <TableWrapper>{children}</TableWrapper>,
          thead: ({ children }) => (
            <thead style={{ background: 'var(--color-surface)' }}>{children}</thead>
          ),
          tbody: ({ children }) => <tbody>{children}</tbody>,
          tr: Tr,
          th: Th,
          td: Td,
  }), [citationsMap, dark])
}
