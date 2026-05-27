import { Component } from 'react'
import type { ReactNode, ErrorInfo } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback
      return (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          gap: '12px',
          color: 'var(--text-secondary)',
          fontFamily: 'var(--font-mono, monospace)',
        }}>
          <div style={{ fontSize: '24px' }}>⚠</div>
          <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Something went wrong
          </div>
          <div style={{ fontSize: '12px', maxWidth: '480px', textAlign: 'center', opacity: 0.7 }}>
            {this.state.error?.message ?? 'An unexpected error occurred.'}
          </div>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              marginTop: '8px',
              padding: '6px 16px',
              border: '1px solid var(--border-default)',
              borderRadius: '6px',
              background: 'transparent',
              color: 'var(--text-secondary)',
              fontSize: '12px',
              cursor: 'pointer',
            }}
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
