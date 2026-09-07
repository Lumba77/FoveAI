/**
 * ForgeCore — WebSocket client and state manager for The Forge IDE.
 *
 * Connects to the Forge API WebSocket for real-time agent events,
 * manages session state, and provides an event bus for UI components.
 */

export interface ForgeEvent {
  type: string;
  session_id?: string;
  model?: string;
  content?: string;
  tool?: string;
  args?: any;
  result?: any;
  path?: string;
  diff?: string;
  message?: string;
  code?: string;
  duration_s?: number;
  duration_ms?: number;
  tokens?: number;
  stream?: string;
  reason?: string;
  workspace?: string;
  timestamp?: string;
  raw?: string;
}

export interface SessionInfo {
  session_id: string;
  model: string;
  is_running: boolean;
  uptime_s: number;
  subscriber_count: number;
  event_summary: Record<string, number>;
}

export type EventHandler = (event: ForgeEvent) => void;

export class ForgeCore {
  private ws: WebSocket | null = null;
  private apiBase: string;
  private handlers: Map<string, Set<EventHandler>> = new Map();
  private _connected: boolean = false;
  private _reconnectTimer: number | null = null;
  private _eventCount: number = 0;
  private _sessionCount: number = 0;

  // Event history for replay
  public eventHistory: ForgeEvent[] = [];
  public maxHistory: number = 500;

  constructor(apiBase?: string) {
    this.apiBase = apiBase || (window as any).FORGE_API || 'http://127.0.0.1:8100';
  }

  // ── Connection ──

  async connect(): Promise<void> {
    const wsUrl = this.apiBase.replace('http://', 'ws://').replace('https://', 'wss://') + '/ws/agent-stream';
    console.log('[ForgeCore] Connecting to', wsUrl);

    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(wsUrl);
      } catch (e) {
        reject(new Error(`WebSocket creation failed: ${e}`));
        return;
      }

      this.ws.onopen = () => {
        console.log('[ForgeCore] WebSocket connected');
        this._connected = true;
        this.emit({ type: 'forge_connected', timestamp: new Date().toISOString() });
        resolve();
      };

      this.ws.onmessage = (msg) => {
        try {
          const event: ForgeEvent = JSON.parse(msg.data);
          this._eventCount++;
          this.eventHistory.push(event);
          if (this.eventHistory.length > this.maxHistory) {
            this.eventHistory = this.eventHistory.slice(-this.maxHistory);
          }
          this.dispatch(event);
        } catch (e) {
          console.warn('[ForgeCore] Failed to parse event:', e);
        }
      };

      this.ws.onclose = (ev) => {
        console.log('[ForgeCore] WebSocket closed:', ev.code, ev.reason);
        this._connected = false;
        this.emit({ type: 'forge_disconnected', code: String(ev.code), reason: ev.reason });
        this.scheduleReconnect();
      };

      this.ws.onerror = (err) => {
        console.error('[ForgeCore] WebSocket error:', err);
        if (!this._connected) {
          reject(new Error('WebSocket connection failed. Is Forge API running on port 8100?'));
        }
      };
    });
  }

  private scheduleReconnect() {
    if (this._reconnectTimer) return;
    console.log('[ForgeCore] Scheduling reconnect in 3s...');
    this._reconnectTimer = window.setTimeout(() => {
      this._reconnectTimer = null;
      this.connect().catch(e => console.warn('[ForgeCore] Reconnect failed:', e));
    }, 3000);
  }

  disconnect() {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close(1000, 'user_disconnect');
      this.ws = null;
    }
    this._connected = false;
  }

  // ── Event System ──

  on(eventType: string, handler: EventHandler): void {
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, new Set());
    }
    this.handlers.get(eventType)!.add(handler);
  }

  off(eventType: string, handler: EventHandler): void {
    this.handlers.get(eventType)?.delete(handler);
  }

  private dispatch(event: ForgeEvent): void {
    // Dispatch to type-specific handlers
    const typeHandlers = this.handlers.get(event.type);
    if (typeHandlers) {
      for (const h of typeHandlers) {
        try { h(event); } catch (e) { console.error('[ForgeCore] Handler error:', e); }
      }
    }
    // Dispatch to wildcard handlers
    const allHandlers = this.handlers.get('*');
    if (allHandlers) {
      for (const h of allHandlers) {
        try { h(event); } catch (e) { console.error('[ForgeCore] Handler error:', e); }
      }
    }
  }

  private emit(event: ForgeEvent): void {
    this.dispatch(event);
  }

  // ── REST API Helpers ──

  async apiGet(path: string): Promise<any> {
    const res = await fetch(`${this.apiBase}/api${path}`);
    if (!res.ok) throw new Error(`API ${path}: ${res.status}`);
    return res.json();
  }

  async apiPost(path: string, body?: any): Promise<any> {
    const res = await fetch(`${this.apiBase}/api${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `API ${path}: ${res.status}`);
    }
    return res.json();
  }

  // ── Session Commands ──

  async spawnSession(model: string = 'deepseek-v4-pro', prompt?: string): Promise<string> {
    const res = await this.apiPost('/sessions/spawn', { model, prompt });
    return res.session_id;
  }

  async stopSession(sessionId: string): Promise<void> {
    await this.apiPost(`/sessions/${sessionId}/stop`);
  }

  async sendPrompt(sessionId: string, text: string): Promise<void> {
    await this.apiPost(`/sessions/${sessionId}/prompt`, { text });
  }

  async getStatus(): Promise<any> {
    return this.apiGet('/status');
  }

  async listSessions(): Promise<SessionInfo[]> {
    const res = await this.apiGet('/sessions');
    return res.sessions || [];
  }

  // ── Properties ──

  get connected(): boolean { return this._connected; }
  get eventCount(): number { return this._eventCount; }
  get sessionCount(): number { return this._sessionCount; }
}
