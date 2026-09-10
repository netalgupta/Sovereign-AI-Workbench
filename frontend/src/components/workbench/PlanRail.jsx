import { MoreHorizontal, Check, Signal } from 'lucide-react'

export function PlanRail() {
  const STEPS = [
    {
      num: 1,
      title: '1. Understand query',
      desc: 'Parse intent and extract entities',
      status: 'done', // green checkmark
    },
    {
      num: 2,
      title: '2. Retrieve information',
      desc: 'Search relevant sources',
      status: 'active', // amber pulsing ring
    },
    {
      num: 3,
      title: '3. Analyze & reason',
      desc: 'Synthesize findings',
      status: 'pending',
    },
    {
      num: 4,
      title: '4. Generate response',
      desc: 'Draft answer with citations',
      status: 'pending',
    },
    {
      num: 5,
      title: '5. Validate & finalize',
      desc: 'Safety and accuracy checks',
      status: 'pending',
    },
  ]

  return (
    <aside
      className="flex flex-col h-full flex-shrink-0 select-none overflow-hidden relative"
      style={{
        width: 305,
        background: 'var(--color-bg)',
        borderLeft: '1px solid rgba(42, 39, 36, 0.06)',
      }}
      aria-label="Plan rail"
    >
      {/* ── Header: Title + Subtext + Overflow Menu ──────────────────── */}
      <div className="flex items-start justify-between px-5 pt-4 pb-3 flex-shrink-0">
        <div className="flex flex-col">
          <h2
            className="text-base font-bold tracking-tight leading-tight"
            style={{ color: 'var(--color-text)' }}
          >
            Plan
          </h2>
          <span
            className="text-[11px] leading-tight mt-0.5"
            style={{ color: 'var(--color-text-muted)' }}
          >
            Agent's current task plan
          </span>
        </div>
        <button
          type="button"
          className="w-7 h-7 rounded-lg flex items-center justify-center transition-fast hover:bg-[#EDE5DC] text-[var(--color-text-muted)]"
          title="Plan options"
        >
          <MoreHorizontal size={15} strokeWidth={2} />
        </button>
      </div>

      {/* ── Connected Vertical Timeline (Reference Design) ──────────── */}
      <div className="flex-1 overflow-y-auto px-5 py-2 z-10">
        <div className="relative flex flex-col gap-2">
          {STEPS.map((step, idx) => {
            const isLast = idx === STEPS.length - 1
            const isDone = step.status === 'done'
            const isActive = step.status === 'active'

            return (
              <div key={step.num} className="relative flex items-start gap-3.5">
                {/* Timeline node + connector line */}
                <div className="flex flex-col items-center flex-shrink-0 mt-0.5 relative">
                  {/* Node icon */}
                  {isDone ? (
                    <div
                      className="w-5 h-5 rounded-full flex items-center justify-center shadow-xs"
                      style={{ background: '#2D7A4F', color: 'white' }}
                    >
                      <Check size={12} strokeWidth={2.5} />
                    </div>
                  ) : isActive ? (
                    <div className="relative flex items-center justify-center w-5 h-5">
                      <span
                        className="absolute w-5 h-5 rounded-full animate-ping opacity-30"
                        style={{ background: '#C67D34' }}
                      />
                      <div
                        className="w-4 h-4 rounded-full border-2 border-white flex items-center justify-center shadow-xs"
                        style={{ background: '#C67D34' }}
                      >
                        <div className="w-1.5 h-1.5 rounded-full bg-white" />
                      </div>
                    </div>
                  ) : (
                    <div
                      className="w-4 h-4 rounded-full border border-[var(--color-border-strong)] flex items-center justify-center mt-0.5"
                      style={{ background: 'var(--color-overlay)' }}
                    >
                      <div
                        className="w-1.5 h-1.5 rounded-full"
                        style={{ background: 'var(--color-text-faint)' }}
                      />
                    </div>
                  )}

                  {/* Vertical line connecting to next step */}
                  {!isLast && (
                    <div
                      className="w-[1.5px] my-1"
                      style={{
                        height: isActive ? 34 : 26,
                        background: isDone
                          ? '#2D7A4F'
                          : isActive
                          ? '#DDB08A'
                          : 'rgba(42, 39, 36, 0.12)',
                      }}
                    />
                  )}
                </div>

                {/* Step content card */}
                <div
                  className={`flex-1 transition-fast ${
                    isActive
                      ? 'p-2.5 rounded-xl border -mt-1'
                      : 'pb-1'
                  }`}
                  style={{
                    background: isActive ? '#FAF3EC' : 'transparent',
                    borderColor: isActive ? '#E2B994' : 'transparent',
                    boxShadow: isActive ? 'var(--shadow-xs)' : 'none',
                  }}
                >
                  <div
                    className="text-xs font-bold leading-tight"
                    style={{ color: 'var(--color-text)' }}
                  >
                    {step.title}
                  </div>
                  <div
                    className="text-[11px] leading-tight mt-0.5"
                    style={{ color: 'var(--color-text-muted)' }}
                  >
                    {step.desc}
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* ── Network Monitor Section ────────────────────────────────── */}
        <div className="mt-7 flex flex-col gap-2.5">
          <span
            className="text-xs font-bold tracking-tight"
            style={{ color: 'var(--color-text)' }}
          >
            Network Monitor
          </span>

          {/* Operational row with stair-step signal bars */}
          <div
            className="flex items-center justify-between p-2.5 rounded-xl text-xs"
            style={{
              background: 'white',
              border: '1px solid var(--color-border)',
              boxShadow: 'var(--shadow-xs)',
            }}
          >
            <div className="flex items-center gap-2">
              <span
                className="w-2 h-2 rounded-full"
                style={{ background: '#2D7A4F' }}
              />
              <span className="font-medium text-xs" style={{ color: 'var(--color-text)' }}>
                All systems operational
              </span>
            </div>
            {/* 4 stair-step signal strength bars */}
            <div className="flex items-end gap-[2px] h-3.5" title="Signal: Optimal / Offline Localhost">
              <span className="w-[3px] h-1.5 rounded-xs" style={{ background: '#2D7A4F' }} />
              <span className="w-[3px] h-2 rounded-xs" style={{ background: '#2D7A4F' }} />
              <span className="w-[3px] h-2.5 rounded-xs" style={{ background: '#2D7A4F' }} />
              <span className="w-[3px] h-3.5 rounded-xs" style={{ background: '#2D7A4F' }} />
            </div>
          </div>

          {/* Status quote card */}
          <div
            className="p-3 rounded-xl text-xs leading-relaxed"
            style={{
              background: 'var(--color-surface)',
              border: '1px solid rgba(42, 39, 36, 0.05)',
              color: 'var(--color-text-muted)',
              fontStyle: 'italic',
            }}
          >
            "Augmenting engineering expertise, responsibly."
          </div>
        </div>
      </div>

      {/* ── Subtle Refinery Silhouette Watermark (Bottom Right) ────── */}
      <div
        className="absolute bottom-0 right-0 pointer-events-none select-none flex items-end justify-end p-2 gap-2"
        style={{ opacity: 0.14 }}
        aria-hidden="true"
      >
        <div
          className="flex flex-col text-[8px] font-mono leading-tight tracking-wider uppercase"
          style={{ color: 'var(--color-text)' }}
        >
          <span>People</span>
          <span>Process</span>
          <span>Progress</span>
        </div>

        {/* Industrial refinery cracking towers & piping silhouette */}
        <svg
          width="110"
          height="80"
          viewBox="0 0 110 80"
          fill="none"
          stroke="var(--color-text)"
          strokeWidth="1.25"
        >
          {/* Main crude column */}
          <rect x="15" y="10" width="16" height="68" rx="2" fill="currentColor" fillOpacity="0.1" />
          <line x1="10" y1="20" x2="36" y2="20" />
          <line x1="10" y1="35" x2="36" y2="35" />
          <line x1="10" y1="50" x2="36" y2="50" />
          <line x1="10" y1="65" x2="36" y2="65" />
          {/* Flare / dome cap */}
          <path d="M15 10 C15 4, 31 4, 31 10" />
          <line x1="23" y1="4" x2="23" y2="0" />

          {/* Secondary reactor / cracker */}
          <rect x="42" y="25" width="20" height="53" rx="3" fill="currentColor" fillOpacity="0.1" />
          <path d="M42 25 C42 18, 62 18, 62 25" />
          <line x1="42" y1="42" x2="62" y2="42" strokeDasharray="2 2" />
          <line x1="42" y1="58" x2="62" y2="58" strokeDasharray="2 2" />

          {/* Process pipes / rack connecting towers */}
          <path d="M31 25 H42" strokeWidth="1.5" />
          <path d="M31 45 H42" strokeWidth="1.5" />
          <path d="M62 35 H78 V78" strokeWidth="1.5" />
          <path d="M62 55 H88 V78" strokeWidth="1.5" />

          {/* Distillation pipe bridges */}
          <rect x="88" y="45" width="18" height="33" rx="1" fill="currentColor" fillOpacity="0.08" />
          <line x1="97" y1="45" x2="97" y2="35" />
          <circle cx="97" cy="34" r="2" />
        </svg>
      </div>
    </aside>
  )
}
