import { useEffect, useState } from 'react'
import { ArrowUpRight, ChevronRight } from 'lucide-react'
import { landingConfig, getTimeGreeting } from '../../config/landingConfig'

export function AmbientBackground() {
  return <div className="landing-ambient" aria-hidden="true" />
}

export function TimeGreeting() {
  const [greeting, setGreeting] = useState(() => getTimeGreeting())

  useEffect(() => {
    const interval = window.setInterval(() => setGreeting(getTimeGreeting()), 60_000)
    return () => window.clearInterval(interval)
  }, [])

  return (
    <div className="landing-greeting" aria-live="polite">
      <p className="landing-eyebrow">MRPL / PRIVATE INTELLIGENCE</p>
      <h1>{greeting.title}</h1>
      <p className="landing-greeting-detail">{greeting.detail}</p>
    </div>
  )
}

export function CommandInput({ value, onChange, onSubmit, onFocus, onBlur, disabled }) {
  return (
    <form
      className="landing-command"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit(value)
      }}
    >
      <label className="landing-command-label" htmlFor="landing-prompt">START AN INVESTIGATION</label>
      <div className="landing-command-field">
        <input
          id="landing-prompt"
          type="text"
          autoComplete="off"
          maxLength={2000}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onFocus={onFocus}
          onBlur={onBlur}
          placeholder="Ask MRPL anything..."
          aria-label="Ask MRPL anything"
          disabled={disabled}
        />
        <button
          className="landing-command-submit"
          type="submit"
          aria-label="Send question"
          title="Start investigation"
          disabled={!value.trim() || disabled}
        >
          <ArrowUpRight size={19} strokeWidth={1.7} />
        </button>
      </div>
      <p className="landing-command-hint">
        <span>ENTER</span> to begin <i /> answers grounded in your local records
      </p>
    </form>
  )
}

export function SuggestedActions({ onQuery, onRoute, disabled }) {
  return (
    <nav className="landing-actions" aria-label="Suggested investigations">
      <div className="landing-actions-heading">
        <span>GOOD PLACES TO START</span>
        <span>LOCAL CAPABILITIES</span>
      </div>
      <div className="landing-actions-list">
        {landingConfig.quickActions.map((action, index) => (
          <button
            type="button"
            className="landing-action"
            key={action.label}
            onClick={() => action.route ? onRoute(action.route) : onQuery(action.query)}
            disabled={disabled}
            style={{ '--action-index': index }}
          >
            <span className="landing-action-index">0{index + 1}</span>
            <span className="landing-action-copy">
              <span className="landing-action-label">{action.label}</span>
              <span className="landing-action-detail">{action.detail}</span>
            </span>
            <ChevronRight className="landing-action-arrow" size={16} strokeWidth={1.5} />
          </button>
        ))}
      </div>
    </nav>
  )
}

function statusTone(value, positiveValues = []) {
  if (!value || value === 'CHECKING') return 'muted'
  if (positiveValues.some((positive) => value.startsWith(positive))) return 'ready'
  if (value.includes('DETECTED')) return 'attention'
  return 'muted'
}

export function SystemStatus({ status }) {
  const items = [
    { label: 'INTELLIGENCE', value: status.intelligence, positive: ['ONLINE'] },
    { label: 'KNOWLEDGE BASE', value: status.knowledge, positive: ['READY'] },
    { label: 'KNOWLEDGE GRAPH', value: status.graph, positive: ['CONNECTED', 'LOCAL SNAPSHOT'] },
    { label: 'LOCAL MODELS', value: status.models, positive: ['RUNTIME READY'] },
    { label: 'NETWORK', value: status.network, positive: ['ISOLATED'] },
  ]

  return (
    <section className="landing-status" aria-label="Local system status">
      <div className="landing-status-title">
        <span className="landing-status-mark" />
        <span>SOVEREIGN SYSTEM</span>
      </div>
      <div className="landing-status-items">
        {items.map((item) => (
          <div className="landing-status-item" key={item.label}>
            <span className="landing-status-label">{item.label}</span>
            <span className={`landing-status-value is-${statusTone(item.value, item.positive)}`}>
              <i />{item.value || 'CHECKING'}
            </span>
          </div>
        ))}
      </div>
      <span className="landing-status-local">ON-DEVICE · PRIVATE BY DESIGN</span>
    </section>
  )
}

export function IntroSequence({ onComplete, onSkip }) {
  const [step, setStep] = useState(0)

  useEffect(() => {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const timer = window.setTimeout(() => {
      if (step < landingConfig.introSteps.length - 1) setStep(step + 1)
      else onComplete()
    }, reducedMotion ? 300 : landingConfig.introStepDurationMs)
    return () => window.clearTimeout(timer)
  }, [onComplete, step])

  return (
    <div className="landing-intro" role="status" aria-live="polite">
      <div className="landing-intro-center">
        <span className="landing-intro-index">0{step + 1} / 05</span>
        <p key={step}>{landingConfig.introSteps[step]}<span className="landing-intro-period">.</span></p>
        <div className="landing-intro-track"><i style={{ width: `${((step + 1) / landingConfig.introSteps.length) * 100}%` }} /></div>
      </div>
      <button className="landing-intro-skip" type="button" onClick={onSkip}>SKIP INTRO <ArrowUpRight size={13} /></button>
    </div>
  )
}