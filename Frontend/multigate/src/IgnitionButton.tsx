import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * IgnitionButton — Floating red/green button in the bottom-right corner.
 *
 * RED   = FoveAI backend is DOWN
 * GREEN = FoveAI backend is UP
 *
 * Click when red → sends a wake request to the ignition endpoint,
 * which starts the sleipnir_launcher.sh backend stack.
 * Polls /api/status on the proxy every 5 seconds.
 */

type IgnitionState = 'checking' | 'down' | 'starting' | 'up';

const PROXY_URL = (import.meta as any).env?.VITE_PROXY_URL || 'http://127.0.0.1:8400';
const IGNITION_URL = 'http://127.0.0.1:8409/ignition';
// const IGNITION_STATUS_URL = 'http://127.0.0.1:8409/ignition/status';
const POLL_INTERVAL = 5000;

export default function IgnitionButton() {
  const [state, setState] = useState<IgnitionState>('checking');
  const [pulse, setPulse] = useState(false);
  const pollRef = useRef<number | null>(null);

  const checkBackend = useCallback(async () => {
    try {
      const res = await fetch(`${PROXY_URL}/api/status`, {
        signal: AbortSignal.timeout(3000),
      });
      if (res.ok) {
        setState((prev) => (prev === 'starting' ? 'up' : 'up'));
      } else {
        setState('down');
      }
    } catch {
      setState('down');
    }
  }, []);

  useEffect(() => {
    checkBackend();
    pollRef.current = window.setInterval(checkBackend, POLL_INTERVAL);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [checkBackend]);

  // Pulse animation when starting
  useEffect(() => {
    if (state === 'starting') {
      const i = setInterval(() => setPulse((p) => !p), 600);
      return () => clearInterval(i);
    }
    setPulse(false);
  }, [state]);

  const handleIgnition = async () => {
    if (state === 'up') return;
    setState('starting');
    try {
      // Try the ignition endpoint (small Python ignition server on :8400/ignition)
      const res = await fetch(IGNITION_URL, {
        method: 'POST',
        signal: AbortSignal.timeout(10000),
      });
      if (res.ok) {
        // Wait a moment then check
        setTimeout(checkBackend, 2000);
      } else {
        // Ignition endpoint not available — show hint
        setState('down');
      }
    } catch {
      // No ignition server running — fallback: try direct proxy wake
      try {
        await fetch(`${PROXY_URL}/api/status`, { signal: AbortSignal.timeout(2000) });
        setState('up');
      } catch {
        setState('down');
      }
    }
  };

  const colors: Record<IgnitionState, string> = {
    checking: '#fbbf24', // amber
    down: '#ef4444',      // red
    starting: pulse ? '#fbbf24' : '#f59e0b', // amber pulse
    up: '#22c55e',       // green
  };

  const labels: Record<IgnitionState, string> = {
    checking: '⟳',
    down: 'IGNITE',
    starting: 'STARTING…',
    up: 'ONLINE',
  };

  const glowColor = colors[state];
  const isClickable = state === 'down' || state === 'starting';

  return (
    <button
      onClick={handleIgnition}
      disabled={!isClickable && state === 'up'}
      style={{
        position: 'fixed',
        bottom: '20px',
        right: '20px',
        width: '64px',
        height: '64px',
        borderRadius: '50%',
        border: `3px solid ${glowColor}`,
        background: state === 'up'
          ? `radial-gradient(circle, ${glowColor}44, ${glowColor}11)`
          : `radial-gradient(circle, ${glowColor}22, ${glowColor}05)`,
        color: glowColor,
        fontSize: state === 'down' ? '10px' : '9px',
        fontWeight: 'bold',
        fontFamily: 'monospace',
        cursor: isClickable ? 'pointer' : 'default',
        boxShadow: `0 0 ${state === 'up' ? '24px' : '16px'} ${glowColor}${state === 'up' ? '88' : '55'}, inset 0 0 12px ${glowColor}33`,
        textShadow: `0 0 8px ${glowColor}`,
        transition: 'all 0.3s ease',
        zIndex: 99999,
        letterSpacing: '0.5px',
        animation: state === 'down' ? 'ignitionBreathe 2s ease-in-out infinite' : 'none',
        userSelect: 'none',
      }}
      title={
        state === 'down' ? 'FoveAI backend is DOWN — click to ignite' :
        state === 'starting' ? 'Starting backend…' :
        state === 'up' ? 'FoveAI backend is ONLINE' :
        'Checking backend…'
      }
    >
      {labels[state]}
      <style>{`
        @keyframes ignitionBreathe {
          0%, 100% { box-shadow: 0 0 12px #ef444455, inset 0 0 8px #ef444433; }
          50% { box-shadow: 0 0 28px #ef444488, inset 0 0 16px #ef444455; }
        }
      `}</style>
    </button>
  );
}
