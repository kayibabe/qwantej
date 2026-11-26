import { Component, StrictMode, type ErrorInfo, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import { AuthProvider } from './auth'
import { installTableSorters } from './table-sorters'

installTableSorters()

interface ErrorBoundaryState { hasError: boolean }

class AppErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep the user-facing fallback deterministic while retaining a useful
    // diagnostic in the browser console for local/support investigation.
    console.error('QwantEj workspace render failure', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4" role="alert" aria-labelledby="app-fatal-error-title">
          <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-8 text-center space-y-3 shadow-sm">
            <span className="text-sm font-bold text-slate-600">Workspace recovery</span>
            <h1 id="app-fatal-error-title" className="text-2xl font-bold tracking-tight text-slate-900">The workspace needs to reload</h1>
            <p className="text-base leading-relaxed text-slate-700">A display component failed before the workspace could be shown. Your saved research data was not changed.</p>
            <button className="inline-flex min-h-11 items-center justify-center rounded-lg bg-emerald-700 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-emerald-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700 cursor-pointer" type="button" onClick={() => window.location.reload()}>Reload workspace</button>
          </div>
        </main>
      )
    }
    return this.props.children
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppErrorBoundary><AuthProvider><App /></AuthProvider></AppErrorBoundary>
  </StrictMode>,
)
