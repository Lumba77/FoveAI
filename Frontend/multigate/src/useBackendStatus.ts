import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * useBackendStatus — polls the foveated-memory proxy's /api/status and
 * exposes the result plus an `ignite()` action that POSTs the ignition
 * endpoint (starts the backend stack when it's down).
 *
 * 'checking' = first probe in flight, 'offline' = proxy itself unreachable
 * (control plane dead — settings can't save, ignite can't be requested),
 * 'down' = proxy answers but the stack is down, 'starting' = ignition
 * requested, 'up' = healthy.
 */
export type BackendState = 'checking' | 'offline' | 'down' | 'starting' | 'up';

const PROXY_URL = (import.meta as any).env?.VITE_PROXY_URL || '/api/foveated';
const IGNITION_URL = '/ignition';
const POLL_INTERVAL = 5000;

export function useBackendStatus() {
  const [state, setState] = useState<BackendState>('checking');
  const pollRef = useRef<number | null>(null);

  const checkBackend = useCallback(async () => {
    try {
      const res = await fetch(`${PROXY_URL}/api/status`, {
        signal: AbortSignal.timeout(3000),
      });
      setState(res.ok ? 'up' : 'down');
    } catch {
      setState('offline');
    }
  }, []);

  useEffect(() => {
    checkBackend();
    pollRef.current = window.setInterval(checkBackend, POLL_INTERVAL);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [checkBackend]);

  const ignite = useCallback(async () => {
    if (state === 'up' || state === 'starting') return;
    setState('starting');
    try {
      const res = await fetch(IGNITION_URL, {
        method: 'POST',
        signal: AbortSignal.timeout(10000),
      });
      if (res.ok) {
        setTimeout(checkBackend, 2000);
      } else {
        setState('down');
      }
    } catch {
      // Ignition request itself failed — try a direct status probe in case it came up anyway
      try {
        await fetch(`${PROXY_URL}/api/status`, { signal: AbortSignal.timeout(2000) });
        setState('up');
      } catch {
        setState('offline');
      }
    }
  }, [state, checkBackend]);

  return { state, ignite };
}
