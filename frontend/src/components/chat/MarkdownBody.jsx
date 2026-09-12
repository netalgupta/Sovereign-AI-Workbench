/**
 * MarkdownBody.jsx — Full markdown renderer for assistant messages.
 *
 * Features (FRONTEND.md §3.1-3.3):
 *  1. react-markdown + remark-gfm: headings, bold, italic, tables, task lists
 *  2. Syntax highlighting: react-syntax-highlighter Prism, theme-aware
 *
 * Citations are NO LONGER rendered inline. They live in the thinking block's
 * "Sources used" section (SourcesUsedList component). This component receives
 * no citation data and renders plain markdown text only.
 */

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneLight, oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'

// ---------------------------------------------------------------------------
// Dark-mode detection — reads the data-theme attribute set by themeStore.js
// ---------------------------------------------------------------------------
function isDarkMode() {
  return document.documentElement.dataset.theme === 'dark'
}

// ---------------------------------------------------------------------------
// Styled table components — match design tokens, no raw browser table borders
// ---------------------------------------------------------------------------
const TableWrapper = ({ children }) => (
  <div style={{ overflowX: 'auto', margin: '12px 0' }}>
    <table
      style={{
        width: '100%',
        borderCollapse: 'collapse',
        fontSize: '12px',
        lineHeight: 1.5,
        borderRadius: 'var(--radius-md)',
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
      padding: '6px 12px',
      textAlign: 'left',
      fontWeight: 600,
      fontSize: '11px',
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
      padding: '5px 12px',
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

// ---------------------------------------------------------------------------
// MarkdownBody component
// ---------------------------------------------------------------------------

/**
 * @param {object} props
 * @param {string} props.content — full markdown string to render
 */
export function MarkdownBody({ content }) {
  const dark = isDarkMode()

  return (
    <div className="markdown-body text-xs leading-relaxed" style={{ color: 'var(--color-text)' }}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // ── Headings ──────────────────────────────────────────────────
          h1: ({ children }) => (
            <h1 className="text-base font-bold mt-4 mb-2" style={{ color: 'var(--color-text)' }}>
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-sm font-bold mt-3 mb-1.5" style={{ color: 'var(--color-text)' }}>
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3
              className="text-xs font-bold mt-2.5 mb-1 uppercase tracking-wide"
              style={{ color: 'var(--color-text)', letterSpacing: '0.04em' }}
            >
              {children}
            </h3>
          ),

          // ── Paragraph ─────────────────────────────────────────────────
          p: ({ children }) => (
            <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>
          ),

          // ── Bold / Italic ─────────────────────────────────────────────
          strong: ({ children }) => (
            <strong className="font-semibold" style={{ color: 'var(--color-text)' }}>
              {children}
            </strong>
          ),
          em: ({ children }) => (
            <em style={{ color: 'var(--color-text-muted)', fontStyle: 'italic' }}>{children}</em>
          ),

          // ── Blockquote ────────────────────────────────────────────────
          blockquote: ({ children }) => (
            <blockquote
              className="my-2 pl-3 py-1 text-xs leading-relaxed"
              style={{
                borderLeft: '3px solid var(--color-accent)',
                color: 'var(--color-text-muted)',
                background: 'var(--color-surface)',
                borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
              }}
            >
              {children}
            </blockquote>
          ),

          // ── Horizontal Rule ───────────────────────────────────────────
          hr: () => (
            <hr
              className="my-3"
              style={{ border: 'none', borderTop: '1px solid var(--color-border)' }}
            />
          ),

          // ── Lists ─────────────────────────────────────────────────────
          ul: ({ children }) => (
            <ul className="mb-2 pl-4 flex flex-col gap-0.5" style={{ listStyleType: 'disc' }}>
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="mb-2 pl-4 flex flex-col gap-0.5" style={{ listStyleType: 'decimal' }}>
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="leading-relaxed text-xs" style={{ color: 'var(--color-text)' }}>
              {children}
            </li>
          ),

          // ── Code ─────────────────────────────────────────────────────
          // Block code (language-*) → SyntaxHighlighter
          // Inline code or fenced without language → monospace span
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
                    margin: '8px 0',
                    borderRadius: 'var(--radius-md)',
                    fontSize: '11px',
                    border: '1px solid var(--color-code-border)',
                    background: dark ? '#1a1714' : 'var(--color-code-bg)',
                    padding: '12px 14px',
                    lineHeight: 1.6,
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
                className="font-mono text-[11px] px-1 py-0.5 rounded"
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

          // ── Tables ────────────────────────────────────────────────────
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
        {content}
      </ReactMarkdown>
    </div>
  )
}
