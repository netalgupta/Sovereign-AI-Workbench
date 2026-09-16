import React, { useEffect, useRef } from 'react'
import { Mic, X, Check } from 'lucide-react'

/**
 * LiveVoiceRecordingBar (LiveAudioVisualizer)
 * Single continuous live scrolling waveform across the full width,
 * matching real voice recorders (WhatsApp voice messages, iOS Voice Memos).
 *
 * [ Mic ]  ||||||||||||||||||||||||||||||||||||||||||||||||||||||  (X)  (✓)
 *
 * @param {MediaStream} stream - Active microphone MediaStream
 * @param {() => void} onConfirm - Finish and accept transcription into composer
 * @param {() => void} onCancel - Cancel and discard transcription, restoring composer
 * @param {() => void} onStop - Fallback stop handler
 */
export default function LiveAudioVisualizer({
  stream,
  onConfirm,
  onCancel,
  onStop,
}) {
  const canvasRef = useRef(null)
  const containerRef = useRef(null)
  const animFrameIdRef = useRef(null)
  const audioContextRef = useRef(null)
  const analyserRef = useRef(null)
  const sourceRef = useRef(null)
  const samplesRef = useRef([])
  const lastSampleTimeRef = useRef(0)

  const handleConfirm = onConfirm || onStop
  const handleCancel = onCancel || onStop

  useEffect(() => {
    if (!stream) return

    let isCancelled = false
    const AudioContextClass = window.AudioContext || window.webkitAudioContext
    if (!AudioContextClass) return

    const audioCtx = new AudioContextClass()
    audioContextRef.current = audioCtx

    if (audioCtx.state === 'suspended') {
      audioCtx.resume().catch(() => {})
    }

    const analyser = audioCtx.createAnalyser()
    analyser.fftSize = 128
    analyser.smoothingTimeConstant = 0.5
    analyserRef.current = analyser
    window.__SOVEREIGN_ANALYSER__ = analyser
    window.__SOVEREIGN_AUDIO_CTX__ = audioCtx

    try {
      const source = audioCtx.createMediaStreamSource(stream)
      source.connect(analyser)
      sourceRef.current = source
    } catch (err) {
      console.warn('Could not connect stream to AnalyserNode:', err)
      return
    }

    const bufferLength = analyser.frequencyBinCount
    const dataArray = new Uint8Array(bufferLength)
    const timeDomainArray = new Uint8Array(bufferLength)

    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')

    // Handle high-DPI scaling dynamically on resize
    const resizeCanvas = () => {
      if (!canvas || !containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const dpr = window.devicePixelRatio || 1
      canvas.width = Math.floor(rect.width * dpr)
      canvas.height = Math.floor(rect.height * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    resizeCanvas()
    const resizeObserver = new ResizeObserver(resizeCanvas)
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current)
    }

    const getAccentColor = () => {
      const computed = getComputedStyle(document.documentElement)
      return computed.getPropertyValue('--color-accent').trim() || '#D97757'
    }

    // Waveform geometry (bars like WhatsApp / Voice Memos)
    const barWidth = 2.5
    const barGap = 2.5
    const step = barWidth + barGap // 5px per sample
    const sampleIntervalMs = 50 // sample ~20 times per second for fluid speech tracking

    // Clear previous history for fresh session
    samplesRef.current = []
    lastSampleTimeRef.current = performance.now()

    const draw = (now) => {
      if (isCancelled) return

      analyser.getByteFrequencyData(dataArray)
      analyser.getByteTimeDomainData(timeDomainArray)

      // Calculate instantaneous speech volume
      // 1. Time-domain RMS
      let sum = 0
      for (let i = 0; i < timeDomainArray.length; i++) {
        const val = (timeDomainArray[i] - 128) / 128
        sum += val * val
      }
      const rms = Math.sqrt(sum / timeDomainArray.length)

      // 2. Frequency-domain speech band peak (bins 2..32 covers ~250Hz - 4kHz)
      let freqPeak = 0
      for (let i = 2; i < Math.min(36, bufferLength); i++) {
        if (dataArray[i] > freqPeak) freqPeak = dataArray[i]
      }
      const freqNorm = freqPeak / 255

      // Combined volume: silence produces near 0; voice produces 0.15 - 1.0
      const speechVolume = Math.min(1, Math.max(0, rms * 3.8 + freqNorm * 0.5))

      // Collect new sample at regular interval
      if (now - lastSampleTimeRef.current >= sampleIntervalMs) {
        lastSampleTimeRef.current = now
        samplesRef.current.push(speechVolume)
      }

      if (!containerRef.current) {
        animFrameIdRef.current = requestAnimationFrame(draw)
        return
      }

      const rect = containerRef.current.getBoundingClientRect()
      const width = rect.width
      const height = rect.height
      const centerY = height / 2
      const maxHeight = height * 0.82 // leave small margin top/bottom

      ctx.clearRect(0, 0, width, height)

      const accent = getAccentColor()
      const samples = samplesRef.current
      const totalSamples = samples.length

      // Calculate total width required for all recorded samples so far
      const totalRecordedWidth = totalSamples * step

      // If total samples fit within canvas width: fill left-to-right from left (x=0)
      // If total samples exceed canvas width: scroll so the newest sample stays at the right edge
      const startX = totalRecordedWidth <= width
        ? 0
        : width - totalRecordedWidth

      // Render every visible bar
      for (let i = 0; i < totalSamples; i++) {
        const x = startX + i * step

        // Skip bars that have scrolled off-screen to the left or beyond right
        if (x + barWidth < 0 || x > width) continue

        const vol = samples[i]

        // Minimal bar height during silence = 3px (clean flat pill)
        // Louder speech = tall dynamic bars up to maxHeight
        const minHeight = 3
        const barHeight = vol > 0.04
          ? Math.max(minHeight, minHeight + vol * (maxHeight - minHeight))
          : minHeight

        const y = centerY - barHeight / 2

        // Style: during silence, clean subtle accent; during voice, solid bright accent
        const alpha = vol > 0.06
          ? Math.max(0.65, Math.min(1, 0.65 + vol * 0.35))
          : 0.3

        ctx.fillStyle = accent
        ctx.globalAlpha = alpha

        ctx.beginPath()
        if (ctx.roundRect) {
          ctx.roundRect(x, y, barWidth, barHeight, barWidth / 2)
        } else {
          ctx.rect(x, y, barWidth, barHeight)
        }
        ctx.fill()

        // Subtle glow on loud speech peaks
        if (vol > 0.45) {
          ctx.shadowColor = accent
          ctx.shadowBlur = 5 * vol
        } else {
          ctx.shadowBlur = 0
        }
      }

      // Draw active leading edge indicator if recording is filling left-to-right
      if (totalSamples > 0) {
        const leadingX = Math.min(width - 2, startX + totalSamples * step)
        ctx.fillStyle = accent
        ctx.globalAlpha = 0.8
        ctx.beginPath()
        ctx.arc(leadingX, centerY, 1.75, 0, Math.PI * 2)
        ctx.fill()
      }

      ctx.globalAlpha = 1.0
      ctx.shadowBlur = 0

      animFrameIdRef.current = requestAnimationFrame(draw)
    }

    animFrameIdRef.current = requestAnimationFrame(draw)

    return () => {
      isCancelled = true
      if (animFrameIdRef.current) cancelAnimationFrame(animFrameIdRef.current)
      resizeObserver.disconnect()
      if (sourceRef.current) {
        try { sourceRef.current.disconnect() } catch (e) {}
      }
      if (audioCtx && audioCtx.state !== 'closed') {
        try { audioCtx.close() } catch (e) {}
      }
    }
  }, [stream])

  return (
    <div
      id="live-voice-recording-bar"
      className="w-full h-[46px] px-4 flex items-center gap-3 rounded-full transition-all shadow-[var(--shadow-md)] select-none"
      style={{
        background: 'var(--color-input-bg)',
        border: '1px solid var(--color-input-border)',
        boxShadow: 'var(--shadow-md)',
      }}
    >
      {/* 1. Left Icon: Mic (dimmed / muted) */}
      <div
        className="flex items-center justify-center flex-shrink-0"
        title="Voice recording active"
      >
        <Mic size={16} strokeWidth={2} style={{ color: 'var(--color-text-faint)', opacity: 0.6 }} />
      </div>

      {/* 2. Full-width continuous scrolling waveform (WhatsApp / iOS Voice Memos style) */}
      <div
        ref={containerRef}
        className="flex-1 h-7 flex items-center min-w-0 mx-2 overflow-hidden relative"
      >
        <canvas
          ref={canvasRef}
          id="live-audiogram-canvas"
          className="w-full h-full block"
        />
      </div>

      {/* 3. Cancel 'X' icon */}
      <button
        type="button"
        id="audiogram-cancel-btn"
        onClick={handleCancel}
        className="p-1.5 rounded-full flex items-center justify-center transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)] flex-shrink-0"
        style={{ color: 'var(--color-text-muted)' }}
        title="Cancel and discard voice recording"
        aria-label="Cancel recording"
      >
        <X size={15} strokeWidth={2.2} />
      </button>

      {/* 4. Confirm checkmark icon in circle, filled accent color */}
      <button
        type="button"
        id="audiogram-confirm-btn"
        onClick={handleConfirm}
        className="w-7 h-7 rounded-full flex items-center justify-center text-white transition-fast cursor-pointer shadow-xs hover:brightness-110 active:scale-95 flex-shrink-0"
        style={{ background: 'var(--color-accent)' }}
        title="Finish and accept transcription"
        aria-label="Confirm transcription"
      >
        <Check size={14} strokeWidth={2.5} />
      </button>
    </div>
  )
}
