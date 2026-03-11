import React, { Component, ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    // Update state so the next render will show the fallback UI.
    return { hasError: true, error, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught error:", error, errorInfo);
    this.setState({ error, errorInfo });
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-zinc-950 text-red-500 p-10 font-mono">
          <div className="max-w-4xl w-full border border-red-900 bg-red-950/20 p-8 rounded-lg shadow-2xl">
            <h1 className="text-3xl font-bold mb-4 uppercase tracking-wider">System Critical Failure</h1>
            <div className="bg-black/50 p-6 rounded border border-red-900/50 mb-6 overflow-auto max-h-[50vh]">
                <p className="text-xl font-bold mb-2">{this.state.error?.toString()}</p>
                <pre className="text-xs text-zinc-400 whitespace-pre-wrap">
                    {this.state.errorInfo?.componentStack}
                </pre>
            </div>
            <button
                onClick={() => window.location.reload()}
                className="bg-red-600 hover:bg-red-700 text-white px-6 py-3 rounded font-bold uppercase transition-colors"
            >
                Re-Initialize System
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
