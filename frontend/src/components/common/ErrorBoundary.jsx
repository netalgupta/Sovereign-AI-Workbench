import React from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback(this.state.error, this.handleReset)
      }

      return (
        <div
          className="p-4 my-2 rounded-xl border flex flex-col gap-2.5 text-xs select-none"
          style={{
            background: 'var(--color-error-tint, rgba(239, 68, 68, 0.08))',
            borderColor: 'var(--color-accent-border, rgba(239, 68, 68, 0.3))',
            color: 'var(--color-text)',
          }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 font-semibold">
              <AlertTriangle size={15} className="text-red-500 flex-shrink-0" />
              <span>Rendering Error in Component</span>
            </div>
            <button
              type="button"
              onClick={this.handleReset}
              className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] border cursor-pointer hover:bg-[var(--color-surface)]"
              style={{ borderColor: 'var(--color-border)' }}
            >
              <RefreshCw size={11} />
              <span>Retry</span>
            </button>
          </div>
          <p className="text-[11px] font-mono text-[var(--color-text-muted)] break-all">
            {this.state.error?.message || 'Unknown render error'}
          </p>
        </div>
      )
    }

    return this.props.children
  }
}
