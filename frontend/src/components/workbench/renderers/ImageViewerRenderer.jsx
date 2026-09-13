import { useState } from 'react'
import { Loader2 } from 'lucide-react'

export function ImageViewerRenderer({ filePath, name, zoomLevel = 100 }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const directUrl = `/api/sources/content?path=${encodeURIComponent(filePath)}`
  const scale = zoomLevel / 100

  return (
    <div className="flex-1 w-full h-full overflow-auto p-4 flex items-center justify-center relative bg-[var(--color-bg)] custom-scrollbar">
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-[var(--color-bg)] z-10">
          <Loader2 size={32} className="animate-spin text-[var(--color-accent)]" />
        </div>
      )}
      {error ? (
        <div className="text-center text-red-500 font-mono text-xs p-4">
          Failed to load image asset
        </div>
      ) : (
        <div
          className="flex items-center justify-center transition-transform duration-150 ease-out p-4 min-h-full"
          style={{
            transform: `scale(${scale})`,
            transformOrigin: 'center center',
          }}
        >
          <img
            src={directUrl}
            alt={name || 'Image preview'}
            className="max-w-full max-h-[80vh] rounded-lg shadow-lg border border-[var(--color-border)] object-contain bg-white"
            onLoad={() => setLoading(false)}
            onError={() => {
              setLoading(false)
              setError(true)
            }}
          />
        </div>
      )}
    </div>
  )
}
