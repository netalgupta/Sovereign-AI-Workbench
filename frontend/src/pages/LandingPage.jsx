import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Moon, Sun } from 'lucide-react'
import { HeroVisual } from '../components/landing/HeroVisual'
import {
  AmbientBackground,
  CommandInput,
  IntroSequence,
  SuggestedActions,
  SystemStatus,
  TimeGreeting,
} from '../components/landing/LandingComponents'
import { landingConfig } from '../config/landingConfig'
import '../styles/landing.css'

async function getLocalJson(path) {
  const response = await fetch(path, { cache: 'no-store' })
  if (!response.ok) throw new Error(`Local service returned ${response.status}`)
  return response.json()
}

function initialStatus() {
  return {
    intelligence: 'CHECKING',
    knowledge: 'CHECKING',
    graph: 'CHECKING',
    models: 'CHECKING',
    network: 'CHECKING',
  }
}

export function LandingPage() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [isFocused, setIsFocused] = useState(false)
  const [isLeaving, setIsLeaving] = useState(false)
  const [theme, setTheme] = useState(() => {
    try {
      return window.localStorage.getItem('mrpl_landing_theme') === 'light' ? 'light' : 'dark'
    } catch {
      return 'dark'
    }
  })
  const [introVisible, setIntroVisible] = useState(() => {
    try {
      return window.localStorage.getItem(landingConfig.introStorageKey) !== '1'
    } catch {
      return false
    }
  })
  const [status, setStatus] = useState(initialStatus)
  const transitionTimer = useRef(null)

  useEffect(() => {
    if (!introVisible) return
    try {
      window.localStorage.setItem(landingConfig.introStorageKey, '1')
    } catch {
      // The intro still works when browser storage is unavailable.
    }
  }, [introVisible])

  useEffect(() => {
    try {
      window.localStorage.setItem('mrpl_landing_theme', theme)
    } catch {
      // The selected theme still applies for this page view.
    }
  }, [theme])

  useEffect(() => {
    let active = true
    const requests = [
      getLocalJson('/api/health'),
      getLocalJson('/api/corpus'),
      getLocalJson('/api/graph'),
      getLocalJson('/api/models'),
      getLocalJson('/api/network/status'),
    ]

    Promise.allSettled(requests).then(([health, corpus, graph, models, network]) => {
      if (!active) return

      const next = initialStatus()
      next.intelligence = health.status === 'fulfilled' ? 'ONLINE' : 'UNAVAILABLE'
      if (corpus.status === 'fulfilled') {
        const data = corpus.value
        const count = data.chunkCount ?? data.chunk_count ?? data.count ?? data.sources?.length
        next.knowledge = count == null ? 'READY' : `READY · ${count} ITEMS`
      } else {
        next.knowledge = 'UNAVAILABLE'
      }
      if (graph.status === 'fulfilled') {
        const count = graph.value.nodes?.length ?? 0
        next.graph = count > 0 ? `CONNECTED · ${count} NODES` : 'UNAVAILABLE'
      } else {
        next.graph = 'UNAVAILABLE'
      }
      if (models.status === 'fulfilled') {
        next.models = models.value.ollama_reachable ? 'RUNTIME READY' : 'RUNTIME OFFLINE'
      } else {
        next.models = 'RUNTIME UNAVAILABLE'
      }
      if (network.status === 'fulfilled') {
        next.network = network.value.is_air_gapped === true
          ? 'ISOLATED · NO OUTBOUND'
          : network.value.is_air_gapped === false
            ? 'CONNECTION DETECTED'
            : 'STATUS UNKNOWN'
      } else {
        next.network = 'STATUS UNKNOWN'
      }
      setStatus(next)
    })

    return () => { active = false }
  }, [])

  useEffect(() => () => window.clearTimeout(transitionTimer.current), [])

  const markIntroComplete = useCallback(() => setIntroVisible(false), [])
  const markIntroSkipped = useCallback(() => setIntroVisible(false), [])

  const beginTransition = useCallback((destination, initialQuery) => {
    if (isLeaving) return
    setIsLeaving(true)
    transitionTimer.current = window.setTimeout(() => {
      navigate(destination, initialQuery ? { state: { initialQuery } } : undefined)
    }, landingConfig.transitionDurationMs)
  }, [isLeaving, navigate])

  const handleSubmit = useCallback((value) => {
    const trimmed = value.trim()
    if (!trimmed) return
    setQuery(trimmed)
    beginTransition('/chat', trimmed)
  }, [beginTransition])

  const handleRoute = useCallback((route) => beginTransition(route), [beginTransition])
  const awake = isFocused || query.length > 0 || isLeaving

  return (
    <main className={`landing-page${awake ? ' is-active' : ''}${isLeaving ? ' is-leaving' : ''}`} data-theme={theme}>
      <AmbientBackground />
      <div className="landing-topline">
        <Link className="landing-brand" to="/" aria-label="MRPL sovereign intelligence home">
          <span className="landing-brand-emblem">M</span>
          <span className="landing-brand-name">MRPL<span> / </span>INTELLIGENCE</span>
        </Link>
        <div className="landing-instance">
          <span className="landing-instance-light" />
          <span>PRIVATE INSTANCE</span>
          <span className="landing-instance-divider" />
          <span>NETWORK MONITORED</span>
          <button
            className="landing-theme-toggle"
            type="button"
            onClick={() => setTheme((current) => current === 'dark' ? 'light' : 'dark')}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            aria-pressed={theme === 'light'}
          >
            {theme === 'dark' ? <Sun size={14} strokeWidth={1.6} /> : <Moon size={14} strokeWidth={1.6} />}
          </button>
        </div>
      </div>

      <div className="landing-content">
        <section className="landing-copy" aria-label="Start a local investigation">
          <TimeGreeting />
          <div className="landing-question-block">
            <p className="landing-question-kicker">MRPL INTELLIGENCE</p>
            <h2>what are we<br />working on?</h2>
          </div>
          <CommandInput
            value={query}
            onChange={setQuery}
            onSubmit={handleSubmit}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            disabled={isLeaving}
          />
          <SuggestedActions onQuery={handleSubmit} onRoute={handleRoute} disabled={isLeaving} />
        </section>

        <HeroVisual awake={awake} asset={landingConfig.heroAsset} />
      </div>

      <SystemStatus status={status} />
      {introVisible && <IntroSequence onComplete={markIntroComplete} onSkip={markIntroSkipped} />}
      <div className="landing-transition-label" aria-hidden="true">OPENING LOCAL SESSION</div>
    </main>
  )
}