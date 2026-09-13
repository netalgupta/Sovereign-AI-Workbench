import { useRef, useState, useEffect, useCallback } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  Send,
  Paperclip,
  CheckCircle2,
  Clock,
  Loader2,
  Database,
  ShieldAlert,
  X,
  Mic,
  Square,
  Trash2,
  Play,
  Pause,
  Volume2,
} from 'lucide-react'
import { useChatStore } from '../../store/chatStore'
import { usePreviewStore } from '../../store/previewStore'
import { sendMessage, uploadAttachment, getAttachmentStatus, uploadVoiceNote, getVoiceStatus } from '../../lib/api'
import { Spinner } from '../ui/Spinner'
import { ErrorBanner } from '../ui/ErrorBanner'

/**
 * ChatComposer — message input bar with attachment payload & state sync.
 *
 * Features:
 *   - Category selection: "temporary" (session inspection) vs "permanent" (KB standard)
 *   - Near-real-time polling (1.2s interval) while attachment status is queued or processing
 *   - Live visual indicator moving queued -> processing -> ready without page refresh
 */
export function ChatComposer() {
  const draft = useChatStore((s) => s.draft)
  const setDraft = useChatStore((s) => s.setDraft)
  const attachments = useChatStore((s) => s.attachments)
  const addAttachment = useChatStore((s) => s.addAttachment)
  const updateAttachmentStatus = useChatStore((s) => s.updateAttachmentStatus)
  const removeAttachment = useChatStore((s) => s.removeAttachment)
  const sessionId = useChatStore((s) => s.sessionId)

  const [category, setCategory] = useState('temporary') // 'temporary' | 'permanent'
  const [sendError, setSendError] = useState(null)
  const [micError, setMicError] = useState(null)

  // ── Voice Recording State & Refs ───────────────────────────────────────────
  const [recordingState, setRecordingState] = useState('idle') // 'idle' | 'recording' | 'review' | 'transcribing'
  const [recordedBlob, setRecordedBlob] = useState(null)
  const [audioUrl, setAudioUrl] = useState(null)
  const [recordingTime, setRecordingTime] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)

  const mediaRecorderRef = useRef(null)
  const audioChunksRef = useRef([])
  const timerRef = useRef(null)
  const streamRef = useRef(null)
  const audioRef = useRef(null)
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)

  const addMessage = useChatStore((s) => s.addMessage)

  // Clean up recording timer & audio stream on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
      if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop())
      if (audioUrl) URL.revokeObjectURL(audioUrl)
    }
  }, [audioUrl])

  // Format seconds -> 00:00
  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  // Start recording voice note via MediaRecorder API
  const startRecording = async () => {
    setMicError(null)
    setSendError(null)
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setMicError('Microphone API is not supported in this browser or environment.')
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      audioChunksRef.current = []

      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder

      mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          audioChunksRef.current.push(e.data)
        }
      }

      mediaRecorder.onstop = () => {
        const mimeType = mediaRecorder.mimeType || 'audio/webm'
        const blob = new Blob(audioChunksRef.current, { type: mimeType })
        if (blob.size === 0) {
          setMicError('No audio recorded (empty audio blob). Please try speaking again.')
          setRecordingState('idle')
          return
        }
        const url = URL.createObjectURL(blob)
        setRecordedBlob(blob)
        setAudioUrl(url)
        setRecordingState('review')
      }

      mediaRecorder.start(100)
      setRecordingState('recording')
      setRecordingTime(0)

      timerRef.current = setInterval(() => {
        setRecordingTime((t) => t + 1)
      }, 1000)
    } catch (err) {
      console.warn('[VoiceRecorder] Permission or media error:', err)
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setMicError('Microphone permission denied. Please allow microphone access to record voice notes.')
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        setMicError('No microphone input device was found on this system.')
      } else {
        setMicError(`Could not access microphone: ${err.message || err.name}`)
      }
      setRecordingState('idle')
    }
  }

  // Stop recording
  const stopRecording = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
  }

  // Discard recording
  const discardRecording = () => {
    if (audioRef.current) {
      audioRef.current.pause()
    }
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl)
    }
    setRecordedBlob(null)
    setAudioUrl(null)
    setIsPlaying(false)
    setRecordingState('idle')
    setRecordingTime(0)
  }

  // Toggle playback of recorded audio preview
  const togglePlayAudio = () => {
    if (!audioRef.current) return
    if (isPlaying) {
      audioRef.current.pause()
      setIsPlaying(false)
    } else {
      audioRef.current.play()
      setIsPlaying(true)
    }
  }

  // Send voice note to backend for offline STT & submit transcript to chat
  const sendVoiceNote = async () => {
    if (!recordedBlob) return
    setRecordingState('transcribing')
    setSendError(null)

    try {
      const uploadRes = await uploadVoiceNote(recordedBlob, category, sessionId)
      const jobId = uploadRes?.job_id

      if (!jobId) {
        throw new Error('Failed to obtain voice job ID from server')
      }

      // Poll job status until ready or failed
      const startTime = Date.now()
      const pollInterval = setInterval(async () => {
        if (Date.now() - startTime > 30000) {
          clearInterval(pollInterval)
          setSendError('Voice transcription timed out after 30 seconds.')
          discardRecording()
          return
        }

        const jobStatus = await getVoiceStatus(jobId)
        if (jobStatus.status === 'ready') {
          clearInterval(pollInterval)
          const transcriptText = jobStatus.transcript || ''

          if (!transcriptText.trim()) {
            setSendError('No speech detected in voice recording.')
            discardRecording()
            return
          }

          // Successfully transcribed — submit through standard chat pipeline!
          let finalMessage = transcriptText.trim()
          const readyAttachments = attachments.filter((a) => a.status === 'ready')
          if (readyAttachments.length > 0) {
            const attNames = readyAttachments.map((a) => a.filename).join(', ')
            finalMessage = `${finalMessage}\n\n[Attached Files: ${attNames}]`
          }

          addMessage('user', finalMessage)
          setDraft('')
          mutation.mutate({ message: finalMessage, session_id: sessionId })

          discardRecording()
        } else if (jobStatus.status === 'failed') {
          clearInterval(pollInterval)
          setSendError(jobStatus.error || 'Voice transcription failed: No speech detected or audio processing error.')
          discardRecording()
        }
      }, 500)
    } catch (err) {
      console.error('[VoiceRecorder] Transcribe error:', err)
      setSendError(err.message || 'Error transmitting voice recording')
      discardRecording()
    }
  }

  const mutation = useMutation({
    mutationFn: ({ message, session_id }) => sendMessage(message, session_id),
    onSuccess: (data) => {
      addMessage('assistant', data.reply, {
        citations: data.citations,
        plan: data.plan,
      })
      setSendError(null)
    },
    onError: (err) => {
      setSendError(err?.message || 'Failed to send message. Please try again.')
    },
  })

  // ── Polling effect for pending attachments ────────────────────────────────
  useEffect(() => {
    const pending = attachments.filter(
      (a) => a.status === 'queued' || a.status === 'processing'
    )
    if (pending.length === 0) return

    const interval = setInterval(async () => {
      for (const att of pending) {
        const res = await getAttachmentStatus(att.attachment_id)
        if (res && res.status && res.status !== att.status) {
          updateAttachmentStatus(att.attachment_id, res.status, res)
        }
      }
    }, 1200)

    return () => clearInterval(interval)
  }, [attachments, updateAttachmentStatus])

  const handleFileSelect = async (e) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return

    for (const file of files) {
      // 1. Send upload request to backend API
      const res = await uploadAttachment(file, category, sessionId)
      const attId = res?.attachment_id || `att_${Date.now()}`

      // 2. Add attachment to store with initial status 'queued'
      addAttachment({
        attachment_id: attId,
        filename: file.name,
        type: file.type || 'application/octet-stream',
        category: category,
        status: res?.status || 'queued',
        created_at: new Date().toISOString(),
      })
    }
    // Reset file input
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const canSend = draft.trim().length > 0 && !mutation.isPending

  const handleSend = () => {
    if (!canSend) return
    const trimmed = draft.trim()
    setSendError(null)

    let finalMessage = trimmed
    const readyAttachments = attachments.filter((a) => a.status === 'ready')
    if (readyAttachments.length > 0) {
      const attNames = readyAttachments.map((a) => a.filename).join(', ')
      finalMessage = `${trimmed}\n\n[Attached Files: ${attNames}]`
    }

    addMessage('user', finalMessage)
    setDraft('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
    mutation.mutate({ message: finalMessage, session_id: sessionId })
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInput = (e) => {
    setDraft(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 200) + 'px'
  }

  return (
    <div
      className="flex-shrink-0 px-6 pb-6 pt-3"
      style={{ borderTop: '1px solid rgba(42, 39, 36, 0.04)' }}
    >
      {/* Error banners */}
      {sendError && (
        <div className="mb-3">
          <ErrorBanner message={sendError} onDismiss={() => setSendError(null)} />
        </div>
      )}

      {micError && (
        <div className="mb-3">
          <ErrorBanner message={micError} onDismiss={() => setMicError(null)} />
        </div>
      )}

      {/* Attachment status list strip */}
      {attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {attachments.map((att) => {
            const isReady = att.status === 'ready'
            const isProcessing = att.status === 'processing'
            const isQueued = att.status === 'queued'
            const isFailed = att.status === 'failed'

            return (
              <div
                key={att.attachment_id}
                onClick={() => usePreviewStore.getState().openPreview(att.filename)}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-mono border transition-all cursor-pointer hover:opacity-90"
                title={`Click to preview "${att.filename}"`}
                style={{
                  background: isReady
                    ? 'rgba(34, 197, 94, 0.08)'
                    : isProcessing
                    ? 'rgba(59, 130, 246, 0.08)'
                    : isFailed
                    ? 'rgba(239, 68, 68, 0.08)'
                    : 'rgba(234, 179, 8, 0.08)',
                  borderColor: isReady
                    ? 'rgba(34, 197, 94, 0.3)'
                    : isProcessing
                    ? 'rgba(59, 130, 246, 0.3)'
                    : isFailed
                    ? 'rgba(239, 68, 68, 0.3)'
                    : 'rgba(234, 179, 8, 0.3)',
                  color: isReady
                    ? '#15803d'
                    : isProcessing
                    ? '#1d4ed8'
                    : isFailed
                    ? '#b91c1c'
                    : '#a16207',
                }}
              >
                {att.category === 'permanent' ? (
                  <Database size={12} className="opacity-70" title="Permanent KB Document" />
                ) : (
                  <Clock size={12} className="opacity-70" title="Temporary Session File" />
                )}

                <span className="truncate max-w-[160px] font-medium">{att.filename}</span>

                <span className="text-[10px] uppercase font-bold px-1 py-0.2 rounded bg-black/5 dark:bg-white/10">
                  {att.category}
                </span>

                {/* Status indicator */}
                <div className="flex items-center gap-1 ml-1 font-semibold text-[11px]">
                  {isQueued && (
                    <>
                      <Clock size={12} className="animate-pulse" />
                      <span>queued</span>
                    </>
                  )}
                  {isProcessing && (
                    <>
                      <Loader2 size={12} className="animate-spin" />
                      <span>processing</span>
                    </>
                  )}
                  {isReady && (
                    <>
                      <CheckCircle2 size={12} />
                      <span>ready</span>
                    </>
                  )}
                  {isFailed && (
                    <>
                      <ShieldAlert size={12} />
                      <span>failed</span>
                    </>
                  )}
                </div>

                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    removeAttachment(att.attachment_id)
                  }}
                  className="ml-1 hover:opacity-75 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 cursor-pointer"
                  title="Remove attachment"
                >
                  <X size={12} />
                </button>
              </div>
            )
          })}
        </div>
      )}

      {/* ── Active Voice Recording State Overlays ─────────────────────────────── */}
      {recordingState === 'recording' ? (
        <div className="flex items-center justify-between p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-600 dark:text-red-400">
          <div className="flex items-center gap-2.5">
            <span className="w-3 h-3 rounded-full bg-red-500 animate-pulse" />
            <span className="font-mono text-xs font-bold">Recording Voice Note… {formatTime(recordingTime)}</span>
          </div>
          <button
            type="button"
            onClick={stopRecording}
            className="px-3 py-1.5 rounded-lg bg-red-500 text-white font-semibold text-xs flex items-center gap-1.5 hover:bg-red-600 transition-colors cursor-pointer shadow-xs"
          >
            <Square size={13} fill="currentColor" />
            <span>Stop Recording</span>
          </button>
        </div>
      ) : recordingState === 'review' ? (
        <div className="flex items-center justify-between p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30">
          <div className="flex items-center gap-3">
            <audio
              ref={audioRef}
              src={audioUrl}
              onEnded={() => setIsPlaying(false)}
              className="hidden"
            />
            <button
              type="button"
              onClick={togglePlayAudio}
              className="p-2 rounded-full bg-emerald-600 text-white hover:bg-emerald-700 transition-colors cursor-pointer flex items-center justify-center"
              title={isPlaying ? 'Pause preview' : 'Play audio preview'}
            >
              {isPlaying ? <Pause size={14} /> : <Play size={14} />}
            </button>
            <div className="flex flex-col text-xs font-mono">
              <span className="font-bold text-emerald-800 dark:text-emerald-300">Voice Note Preview ({formatTime(recordingTime)})</span>
              <span className="text-[10px] text-zinc-500">Ready for local offline STT</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={discardRecording}
              className="px-2.5 py-1.5 rounded-lg text-xs font-semibold text-zinc-600 hover:text-red-500 hover:bg-red-500/10 transition-colors cursor-pointer flex items-center gap-1"
              title="Discard recording"
            >
              <Trash2 size={13} />
              <span>Discard</span>
            </button>

            <button
              type="button"
              onClick={sendVoiceNote}
              className="px-3 py-1.5 rounded-lg bg-emerald-600 text-white font-semibold text-xs flex items-center gap-1.5 hover:bg-emerald-700 transition-colors cursor-pointer shadow-xs"
            >
              <Send size={13} />
              <span>Send Voice Note</span>
            </button>
          </div>
        </div>
      ) : recordingState === 'transcribing' ? (
        <div className="flex items-center gap-3 p-3 rounded-xl bg-blue-500/10 border border-blue-500/30 text-blue-600 dark:text-blue-400">
          <Loader2 size={16} className="animate-spin" />
          <span className="text-xs font-mono font-semibold">Transcribing voice note locally (faster-whisper-base)…</span>
        </div>
      ) : (
        /* Standard Composer box */
        <div
          className="flex items-end gap-2 p-3 rounded-xl transition-base"
          style={{
            background: 'white',
            border: '1px solid var(--color-border)',
            boxShadow: 'var(--shadow-sm)',
          }}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = 'var(--color-accent-border)'
            e.currentTarget.style.boxShadow = `var(--shadow-sm), 0 0 0 3px var(--color-accent-tint)`
          }}
          onBlur={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget)) {
              e.currentTarget.style.borderColor = 'var(--color-border)'
              e.currentTarget.style.boxShadow = 'var(--shadow-sm)'
            }
          }}
        >
          {/* Attachment & Voice Controls */}
          <div className="flex items-center gap-1 flex-shrink-0">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              onChange={handleFileSelect}
              className="hidden"
              disabled={mutation.isPending}
            />

            <button
              type="button"
              disabled={mutation.isPending}
              onClick={() => fileInputRef.current?.click()}
              title="Attach file (PDF, image, doc, csv)"
              className="p-1.5 rounded-md hover:bg-black/5 dark:hover:bg-white/5 text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 transition-colors disabled:opacity-40"
            >
              <Paperclip size={16} />
            </button>

            {/* Microphone Voice Note Button */}
            <button
              type="button"
              disabled={mutation.isPending}
              onClick={startRecording}
              title="Record voice note (local offline STT)"
              className="p-1.5 rounded-md hover:bg-black/5 dark:hover:bg-white/5 text-zinc-500 hover:text-red-500 dark:hover:text-red-400 transition-colors disabled:opacity-40"
            >
              <Mic size={16} />
            </button>

            {/* Category Toggle */}
            <button
              type="button"
              onClick={() => setCategory((c) => (c === 'temporary' ? 'permanent' : 'temporary'))}
              title={`Current upload category: ${category}. Click to toggle.`}
              className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold tracking-tight uppercase border transition-colors"
              style={{
                background: category === 'permanent' ? 'rgba(59, 130, 246, 0.1)' : 'rgba(107, 114, 128, 0.1)',
                borderColor: category === 'permanent' ? 'rgba(59, 130, 246, 0.3)' : 'rgba(107, 114, 128, 0.3)',
                color: category === 'permanent' ? '#2563eb' : '#4b5563',
              }}
            >
              {category === 'permanent' ? 'perm' : 'temp'}
            </button>
          </div>

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            id="chat-composer-input"
            value={draft}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            disabled={mutation.isPending}
            placeholder="Message Sovereign Workbench…"
            rows={1}
            className="flex-1 resize-none bg-transparent text-sm leading-relaxed outline-none"
            style={{
              color: 'var(--color-text)',
              minHeight: 24,
              maxHeight: 200,
              fontFamily: 'var(--font-ui)',
            }}
            aria-label="Message input"
          />

          {/* Send button */}
          <button
            id="chat-send-button"
            onClick={handleSend}
            disabled={!canSend}
            className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-lg transition-fast"
            style={{
              background: canSend ? 'var(--color-accent)' : 'var(--color-border)',
              color: canSend ? 'white' : 'var(--color-text-faint)',
              cursor: canSend ? 'pointer' : 'not-allowed',
            }}
            aria-label="Send message"
            title="Send (Enter)"
          >
            {mutation.isPending ? (
              <Spinner size="sm" />
            ) : (
              <Send size={15} strokeWidth={2} />
            )}
          </button>
        </div>
      )}

      {/* Hint text */}
      <p
        className="mt-2 text-center text-xs"
        style={{ color: 'var(--color-text-faint)' }}
      >
        Enter to send — Shift+Enter for newline · Click Mic to record voice note
      </p>
    </div>
  )
}
