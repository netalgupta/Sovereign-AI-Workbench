import React, { useState } from 'react'
import { Scan, AlertTriangle, ShieldAlert } from 'lucide-react'

const SEVERITY = {
  low: { color: '#10b981', label: 'low' },
  medium: { color: '#f59e0b', label: 'medium' },
  high: { color: '#ef4444', label: 'high' },
  critical: { color: '#b91c1c', label: 'critical' },
}

/**
 * Convert one detection box into % coordinates of the image display box.
 *
 * Contract allows 0-1 normalized OR pixel coordinates. A box whose four
 * corners are all within [0, 1] is treated as normalized; anything else is
 * treated as pixel space and normalized against the image's natural size once
 * it has loaded. Until the image is loadable (and for genuinely malformed
 * boxes), the detection is reported as unplaceable rather than guessed at a
 * position.
 */
function boxToPercent(box, image) {
  if (!box) return null
  const { xmin, ymin, xmax, ymax } = box
  if (![xmin, ymin, xmax, ymax].every((v) => typeof v === 'number')) return null

  let x = xmin
  let y = ymin
  let w = xmax - xmin
  let h = ymax - ymin

  const isNormalized = xmin >= 0 && ymin >= 0 && xmax <= 1 && ymax <= 1 && w >= 0 && h >= 0
  if (!isNormalized) {
    if (!image?.naturalWidth || !image?.naturalHeight) return null
    x = xmin / image.naturalWidth
    y = ymin / image.naturalHeight
    w = (xmax - xmin) / image.naturalWidth
    h = (ymax - ymin) / image.naturalHeight
  }

  if (h < 0) {
    y += h
    h = Math.abs(h)
  }
  if (w < 0) {
    x += w
    w = Math.abs(w)
  }
  // Clamp into the display box; a stray out-of-image box must not overflow the card.
  return {
    x: Math.max(0, Math.min(100, x * 100)),
    y: Math.max(0, Math.min(100, y * 100)),
    w: Math.max(0, Math.min(100 - x * 100, w * 100)),
    h: Math.max(0, Math.min(100 - y * 100, h * 100)),
  }
}

/**
 * Real Defect/Annotation Overlay Viewer (FRONTEND.md §3.14 / CARD 10).
 *
 * Renders an inspection image with YOLOv8-style bounding boxes overlaid,
 * labeled with class + confidence. Clicking a box (or a linked finding in the
 * side panel) selects and highlights it.
 *
 * It renders ONLY real model output. When mounted without detections or an
 * image, it shows an explicit empty state rather than a crafted sample — the
 * CARD 10 backend does not exist yet, so nothing fake is ever displayed.
 *
 * @param {import('./contract').DefectOverlayProps} props
 */
export default function DefectOverlay({
  imageUrl,
  detections = [],
  selectedDetectionId = null,
  onSelectBox,
  findings = [],
  showLabels = true,
}) {
  const [activeId, setActiveId] = useState(selectedDetectionId || null)
  const [image, setImage] = useState(null)

  const boxes = Array.isArray(detections)
    ? detections.map((d) => ({ detection: d, geom: boxToPercent(d?.box, image) }))
    : []

  const hasDetections = boxes.length > 0

  const sevCounts = {}
  for (const d of Array.isArray(detections) ? detections : []) {
    const sev = d.severity || 'medium'
    sevCounts[sev] = (sevCounts[sev] || 0) + 1
  }

  let highest = null
  for (const key of ['critical', 'high', 'medium', 'low']) {
    if (sevCounts[key]) {
      highest = { key, count: sevCounts[key] }
      break
    }
  }

  // Empty state — no fabricated overlay when there is no real model output.
  if (!imageUrl || !hasDetections) {
    return (
      <div
        className="my-3 rounded-xl border px-4 py-5 flex flex-col items-center justify-center gap-1.5 text-center text-xs"
        style={{ background: 'var(--color-card-bg)', borderColor: 'var(--color-card-border)' }}
      >
        <Scan size={18} style={{ color: 'var(--color-text-muted)' }} />
        <span className="font-semibold" style={{ color: 'var(--color-text)' }}>
          No defect detections available
        </span>
        <span style={{ color: 'var(--color-text-muted)' }}>
          {!imageUrl
            ? 'No inspection image was provided for this tool output.'
            : 'The detection tool returned no bounding boxes for this image — an overlay is only drawn from real model output.'}
        </span>
      </div>
    )
  }

  const findDetection = (id) => detections.find((d) => d.id === id)

  const handleClick = (id) => {
    setActiveId(id)
    onSelectBox?.(id)
  }

  return (
    <div
      className="my-3 rounded-xl border shadow-xs overflow-hidden text-xs"
      style={{ background: 'var(--color-card-bg)', borderColor: 'var(--color-card-border)' }}
    >
      <div
        className="px-4 py-2.5 border-b flex flex-wrap items-center justify-between gap-2"
        style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
      >
        <div className="flex items-center gap-2">
          <Scan size={15} style={{ color: 'var(--color-accent)' }} />
          <span className="font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
            Defect &amp; Anomaly Overlay
          </span>
        </div>

        <div className="flex items-center gap-2 text-[11px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
          {highest && (
            <span className="flex items-center gap-1">
              <AlertTriangle size={12} style={{ color: SEVERITY[highest.key].color }} />
              <span style={{ color: SEVERITY[highest.key].color }}>
                {highest.count} {highest.key === 'critical' ? 'critical' : 'high'} risk
              </span>
            </span>
          )}
          <span>{detections.length} box{detections.length === 1 ? '' : 'es'}</span>
        </div>
      </div>

      <div className="p-4 grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2 relative rounded-lg overflow-hidden border bg-zinc-950 flex items-start justify-center">
          <img
            src={imageUrl}
            alt="Inspection target"
            onLoad={(e) => setImage(e.currentTarget)}
            className="w-full h-auto max-h-[420px] object-contain"
            draggable={false}
          />

          {/* Bounding box overlay — real detections only */}
          <svg
            className="absolute inset-0 w-full h-full"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            {boxes.map(({ detection: det, geom }) => {
              if (!geom) return null
              const isSelected = det.id === activeId
              const color = SEVERITY[det.severity || 'medium'].color
              return (
                <rect
                  key={det.id}
                  x={geom.x}
                  y={geom.y}
                  width={geom.w}
                  height={geom.h}
                  fill={isSelected ? `${color}2e` : 'transparent'}
                  stroke={color}
                  strokeWidth={isSelected ? 0.65 : 0.35}
                  strokeDasharray={isSelected ? 'none' : '1.8 0.9'}
                  vectorEffect="non-scaling-stroke"
                  className="cursor-pointer transition-opacity hover:opacity-80"
                  onClick={() => handleClick(det.id)}
                >
                  <title>{`${det.label} (${Math.round((det.confidence || 0) * 100)}%)`}</title>
                </rect>
              )
            })}
          </svg>

          {/* Class/confidence labels */}
          {showLabels &&
            boxes.map(({ detection: det, geom }) => {
              if (!geom) return null
              const color = SEVERITY[det.severity || 'medium'].color
              const above = geom.y >= 4
              return (
                <span
                  key={`${det.id}-label`}
                  onClick={() => handleClick(det.id)}
                  className="absolute px-1.5 py-0.5 rounded text-[9px] font-mono font-bold whitespace-nowrap cursor-pointer shadow-sm"
                  style={{
                    left: geom.x,
                    top: above ? `${geom.y - 0.1}%` : `${geom.y}%`,
                    transform: above ? 'translateY(-100%)' : 'translateY(0)',
                    background: color,
                    color: '#fff',
                    zIndex: activeId === det.id ? 5 : 1,
                  }}
                >
                  {det.label} · {Math.round((det.confidence || 0) * 100)}%
                </span>
              )
            })}
        </div>

        {/* Findings panel — mirrors the active selection */}
        <div
          className="rounded-lg border p-3 flex flex-col gap-2.5 overflow-y-auto"
          style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
        >
          <div className="flex items-center gap-1.5 font-bold text-xs" style={{ color: 'var(--color-text)' }}>
            <ShieldAlert size={14} style={{ color: 'var(--color-accent)' }} />
            <span>Inspection Findings</span>
          </div>

          {findings.length === 0 ? (
            <p className="text-[11px] leading-relaxed" style={{ color: 'var(--color-text-muted)' }}>
              No linked findings in this tool output. Findings arrive with the detection result.
            </p>
          ) : (
            <div className="space-y-2">
              {findings.map((finding) => {
                const det = findDetection(finding.detectionId)
                const isSelected = finding.detectionId === activeId
                const color = SEVERITY[det?.severity || 'medium'].color

                return (
                  <div
                    key={finding.id}
                    onClick={() => det && handleClick(det.id)}
                    className="p-2.5 rounded-lg border cursor-pointer transition-colors text-xs"
                    style={{
                      background: isSelected ? 'var(--color-card-bg)' : 'transparent',
                      borderColor: isSelected ? color : 'var(--color-border)',
                      boxShadow: isSelected ? `0 0 0 1px ${color}` : 'none',
                    }}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-bold text-[11px]" style={{ color }}>
                        {det?.label || finding.detectionId}
                      </span>
                      {det ? (
                        <span className="font-mono text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                          {Math.round((det.confidence || 0) * 100)}% conf
                        </span>
                      ) : (
                        <span className="font-mono text-[10px]" style={{ color: 'var(--color-text-faint)' }}>
                          unlinked box
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] leading-relaxed" style={{ color: 'var(--color-text)' }}>
                      {finding.description}
                    </p>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}