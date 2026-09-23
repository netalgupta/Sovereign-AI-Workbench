import { useState, useEffect, useMemo } from 'react'
import * as XLSX from 'xlsx'
import { Loader2, AlertCircle, Table as TableIcon } from 'lucide-react'

// Helper to convert 0-indexed column number to Excel column letter (0 -> A, 25 -> Z, 26 -> AA)
function getColumnLetter(colIndex) {
  let letter = ''
  let temp = colIndex
  while (temp >= 0) {
    letter = String.fromCharCode((temp % 26) + 65) + letter
    temp = Math.floor(temp / 26) - 1
  }
  return letter
}

export function XlsxGridRenderer({ filePath, zoomLevel = 100, onSheetChange }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [workbook, setWorkbook] = useState(null)
  const [activeSheetIndex, setActiveSheetIndex] = useState(0)

  useEffect(() => {
    if (!filePath) return

    setLoading(true)
    setError(null)

    const url = `/api/sources/content?path=${encodeURIComponent(filePath)}`
    
    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch XLSX document`)
        return res.arrayBuffer()
      })
      .then((buffer) => {
        const wb = XLSX.read(buffer, {
          type: 'array',
          cellStyles: true,
          cellDates: true,
          cellNF: true,
          cellFormulas: true,
        })
        setWorkbook(wb)
        setActiveSheetIndex(0)
        setLoading(false)
        if (onSheetChange && wb.SheetNames.length > 0) {
          onSheetChange(1, wb.SheetNames.length, wb.SheetNames[0])
        }
      })
      .catch((err) => {
        console.error('XLSX parse error:', err)
        setError(err.message || 'Failed to parse Excel spreadsheet grid')
        setLoading(false)
      })
  }, [filePath])

  // Process current active sheet into a structured 2D grid
  const sheetData = useMemo(() => {
    if (!workbook || !workbook.SheetNames.length) return null

    const sheetName = workbook.SheetNames[activeSheetIndex] || workbook.SheetNames[0]
    const ws = workbook.Sheets[sheetName]
    if (!ws) return null

    const ref = ws['!ref'] || 'A1:A1'
    const range = XLSX.utils.decode_range(ref)

    const startRow = range.s.r
    const endRow = Math.min(range.e.r, 500) // Cap to 500 rows for smooth UI performance
    const startCol = range.s.c
    const endCol = Math.min(range.e.c, 50)  // Cap to 50 columns

    const rows = []
    for (let r = startRow; r <= endRow; r++) {
      const rowCells = []
      let rowHasData = false
      for (let c = startCol; c <= endCol; c++) {
        const cellAddress = XLSX.utils.encode_cell({ r, c })
        const cell = ws[cellAddress]

        let val = ''
        let formattedVal = ''
        let isBold = false
        let isNum = false

        if (cell) {
          val = cell.v !== undefined ? cell.v : ''
          formattedVal = cell.w || (typeof val === 'number' ? val.toLocaleString() : String(val))
          isNum = typeof val === 'number'
          if (cell.s && cell.s.font && cell.s.font.bold) {
            isBold = true
          }
        }

        if (val !== '') rowHasData = true

        rowCells.push({
          colIndex: c,
          address: cellAddress,
          val: formattedVal || val,
          isNum,
          isBold,
        })
      }
      rows.push({
        rowIndex: r + 1, // 1-based row number
        cells: rowCells,
        hasData: rowHasData,
      })
    }

    // Filter out trailing completely empty rows beyond range if needed
    const columns = []
    for (let c = startCol; c <= endCol; c++) {
      columns.push({
        colIndex: c,
        letter: getColumnLetter(c),
      })
    }

    return {
      sheetName,
      columns,
      rows,
      totalSheets: workbook.SheetNames.length,
      merges: ws['!merges'] || [],
    }
  }, [workbook, activeSheetIndex])

  const handleTabSelect = (idx) => {
    setActiveSheetIndex(idx)
    if (onSheetChange && workbook) {
      onSheetChange(idx + 1, workbook.SheetNames.length, workbook.SheetNames[idx])
    }
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center p-12 gap-3 text-center min-h-[300px]">
        <Loader2 size={32} className="animate-spin text-[var(--color-accent)]" />
        <span className="text-sm font-semibold">Parsing Spreadsheet Data & Grid...</span>
        <span className="text-xs text-muted">Building native client-side HTML table view</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center p-8 gap-3 max-w-md mx-auto text-center rounded-xl border border-red-500/30 bg-red-500/5 my-8">
        <AlertCircle size={32} className="text-red-500" />
        <span className="text-sm font-bold text-red-500">Spreadsheet Parsing Failed</span>
        <p className="text-xs text-muted font-mono">{error}</p>
      </div>
    )
  }

  if (!sheetData) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center text-muted">
        <TableIcon size={36} className="mb-2 opacity-50" />
        <span>No sheet data found in workbook</span>
      </div>
    )
  }

  const fontScale = zoomLevel / 100

  return (
    <div className="flex flex-col h-full w-full overflow-hidden bg-[var(--color-bg)]">
      {/* ── Main Spreadsheet Grid Container ────────────────────────────── */}
      <div className="flex-1 overflow-auto custom-scrollbar p-2">
        <div
          className="inline-block min-w-full border rounded-md shadow-sm overflow-hidden select-text"
          style={{
            borderColor: 'var(--color-border)',
            fontSize: `${12 * fontScale}px`,
          }}
        >
          <table className="border-collapse w-max min-w-full font-sans text-xs">
            {/* ── Table Header: Column Letters (A, B, C...) ────────────── */}
            <thead>
              <tr style={{ background: 'var(--color-surface)' }}>
                {/* Top-Left Corner Cell */}
                <th
                  className="sticky top-0 left-0 z-30 border border-[var(--color-border)] px-2 py-1.5 text-center font-mono font-bold text-[10px] text-muted select-none w-10 min-w-10"
                  style={{ background: 'var(--color-surface)' }}
                >
                  #
                </th>
                {/* Column Headers (A, B, C...) */}
                {sheetData.columns.map((col) => (
                  <th
                    key={col.colIndex}
                    className="sticky top-0 z-20 border border-[var(--color-border)] px-3 py-1.5 text-center font-mono font-semibold text-xs select-none min-w-[90px]"
                    style={{
                      background: 'var(--color-surface)',
                      color: 'var(--color-text)',
                    }}
                  >
                    {col.letter}
                  </th>
                ))}
              </tr>
            </thead>

            {/* ── Table Body: Row Numbers (1, 2, 3...) & Cells ──────────── */}
            <tbody>
              {sheetData.rows.map((row) => (
                <tr
                  key={row.rowIndex}
                  className="hover:bg-[var(--color-overlay)] transition-colors"
                >
                  {/* Sticky Row Number Label (1, 2, 3...) */}
                  <td
                    className="sticky left-0 z-10 border border-[var(--color-border)] px-2 py-1 text-center font-mono text-[11px] font-semibold text-muted select-none w-10 min-w-10"
                    style={{ background: 'var(--color-surface)' }}
                  >
                    {row.rowIndex}
                  </td>

                  {/* Cell Data Columns */}
                  {row.cells.map((cell) => (
                    <td
                      key={cell.colIndex}
                      className={`border border-[var(--color-border)] px-3 py-1.5 min-w-[90px] max-w-[300px] truncate leading-tight ${
                        cell.isNum ? 'text-right font-mono' : 'text-left'
                      } ${cell.isBold ? 'font-bold' : ''}`}
                      style={{
                        color: cell.val ? 'var(--color-text)' : 'var(--color-text-muted)',
                      }}
                      title={String(cell.val)}
                    >
                      {String(cell.val)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Excel Workbook Sheet Tabs Bar at Bottom ───────────────────────── */}
      {workbook && workbook.SheetNames.length > 0 && (
        <div
          className="flex items-center gap-1 px-3 py-2 border-t flex-shrink-0 overflow-x-auto select-none"
          style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
        >
          <span className="text-[10px] font-mono font-bold text-muted uppercase tracking-wider mr-2 flex-shrink-0">
            Sheets ({workbook.SheetNames.length}):
          </span>
          {workbook.SheetNames.map((sheetName, idx) => {
            const isActive = idx === activeSheetIndex
            return (
              <button
                key={sheetName}
                type="button"
                onClick={() => handleTabSelect(idx)}
                className={`px-3 py-1 text-xs font-semibold rounded-md transition-colors flex-shrink-0 cursor-pointer ${
                  isActive
                    ? 'bg-emerald-600 text-white shadow-xs'
                    : 'hover:bg-[var(--color-overlay)] text-muted hover:text-[var(--color-text)] border border-[var(--color-border)]'
                }`}
              >
                {sheetName}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
