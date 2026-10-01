import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children?: ReactNode;
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
    errorInfo: null
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught error:", error, errorInfo);
    this.setState({ errorInfo });
    // TODO: Send to a logging service or the Core Solver
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary" style={{ padding: '20px', background: 'rgba(255, 0, 0, 0.1)', border: '1px solid red', borderRadius: '8px', margin: '20px' }}>
          <h2>Oops! Something went wrong.</h2>
          <p>Don't worry, the system is attempting to bypass this issue.</p>
          <p style={{ fontFamily: 'monospace', fontSize: '12px' }}>{this.state.error?.message}</p>
          <button 
            onClick={() => this.setState({ hasError: false })}
            style={{ padding: '8px 16px', background: 'red', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', marginTop: '10px' }}
          >
            Try Again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
