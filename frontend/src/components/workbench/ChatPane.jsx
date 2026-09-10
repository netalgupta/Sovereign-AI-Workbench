import { useState } from 'react'
import {
  MoreHorizontal,
  Paperclip,
  Globe,
  Send,
  Search,
  BarChart2,
  CheckCircle2,
  ChevronDown,
  CheckCheck,
} from 'lucide-react'
import { useChatStore } from '../../store/chatStore'
import { sendMessage } from '../../lib/api'

export function ChatPane() {
  const messages = useChatStore((s) => s.messages)
  const addMessage = useChatStore((s) => s.addMessage)
  const sessionId = useChatStore((s) => s.sessionId)
  const [draft, setDraft] = useState('')
  const [isPending, setIsPending] = useState(false)

  const handleSend = async () => {
    if (!draft.trim() || isPending) return
    const text = draft.trim()
    setDraft('')
    addMessage('user', text)
    setIsPending(true)
    try {
      const res = await sendMessage(text, sessionId)
      addMessage('assistant', res.reply)
    } finally {
      setIsPending(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden p-3 min-w-0" style={{ background: 'var(--color-bg)' }}>
      {/* ── Elevated Chat Card (Matches Reference Image) ──────────────── */}
      <div
        className="flex-1 rounded-2xl flex flex-col overflow-hidden relative shadow-xs"
        style={{
          background: '#ECE4DB',
          border: '1px solid #DFD7CE',
        }}
      >
        {/* Chat Card Header */}
        <div
          className="flex items-start justify-between px-6 pt-4 pb-3 flex-shrink-0 select-none"
          style={{ borderBottom: '1px solid rgba(42, 39, 36, 0.05)' }}
        >
          <div className="flex flex-col">
            <h2
              className="text-base font-bold tracking-tight leading-tight"
              style={{ color: 'var(--color-text)' }}
            >
              Chat
            </h2>
            <span
              className="text-xs italic leading-tight mt-0.5"
              style={{ color: 'var(--color-text-muted)' }}
            >
              Ask. Analyze. Act.
            </span>
          </div>

          <button
            type="button"
            className="w-7 h-7 rounded-lg flex items-center justify-center transition-fast hover:bg-[#E0D7CE] text-[var(--color-text-muted)]"
            title="Chat options"
          >
            <MoreHorizontal size={16} strokeWidth={2} />
          </button>
        </div>

        {/* Chat Message Stream */}
        <div className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-4">
          {/* User Message 1 */}
          <div className="flex justify-end">
            <div
              className="rounded-2xl px-4 py-3 text-xs leading-relaxed max-w-[72%] shadow-xs"
              style={{
                background: '#DFCAC0',
                border: '1px solid #D2B7AC',
                borderBottomRightRadius: '6px',
                color: 'var(--color-text)',
              }}
            >
              <div>What are the key risks in increasing feed rate in the HCU beyond 110%?</div>
              <div className="flex items-center justify-end gap-1 mt-1 text-[10px]" style={{ color: 'var(--color-accent)' }}>
                <span>10:14 AM</span>
                <CheckCheck size={13} strokeWidth={2.2} />
              </div>
            </div>
          </div>

          {/* Assistant Response 1 */}
          <div className="flex flex-col gap-3 max-w-[86%] text-xs leading-relaxed" style={{ color: 'var(--color-text)' }}>
            <p>
              Increasing the feed rate in the HCU beyond 110% can lead to several operational and safety risks,
              including reduced catalyst life, higher temperatures, and potential off-spec products.{' '}
              <span className="inline-flex gap-1 ml-1 select-none">
                <span className="px-1.5 py-0.2 rounded border bg-white/70 text-[10px] font-mono border-stone-300">1</span>
                <span className="px-1.5 py-0.2 rounded border bg-white/70 text-[10px] font-mono border-stone-300">2</span>
                <span className="px-1.5 py-0.2 rounded border bg-white/70 text-[10px] font-mono border-stone-300">3</span>
              </span>
              .
            </p>

            {/* Tool-Call Event 1: Searching documents */}
            <div
              className="rounded-xl p-3 flex items-center justify-between transition-fast shadow-xs"
              style={{
                background: '#E2D9CF',
                border: '1px solid #D7CDC2',
              }}
            >
              <div className="flex items-center gap-3">
                <div
                  className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
                  style={{ background: '#D3C9BE', color: 'var(--color-text)' }}
                >
                  <Search size={15} strokeWidth={2} />
                </div>
                <div className="flex flex-col">
                  <span className="text-xs font-bold leading-tight" style={{ color: 'var(--color-text)' }}>
                    Searching documents
                  </span>
                  <span className="text-[11px] leading-tight mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                    Scanning 3 sources...
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <CheckCircle2 size={16} strokeWidth={2.2} style={{ color: '#2D7A4F' }} />
                <ChevronDown size={14} strokeWidth={2} style={{ color: 'var(--color-text-muted)' }} />
              </div>
            </div>

            {/* Bullet points based on manual */}
            <div className="flex flex-col gap-1.5">
              <span className="font-semibold">Based on the operator manual:</span>
              <div className="flex flex-col gap-1 pl-2">
                <div>1. Elevated reactor temperatures and potential catalyst thermal runaway</div>
                <div>2. Increased H₂ consumption leading to makeup compressor capacity limits</div>
                <div>3. Higher chance of downstream fractionation column flooding</div>
              </div>
            </div>

            {/* Monospace code / rule check block */}
            <div
              className="rounded-xl p-3 font-mono text-xs overflow-x-auto shadow-xs"
              style={{
                background: '#DFD6CB',
                border: '1px solid #D4C9BC',
                color: '#2A2724',
              }}
            >
              <div className="flex gap-4">
                <span className="text-stone-400 select-none text-right w-3">1</span>
                <span>if feed_rate &gt; 1.10 * design_capacity:</span>
              </div>
              <div className="flex gap-4">
                <span className="text-stone-400 select-none text-right w-3">2</span>
                <span className="pl-4">alert("High risk: exceeds design threshold")</span>
              </div>
              <div className="flex gap-4">
                <span className="text-stone-400 select-none text-right w-3">3</span>
                <span className="pl-4">suggest_mitigation(cool_quench=True)</span>
              </div>
            </div>
          </div>

          {/* User Message 2 */}
          <div className="flex justify-end mt-1">
            <div
              className="rounded-2xl px-4 py-3 text-xs leading-relaxed max-w-[72%] shadow-xs"
              style={{
                background: '#DFCAC0',
                border: '1px solid #D2B7AC',
                borderBottomRightRadius: '6px',
                color: 'var(--color-text)',
              }}
            >
              <div>Can you check the latest trend data for reactor inlet temp?</div>
              <div className="flex items-center justify-end gap-1 mt-1 text-[10px]" style={{ color: 'var(--color-accent)' }}>
                <span>10:18 AM</span>
                <CheckCheck size={13} strokeWidth={2.2} />
              </div>
            </div>
          </div>

          {/* Tool-Call Event 2: Querying time series data */}
          <div className="max-w-[86%]">
            <div
              className="rounded-xl p-3 flex items-center justify-between transition-fast shadow-xs"
              style={{
                background: '#E2D9CF',
                border: '1px solid #D7CDC2',
              }}
            >
              <div className="flex items-center gap-3">
                <div
                  className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
                  style={{ background: '#D3C9BE', color: 'var(--color-text)' }}
                >
                  <BarChart2 size={15} strokeWidth={2} />
                </div>
                <div className="flex flex-col">
                  <span className="text-xs font-bold leading-tight" style={{ color: 'var(--color-text)' }}>
                    Querying time series data
                  </span>
                  <span className="text-[11px] leading-tight mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                    Fetching from Historical_Trend_Data.csv...
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <CheckCircle2 size={16} strokeWidth={2.2} style={{ color: '#2D7A4F' }} />
                <ChevronDown size={14} strokeWidth={2} style={{ color: 'var(--color-text-muted)' }} />
              </div>
            </div>
          </div>

          {/* Assistant Response 2 */}
          <div className="max-w-[86%] text-xs leading-relaxed" style={{ color: 'var(--color-text)' }}>
            <p>
              The current reactor inlet temperature is <span className="font-semibold">382°C</span>, which is within the normal operating range (360–400°C){' '}
              <span className="inline-flex px-1.5 py-0.2 rounded border bg-white/70 text-[10px] font-mono border-stone-300 select-none">
                4
              </span>
              .
            </p>
          </div>

          {/* Dynamic Messages sent by the user during interaction */}
          {messages.map((m) => (
            <div
              key={m.id}
              className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className="rounded-2xl px-4 py-3 text-xs leading-relaxed max-w-[76%] shadow-xs"
                style={{
                  background: m.role === 'user' ? '#DFCAC0' : '#E8DFD5',
                  border: m.role === 'user' ? '1px solid #D2B7AC' : '1px solid #DBD1C5',
                  borderBottomRightRadius: m.role === 'user' ? '6px' : '16px',
                  borderBottomLeftRadius: m.role === 'assistant' ? '6px' : '16px',
                  color: 'var(--color-text)',
                }}
              >
                {m.content}
              </div>
            </div>
          ))}
        </div>

        {/* ── Chat Composer Floating at Bottom (Matches Reference) ───────── */}
        <div className="p-4 pt-1 flex-shrink-0">
          <div
            className="flex items-center gap-2 px-3.5 py-2.5 rounded-xl transition-fast"
            style={{
              background: '#FFFFFF',
              border: '1px solid #DFD7CE',
              boxShadow: '0 2px 8px rgba(42, 39, 36, 0.05)',
            }}
          >
            {/* Left buttons: Paperclip + Globe */}
            <button
              type="button"
              className="w-7 h-7 rounded-lg flex items-center justify-center transition-fast hover:bg-[#F5EFEB] text-[var(--color-text-muted)]"
              title="Attach document (coming Day 3-4)"
            >
              <Paperclip size={15} strokeWidth={2} />
            </button>
            <button
              type="button"
              className="w-7 h-7 rounded-lg flex items-center justify-center transition-fast hover:bg-[#F5EFEB] text-[var(--color-text-muted)]"
              title="Grounded live sources"
            >
              <Globe size={15} strokeWidth={2} />
            </button>

            {/* Input field */}
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a follow-up..."
              className="flex-1 bg-transparent text-xs outline-none placeholder:text-[#A39B92]"
              style={{ color: 'var(--color-text)' }}
              disabled={isPending}
            />

            {/* Solid Terracotta Send Button */}
            <button
              type="button"
              onClick={handleSend}
              disabled={!draft.trim() || isPending}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-white transition-fast shadow-xs cursor-pointer flex-shrink-0"
              style={{
                background: 'var(--color-accent)',
                opacity: draft.trim() ? 1 : 0.85,
              }}
              title="Send message"
            >
              <Send size={14} strokeWidth={2} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
