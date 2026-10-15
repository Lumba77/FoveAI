/**
 * Service registry — the single place that knows where things live.
 *
 * Rules this replaces:
 *   1. No component ever hardcodes `127.0.0.1:<port>`. A port belongs to a
 *      *service name*; resolution happens here, same-origin first.
 *   2. Nothing throws into the void. Every call has a timeout, a retry budget
 *      and a circuit breaker, so a service that is down degrades the feature
 *      instead of blanking the page.
 *   3. Absence is a value. `resolve()` returns null rather than a broken URL,
 *      and callers branch on it.
 */

/** Logical service names → how to reach them. */
export const SERVICES = {
  gateway:   { path: '/api',                              port: 8400, label: 'proxy' },
  soul:      { path: '/api/soul',                         port: 8405, label: 'soul' },
  hearing:   { path: '/api/stt',                          port: 8401, label: 'ears' },
  voice:     { path: '/api/kokoro',                       port: 8411, label: 'mouth' },
  theme:     { path: '/api/themes',                       port: 8415, label: 'skin' },
  relay:     { path: '/api/relay',                        port: 8413, label: 'relay' },
  creative:  { path: '/api/creative',                     port: 8412, label: 'dreamscape' },
  dashboard: { path: '/',                                 port: 8414, label: 'eyes' },
  ignition:  { path: '/api/ignition',                     port: 8416, label: 'spark' },
  bridge:    { ws: '/ws/xrl',                             port: 8403, label: 'touch' },
} as const;

export type ServiceName = keyof typeof SERVICES;

export interface ServiceStatus {
  name: ServiceName;
  reachable: boolean;
  url: string | null;
  checkedAt: number;
  error?: string;
}

const status = new Map<ServiceName, ServiceStatus>();
const inflight = new Map<ServiceName, Promise<ServiceStatus>>();

const origin = () => (typeof window !== 'undefined' ? window.location.origin : '');

/** Absolute URL for a service, or null when it has no route of its own. */
export function resolve(name: ServiceName): string | null {
  const svc = SERVICES[name] as { path?: string; ws?: string; port: number };
  if (svc.path) return svc.path.startsWith('/') ? svc.path : null;
  return null;
}

/** WebSocket URL for a service (absolute, derived from the page origin). */
export function resolveWs(name: ServiceName): string | null {
  const svc = SERVICES[name] as { ws?: string };
  if (!svc.ws) return null;
  const proto = typeof location !== 'undefined' && location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}${svc.ws}`;
}

/**
 * Probe a service. Same-origin paths are trusted (the dev proxy answers);
 * anything else is health-checked directly and cached briefly.
 */
export async function probe(name: ServiceName, timeoutMs = 1200): Promise<ServiceStatus> {
  const cached = status.get(name);
  if (cached && Date.now() - cached.checkedAt < 5000) return cached;
  const pending = inflight.get(name);
  if (pending) return pending;

  const svc = SERVICES[name] as { path?: string; ws?: string; port: number; label: string };
  const task = (async (): Promise<ServiceStatus> => {
    const path = svc.path ?? (svc.ws ? svc.ws : '/');
    const url = path.startsWith('/') ? `${origin()}${path}` : null;
    let reachable = false;
    let error: string | undefined;
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), timeoutMs);
      const resp = await fetch(url ?? '', { method: 'GET', signal: ctrl.signal });
      clearTimeout(t);
      reachable = resp.ok || resp.status === 404;   // 404 still means "server answered"
    } catch (e) {
      reachable = false;
      error = String(e).slice(0, 120);
    }
    const result: ServiceStatus = { name, reachable, url, checkedAt: Date.now(), error };
    status.set(name, result);
    inflight.delete(name);
    return result;
  })();
  inflight.set(name, task);
  return task;
}

/** Circuit breaker: after N consecutive failures, stop trying for a while. */
const breakers = new Map<ServiceName, { fails: number; openUntil: number }>();
const FAIL_LIMIT = 3;
const COOLDOWN_MS = 20000;

export function breakerOpen(name: ServiceName): boolean {
  const b = breakers.get(name);
  return !!b && b.fails >= FAIL_LIMIT && Date.now() < b.openUntil;
}
function recordFailure(name: ServiceName) {
  const b = breakers.get(name) ?? { fails: 0, openUntil: 0 };
  b.fails += 1;
  if (b.fails >= FAIL_LIMIT) b.openUntil = Date.now() + COOLDOWN_MS;
  breakers.set(name, b);
}
function recordSuccess(name: ServiceName) {
  breakers.set(name, { fails: 0, openUntil: 0 });
}

/**
 * Fetch that cannot take the app down.
 * - honours the breaker (fails fast while a service is known-down)
 * - bounded retries with backoff
 * - returns a discriminated result; never throws
 */
export async function safeFetch(
  name: ServiceName,
  init: RequestInit & { retries?: number; timeoutMs?: number } = {},
): Promise<{ ok: boolean; status: number; data: any; error?: string }> {
  const { retries = 1, timeoutMs = 8000, ...rest } = init;
  const url = resolve(name);
  if (!url) return { ok: false, status: 0, data: null, error: `no route for ${name}` };
  if (breakerOpen(name)) return { ok: false, status: 0, data: null, error: `${name} breaker open` };

  let lastError = 'unknown';
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), timeoutMs);
      const resp = await fetch(url, { ...rest, signal: ctrl.signal });
      clearTimeout(timer);
      recordSuccess(name);
      const text = await resp.text();
      let data: any = text;
      try { data = JSON.parse(text); } catch { /* plain text */ }
      return { ok: resp.ok, status: resp.status, data };
    } catch (e) {
      lastError = String(e).slice(0, 160);
      if (attempt < retries) await new Promise(r => setTimeout(r, 250 * (attempt + 1)));
    }
  }
  recordFailure(name);
  return { ok: false, status: 0, data: null, error: lastError };
}

/**
 * WebSocket that never throws into the void: errors are swallowed, reconnection
 * is bounded and backoff-delayed, and callers get a plain callback.
 */
export function safeSocket(
  name: ServiceName,
  handlers: { onMessage?: (data: any) => void; onOpen?: () => void; onClose?: () => void },
  opts: { maxRetries?: number } = {},
): () => void {
  const url = resolveWs(name);
  const maxRetries = opts.maxRetries ?? 5;
  let closed = false;
  let attempt = 0;
  let ws: WebSocket | null = null;
  let timer: number | undefined;

  const connect = () => {
    if (closed || !url) return;
    if (breakerOpen(name)) {                       // back off, then try again later
      timer = window.setTimeout(connect, COOLDOWN_MS);
      return;
    }
    try {
      ws = new WebSocket(url);
    } catch {
      scheduleRetry();
      return;
    }
    ws.onopen = () => { attempt = 0; recordSuccess(name); handlers.onOpen?.(); };
    ws.onmessage = (ev) => {
      try { handlers.onMessage?.(JSON.parse(ev.data)); }
      catch { handlers.onMessage?.(ev.data); }
    };
    ws.onerror = () => { /* onclose owns retry; never let this escape */ };
    ws.onclose = () => { handlers.onClose?.(); scheduleRetry(); };
  };

  const scheduleRetry = () => {
    if (closed) return;
    if (attempt >= maxRetries) { recordFailure(name); return; }
    attempt += 1;
    timer = window.setTimeout(connect, Math.min(1000 * 2 ** attempt, 30000));
  };

  connect();
  return () => {
    closed = true;
    if (timer) clearTimeout(timer);
    try { ws?.close(); } catch { /* already gone */ }
  };
}

/** Everything we know, for diagnostics/HUD. */
export function serviceReport(): ServiceStatus[] {
  return [...status.values()];
}