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
        const cit = citationsMap[id] || {
          id,
          doc: `Corpus Source [${id}]`,
          section: 'Retrieved excerpt',
          passage: `Retrieved grounding passage for claim [${id}].`,
        }
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

const TableWrapper = ({ children }) => (
  <div style={{ overflowX: 'auto', margin: '16px 0' }}>
    <table
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
)

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

  // Map citations by 1-based index or id
  const citationsMap = React.useMemo(() => {
    const map = {}
    if (Array.isArray(citations)) {
      citations.forEach((c, idx) => {
        const id = c.id ?? idx + 1
        map[id] = c
      })
    }
    return map
  }, [citations])

  return (
    <div
      className="markdown-body text-[13.5px] leading-[1.72] tracking-[-0.005em] select-text"
      style={{ color: 'var(--color-text)' }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
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

          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '')
            const language = match ? match[1] : null

            if (language) {
              return (
                <SyntaxHighlighter
                  style={dark ? oneDark : oneLight}
                  language={language}
                  PreTag="div"
                  customStyle={{
                    margin: '16px 0',
                    borderRadius: 'var(--radius-lg)',
                    fontSize: '12px',
                    border: '1px solid var(--color-code-border)',
                    background: dark ? '#1a1714' : 'var(--color-code-bg)',
                    padding: '16px 18px',
                    lineHeight: 1.68,
                    boxShadow: dark
                      ? '0 2px 8px -2px rgba(0,0,0,0.5)'
                      : '0 1px 4px -1px rgba(42,39,36,0.08)',
                  }}
                  codeTagProps={{ style: { fontFamily: 'var(--font-mono)' } }}
                  {...props}
                >
                  {String(children).replace(/\n$/, '')}
                </SyntaxHighlighter>
              )
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
        }}
      >
        {plainMath(content)}
      </ReactMarkdown>
    </div>
  )
}
