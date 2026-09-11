import { useState, useRef } from 'react'
import {
  X,
  FolderPlus,
  FilePlus,
  Folder,
  HardDrive,
  CheckCircle2,
  Trash2,
  UploadCloud,
  Plus,
  Loader2,
} from 'lucide-react'
import { showToast } from '../../store/toastStore'

// Helper to convert browser File object to Base64
const readFileAsBase64 = (file) => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result
      const base64 = typeof result === 'string' ? result.split(',')[1] || '' : ''
      resolve(base64)
    }
    reader.onerror = (err) => reject(err)
    reader.readAsDataURL(file)
  })
}

export function AddSourceDirectoryModal({ isOpen, onClose, onDirectoriesUpdated, currentDirectories = [] }) {
  const [customPath, setCustomPath] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [uploadStatus, setUploadStatus] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const folderInputRef = useRef(null)
  const fileInputRef = useRef(null)

  if (!isOpen) return null

  // Core file batch upload handler
  const uploadFiles = async (fileList) => {
    const filesArray = Array.from(fileList || [])
    if (filesArray.length === 0) return

    setIsSubmitting(true)
    setUploadStatus(`Preparing ${filesArray.length} file(s)...`)

    try {
      const filesToUpload = []
      for (let i = 0; i < filesArray.length; i++) {
        const file = filesArray[i]
        setUploadStatus(`Reading ${i + 1}/${filesArray.length}: ${file.name}...`)
        const base64 = await readFileAsBase64(file)
        const relPath = file.webkitRelativePath || file.name
        filesToUpload.push({
          name: file.name,
          relPath,
          contentBase64: base64,
          sizeBytes: file.size,
        })
      }

      setUploadStatus(`Ingesting, chunking & generating embeddings for ${filesToUpload.length} file(s)...`)

      const res = await fetch('/api/sources/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ files: filesToUpload }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.error || 'Failed to upload source file(s)')
      }

      const chunkNotice = data.total_chunks != null ? ` (${data.total_chunks} chunks embedded & indexed in FAISS)` : ''
      showToast(
        data.message || `Successfully ingested ${data.count || filesToUpload.length} source document(s)${chunkNotice}`,
        'success'
      )
      if (onDirectoriesUpdated) onDirectoriesUpdated()
      onClose()
    } catch (err) {
      showToast(err.message || 'Failed to upload source documents', 'error')
    } finally {
      setIsSubmitting(false)
      setUploadStatus('')
    }
  }

  // Handle manual path submission
  const handleAddPath = async (e) => {
    e?.preventDefault()
    const pathToAdd = customPath.trim()
    if (!pathToAdd) {
      showToast('Please enter a valid directory or file path', 'error')
      return
    }

    setIsSubmitting(true)
    setUploadStatus('Resolving path, chunking document(s) & generating embeddings...')
    try {
      const res = await fetch('/api/sources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: pathToAdd, recursive: true }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.error || 'Failed to add source')
      }

      showToast(data.message || `Source registered: ${pathToAdd}`, 'success')
      setCustomPath('')
      if (onDirectoriesUpdated) onDirectoriesUpdated()
    } catch (err) {
      showToast(err.message, 'error')
    } finally {
      setIsSubmitting(false)
      setUploadStatus('')
    }
  }


  // Handle native folder browse
  const handleFolderPicked = async (e) => {
    const files = e.target.files
    if (!files || files.length === 0) return
    await uploadFiles(files)
    e.target.value = ''
  }

  // Handle native files browse
  const handleFilesPicked = async (e) => {
    const files = e.target.files
    if (!files || files.length === 0) return
    await uploadFiles(files)
    e.target.value = ''
  }

  // Handle drag & drop
  const handleDrop = async (e) => {
    e.preventDefault()
    setDragOver(false)
    const files = e.dataTransfer.files
    if (files && files.length > 0) {
      await uploadFiles(files)
    }
  }

  // Remove directory
  const handleRemoveDir = async (dirPath) => {
    try {
      const res = await fetch(`/api/sources?path=${encodeURIComponent(dirPath)}`, {
        method: 'DELETE',
      })
      if (res.ok) {
        showToast('Source removed from retrieval scope', 'info')
        if (onDirectoriesUpdated) onDirectoriesUpdated()
      }
    } catch {
      showToast('Failed to remove source', 'error')
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in"
      style={{ background: 'rgba(0, 0, 0, 0.55)', backdropFilter: 'blur(3px)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-xl shadow-2xl border flex flex-col overflow-hidden animate-scale-in"
        style={{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
          color: 'var(--color-text)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Hidden inputs for native browser file/folder dialogs */}
        <input
          type="file"
          ref={folderInputRef}
          onChange={handleFolderPicked}
          webkitdirectory="true"
          directory="true"
          multiple
          className="hidden"
        />
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFilesPicked}
          multiple
          accept=".pdf,.docx,.xlsx,.xls,.png,.jpg,.jpeg,.txt,.json,.csv"
          className="hidden"
        />

        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-3.5 border-b"
          style={{ borderColor: 'var(--color-border)' }}
        >
          <div className="flex items-center gap-2.5">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center"
              style={{
                background: 'var(--color-accent-tint, rgba(37,99,235,0.12))',
                color: 'var(--color-accent)',
                border: '1px solid var(--color-border)',
              }}
            >
              <FolderPlus size={16} strokeWidth={2.2} />
            </div>
            <div>
              <h3 className="text-sm font-bold leading-tight" style={{ color: 'var(--color-text)' }}>
                Add Source Directories & Files
              </h3>
              <p className="text-[11px] leading-tight mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                Air-gapped on-prem ingestion into local knowledge base
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-7 h-7 rounded-md flex items-center justify-center hover:bg-[var(--color-overlay)] transition-fast cursor-pointer"
            style={{ color: 'var(--color-text-muted)' }}
          >
            <X size={15} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 flex flex-col gap-4 overflow-y-auto max-h-[75vh]">
          {/* Quick Browse Buttons (Native System Picker) */}
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              disabled={isSubmitting}
              onClick={() => folderInputRef.current?.click()}
              className="flex items-center gap-2.5 p-3 rounded-lg border text-left transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)] group disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                background: 'var(--color-bg)',
                borderColor: 'var(--color-border)',
              }}
            >
              <div
                className="w-8 h-8 rounded-md flex items-center justify-center flex-shrink-0"
                style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-accent)',
                }}
              >
                <Folder size={16} />
              </div>
              <div className="flex flex-col min-w-0">
                <span className="text-xs font-semibold" style={{ color: 'var(--color-text)' }}>
                  Browse Folder…
                </span>
                <span className="text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                  Pick directory from PC
                </span>
              </div>
            </button>

            <button
              type="button"
              disabled={isSubmitting}
              onClick={() => fileInputRef.current?.click()}
              className="flex items-center gap-2.5 p-3 rounded-lg border text-left transition-fast cursor-pointer hover:bg-[var(--color-surface-hover)] group disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                background: 'var(--color-bg)',
                borderColor: 'var(--color-border)',
              }}
            >
              <div
                className="w-8 h-8 rounded-md flex items-center justify-center flex-shrink-0"
                style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  color: '#059669',
                }}
              >
                <FilePlus size={16} />
              </div>
              <div className="flex flex-col min-w-0">
                <span className="text-xs font-semibold" style={{ color: 'var(--color-text)' }}>
                  Browse Files…
                </span>
                <span className="text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                  PDF, DOCX, XLSX, PNG
                </span>
              </div>
            </button>
          </div>

          {/* Active Ingestion / Upload Progress Indicator */}
          {isSubmitting && (
            <div
              className="flex items-center gap-2.5 p-3 rounded-lg border text-xs animate-pulse"
              style={{
                background: 'var(--color-accent-tint, rgba(37,99,235,0.08))',
                borderColor: 'var(--color-accent)',
                color: 'var(--color-accent)',
              }}
            >
              <Loader2 size={16} className="animate-spin flex-shrink-0" />
              <div className="flex flex-col min-w-0">
                <span className="font-semibold text-xs leading-tight">
                  {uploadStatus || 'Processing documents...'}
                </span>
                <span className="text-[10px] opacity-80 mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                  Extracting pages, structuring metadata & updating local corpus
                </span>
              </div>
            </div>
          )}

          {/* Drag & Drop Zone */}
          <div
            onDragOver={(e) => {
              if (isSubmitting) return
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-xl p-4 flex flex-col items-center justify-center text-center transition-fast ${
              isSubmitting ? 'opacity-50 pointer-events-none' : ''
            }`}
            style={{
              borderColor: dragOver ? 'var(--color-accent)' : 'var(--color-border-strong, var(--color-border))',
              background: dragOver ? 'var(--color-overlay)' : 'var(--color-bg)',
            }}
          >
            <UploadCloud
              size={24}
              strokeWidth={1.8}
              className="mb-1.5"
              style={{ color: dragOver ? 'var(--color-accent)' : 'var(--color-text-muted)' }}
            />
            <span className="text-xs font-medium" style={{ color: 'var(--color-text)' }}>
              Drag and drop folders or files here
            </span>
            <span className="text-[10px] mt-0.5" style={{ color: 'var(--color-text-faint)' }}>
              Auto-extracted with OCR & table structure preservation
            </span>
          </div>

          {/* Manual Path Entry Form */}
          <form onSubmit={handleAddPath} className="flex flex-col gap-2">
            <label className="text-xs font-semibold flex items-center justify-between">
              <span style={{ color: 'var(--color-text)' }}>Enter Host Filesystem Path</span>
              <span className="text-[10px] font-mono" style={{ color: 'var(--color-text-muted)' }}>
                Absolute or relative
              </span>
            </label>
            <div className="flex items-center gap-2">
              <div
                className="flex-1 flex items-center gap-2 px-3 py-2 rounded-md border text-xs"
                style={{
                  background: 'var(--color-bg)',
                  borderColor: 'var(--color-border)',
                }}
              >
                <HardDrive size={14} className="flex-shrink-0" style={{ color: 'var(--color-text-muted)' }} />
                <input
                  type="text"
                  value={customPath}
                  onChange={(e) => setCustomPath(e.target.value)}
                  placeholder="e.g. C:\SIH\SIH26117-Sovereign-Workbench\MRPL_Chart_Stress_Corpus"
                  className="flex-1 bg-transparent outline-none font-mono text-[11px]"
                  style={{ color: 'var(--color-text)' }}
                />
              </div>
              <button
                type="submit"
                disabled={isSubmitting || !customPath.trim()}
                className="px-3.5 py-2 rounded-md text-xs font-semibold flex items-center gap-1.5 shadow-xs transition-fast cursor-pointer disabled:opacity-50"
                style={{
                  background: 'var(--color-accent)',
                  color: '#fff',
                }}
              >
                <Plus size={13} strokeWidth={2.4} />
                <span>Add</span>
              </button>
            </div>
          </form>

          {/* Watched Directories List */}
          <div className="flex flex-col gap-2 pt-2 border-t" style={{ borderColor: 'var(--color-border)' }}>
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold uppercase tracking-wider text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                Active Watched Directories ({currentDirectories.length})
              </span>
              <span className="text-[10px] text-muted font-mono">Dynamic On-Disk Sync</span>
            </div>

            <div className="flex flex-col gap-1.5 max-h-40 overflow-y-auto pr-1">
              {currentDirectories.map((dir) => (
                <div
                  key={dir.id || dir.path}
                  className="flex items-center justify-between p-2 rounded-md border text-xs"
                  style={{
                    background: 'var(--color-bg)',
                    borderColor: 'var(--color-border)',
                  }}
                >
                  <div className="flex items-center gap-2 min-w-0 pr-2">
                    <CheckCircle2
                      size={13}
                      className="flex-shrink-0"
                      style={{ color: 'var(--color-success, #2f7a52)' }}
                    />
                    <div className="flex flex-col min-w-0">
                      <div className="flex items-center gap-1.5 truncate">
                        <span className="font-semibold text-[11px] truncate" style={{ color: 'var(--color-text)' }}>
                          {dir.name}
                        </span>
                        {dir.isPreset && (
                          <span
                            className="text-[9px] px-1 py-0.2 rounded font-mono font-semibold"
                            style={{ background: 'var(--color-overlay)', color: 'var(--color-accent)' }}
                          >
                            DEFAULT
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] font-mono truncate" style={{ color: 'var(--color-text-muted)' }} title={dir.fullPath || dir.path}>
                        {dir.fullPath || dir.path}
                      </span>
                    </div>
                  </div>

                  {!dir.isPreset && (
                    <button
                      type="button"
                      onClick={() => handleRemoveDir(dir.path)}
                      className="p-1 rounded hover:bg-[var(--color-overlay)] text-muted hover:text-red-500 transition-fast cursor-pointer"
                      title="Remove from watched sources"
                    >
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div
          className="px-5 py-3 border-t flex items-center justify-between"
          style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)' }}
        >
          <span className="text-[11px]" style={{ color: 'var(--color-text-faint)' }}>
            Zero-egress: files are processed strictly on local hardware
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded-md text-xs font-medium border cursor-pointer hover:bg-[var(--color-surface)]"
            style={{ borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
          >
            Done
          </button>
        </div>
      </div>
    </div>
  )
}
