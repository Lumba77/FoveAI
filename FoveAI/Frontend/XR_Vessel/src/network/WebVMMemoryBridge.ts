/**
 * WebVM Memory Bridge — SQLite-backed memory vault inside CheerpX Alpine Linux.
 * 
 * Architecture:
 * - Dexie/IndexedDB = fast primary cache (browser-side)
 * - WebVM SQLite = canonical persistent store (survives IndexedDB eviction better)
 * - Chrome Extension = cross-device sync + always-on keepalive
 * 
 * Communication: postMessage ↔ WebVM iframe ↔ CheerpX Linux ↔ sqlite3 CLI
 */

import Dexie from 'dexie';

const WEBVM_IFRAME_ID = 'foveai-webvm-vault';
const WEBVM_ORIGIN = window.location.origin;

interface BridgeMessage {
  type: 'sql_query' | 'sql_exec' | 'sql_result' | 'sql_error' | 'ready' | 'sync_request' | 'sync_data' | 'pong' | 'ping';
  id: string;
  sql?: string;
  params?: any[];
  data?: any;
  error?: string;
}

interface SyncPayload {
  messages: any[];
  entities: any[];
  relations: any[];
  timestamp: number;
}

export class WebVMMemoryBridge {
  private iframe: HTMLIFrameElement | null = null;
  private ready: boolean = false;
  private pendingRequests: Map<string, { resolve: (v: any) => void; reject: (e: any) => void }> = new Map();
  private requestCounter: number = 0;
  private syncInterval: number | null = null;
  private db: Dexie | null = null;

  // Auto-sync configuration
  private SYNC_INTERVAL_MS = 30000; // 30 seconds
  private SYNC_BATCH_SIZE = 100;
  private SERVER_BACKUP_URL = '/api/memory/backup';
  private SERVER_RESTORE_URL = '/api/memory/restore';

  constructor() {}

  /**
   * Initialize the WebVM bridge. Creates the hidden iframe and waits for it to be ready.
   */
  async initialize(db: Dexie): Promise<boolean> {
    this.db = db;

    // Check if WebVM vault is already present
    let iframe = document.getElementById(WEBVM_IFRAME_ID) as HTMLIFrameElement;
    if (!iframe) {
      iframe = document.createElement('iframe');
      iframe.id = WEBVM_IFRAME_ID;
      iframe.src = '/webvm/vault.html';
      iframe.style.display = 'none';
      document.body.appendChild(iframe);
    }
    this.iframe = iframe;

    // Listen for messages from WebVM
    window.addEventListener('message', this.handleMessage.bind(this));

    // Wait for WebVM to signal ready (max 60s)
    const isReady = await this.waitForReady(60000);
    this.ready = isReady;

    if (this.ready) {
      console.log('[WebVM Bridge] Vault ready. Starting periodic sync...');
      this.startPeriodicSync();
    } else {
      console.warn('[WebVM Bridge] Vault did not become ready. Falling back to IndexedDB-only mode.');
    }

    return this.ready;
  }

  /**
   * Execute a SQL statement inside WebVM SQLite.
   */
  async exec(sql: string, params?: any[]): Promise<any> {
    if (!this.ready) {
      throw new Error('WebVM bridge not ready');
    }
    return this.sendRequest({ type: 'sql_exec', id: this.nextId(), sql, params });
  }

  /**
   * Query SQLite and get results back.
   */
  async query(sql: string, params?: any[]): Promise<any[]> {
    if (!this.ready) {
      throw new Error('WebVM bridge not ready');
    }
    return this.sendRequest({ type: 'sql_query', id: this.nextId(), sql, params });
  }

  /**
   * Sync all data from Dexie → WebVM SQLite.
   * This is the "backup" operation.
   */
  async syncToVault(): Promise<{ tables: string[]; rows: number }> {
    if (!this.ready || !this.db) {
      return { tables: [], rows: 0 };
    }

    const syncData: SyncPayload = {
      messages: [],
      entities: [],
      relations: [],
      timestamp: Date.now()
    };

    try {
      // Pull from Dexie tables
      if (this.db.table('messages')) {
        syncData.messages = await this.db.table('messages').toArray();
      }
      if (this.db.table('entities')) {
        syncData.entities = await this.db.table('entities').toArray();
      }
      if (this.db.table('relations')) {
        syncData.relations = await this.db.table('relations').toArray();
      }
    } catch (e) {
      console.warn('[WebVM Bridge] Error reading from Dexie:', e);
    }

    // Send to WebVM vault
    const result = await this.sendRequest({
      type: 'sync_data',
      id: this.nextId(),
      data: syncData
    });

    // Also persist to Chrome Extension storage (if available)
    this.syncToChromeExtension(syncData);

    console.log(`[WebVM Bridge] Synced ${syncData.messages.length} messages, ${syncData.entities.length} entities, ${syncData.relations.length} relations`);
    return result;
  }

  /**
   * Restore data from WebVM SQLite → Dexie.
   * This is the "recovery" operation after browser cleanse.
   */
  async restoreFromVault(): Promise<{ tables: string[]; rows: number }> {
    if (!this.ready || !this.db) {
      return { tables: [], rows: 0 };
    }

    // Request data from WebVM
    const result = await this.sendRequest({
      type: 'sync_request',
      id: this.nextId()
    });

    if (!result || !result.data) {
      console.warn('[WebVM Bridge] No data available in vault for restore');
      return { tables: [], rows: 0 };
    }

    const data: SyncPayload = result.data;
    let totalRows = 0;

    try {
      // Clear and repopulate Dexie tables
      if (data.messages?.length && this.db.table('messages')) {
        await this.db.table('messages').clear();
        await this.db.table('messages').bulkAdd(data.messages);
        totalRows += data.messages.length;
      }
      if (data.entities?.length && this.db.table('entities')) {
        await this.db.table('entities').clear();
        await this.db.table('entities').bulkAdd(data.entities);
        totalRows += data.entities.length;
      }
      if (data.relations?.length && this.db.table('relations')) {
        await this.db.table('relations').clear();
        await this.db.table('relations').bulkAdd(data.relations);
        totalRows += data.relations.length;
      }
    } catch (e) {
      console.error('[WebVM Bridge] Error restoring to Dexie:', e);
    }

    console.log(`[WebVM Bridge] Restored ${totalRows} rows from vault`);
    return { tables: ['messages', 'entities', 'relations'], rows: totalRows };
  }

  /**
   * Check if vault has data (useful for detecting fresh browser after cleanse).
   */
  async vaultHasData(): Promise<boolean> {
    if (!this.ready) return false;
    try {
      const result = await this.query('SELECT COUNT(*) as cnt FROM messages');
      return result?.[0]?.cnt > 0;
    } catch {
      return false;
    }
  }

  /**
   * Sync data to Chrome Extension storage via chrome.storage.local.
   * Chrome Extension storage survives "Clear site data" (different origin scope).
   */
  private async syncToChromeExtension(data: SyncPayload): Promise<void> {
    // Check if Chrome Extension API is available
    if (!(window as any).chrome?.runtime?.sendMessage) return;

    try {
      (window as any).chrome.runtime.sendMessage(
        'foveai-life-bridge', // Extension ID
        {
          action: 'memory_sync',
          data: {
            messages: data.messages.slice(-this.SYNC_BATCH_SIZE), // Last N messages
            entities: data.entities,
            relations: data.relations,
            timestamp: data.timestamp
          }
        },
        (response: any) => {
          if (response?.success) {
            console.log('[WebVM Bridge] Chrome Extension sync OK');
          }
        }
      );
    } catch (e) {
      // Extension not installed or not accessible — silently ignore
    }
  }

  /**
   * Restore data from Chrome Extension storage.
   * Falls back to WebVM vault if Extension data is also empty.
   */
  async restoreFromChromeExtension(): Promise<SyncPayload | null> {
    if (!(window as any).chrome?.runtime?.sendMessage) return null;

    return new Promise((resolve) => {
      try {
        (window as any).chrome.runtime.sendMessage(
          'foveai-life-bridge',
          { action: 'memory_restore' },
          (response: any) => {
            if (response?.success && response?.data) {
              resolve(response.data);
            } else {
              resolve(null);
            }
          }
        );
      } catch {
        resolve(null);
      }
    });
  }

  /**
   * Push memory snapshot to server-side backup endpoint.
   * This is the most resilient backup — survives browser data clearing entirely.
   */
  private async syncToServer(data: SyncPayload): Promise<void> {
    try {
      const response = await fetch(this.SERVER_BACKUP_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      if (response.ok) {
        const result = await response.json();
        console.log(`[WebVM Bridge] Server backup OK: ${result.counts?.messages || 0} msgs`);
      }
    } catch (e) {
      console.debug('[WebVM Bridge] Server backup skipped:', e);
    }
  }

  /**
   * Restore memory from server-side backup.
   * Last-resort restore when both WebVM vault and Chrome Extension are empty.
   */
  async restoreFromServer(): Promise<SyncPayload | null> {
    try {
      const response = await fetch(this.SERVER_RESTORE_URL);
      if (response.ok) {
        const result = await response.json();
        if (result.status === 'ok' && result.data) {
          console.log(`[WebVM Bridge] Server restore available: ${result.counts?.messages || 0} msgs`);
          return result.data;
        }
      }
    } catch (e) {
      console.debug('[WebVM Bridge] Server restore unavailable:', e);
    }
    return null;
  }

  // --- Internal methods ---

  private startPeriodicSync(): void {
    if (this.syncInterval) clearInterval(this.syncInterval);
    this.syncInterval = window.setInterval(() => {
      this.syncToVault().catch(e => console.warn('[WebVM Bridge] Periodic sync failed:', e));
    }, this.SYNC_INTERVAL_MS);

    // Also sync on beforeunload (fire-and-forget)
    window.addEventListener('beforeunload', () => {
      this.syncToVault().catch(() => {});
    });

    // Also use sendBeacon as backup (survives page unload)
    window.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') {
        this.syncToVault().catch(() => {});
      }
    });
  }

  private async waitForReady(timeoutMs: number): Promise<boolean> {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (this.ready) return true;
      // Send ping to WebVM
      this.postMessage({ type: 'ping', id: this.nextId() });
      await new Promise(r => setTimeout(r, 2000));
    }
    return false;
  }

  private handleMessage(event: MessageEvent): void {
    if (event.origin !== WEBVM_ORIGIN && event.origin !== 'null') return; // iframe origins can be 'null'

    const msg = event.data as BridgeMessage;
    if (!msg?.type || !msg?.id) return;

    switch (msg.type) {
      case 'ready':
        this.ready = true;
        console.log('[WebVM Bridge] WebVM vault signaled ready');
        break;
      case 'pong':
        this.ready = true;
        break;
      case 'sql_result':
      case 'sql_error': {
        const pending = this.pendingRequests.get(msg.id);
        if (pending) {
          this.pendingRequests.delete(msg.id);
          if (msg.type === 'sql_error') {
            pending.reject(new Error(msg.error || 'Unknown SQL error'));
          } else {
            pending.resolve(msg.data);
          }
        }
        break;
      }
      case 'sync_data': {
        // Response to sync_request — vault is sending data back
        const pending = this.pendingRequests.get(msg.id);
        if (pending) {
          this.pendingRequests.delete(msg.id);
          pending.resolve(msg);
        }
        break;
      }
    }
  }

  private sendRequest(msg: BridgeMessage): Promise<any> {
    return new Promise((resolve, reject) => {
      this.pendingRequests.set(msg.id, { resolve, reject });
      this.postMessage(msg);

      // Timeout after 15s
      setTimeout(() => {
        if (this.pendingRequests.has(msg.id)) {
          this.pendingRequests.delete(msg.id);
          reject(new Error('WebVM bridge timeout'));
        }
      }, 15000);
    });
  }

  private postMessage(msg: BridgeMessage): void {
    if (this.iframe?.contentWindow) {
      this.iframe.contentWindow.postMessage(msg, '*');
    }
  }

  private nextId(): string {
    return `br_${++this.requestCounter}_${Date.now()}`;
  }

  get isReady(): boolean {
    return this.ready;
  }

  destroy(): void {
    if (this.syncInterval) clearInterval(this.syncInterval);
    window.removeEventListener('message', this.handleMessage.bind(this));
    if (this.iframe) {
      this.iframe.remove();
      this.iframe = null;
    }
    this.ready = false;
  }
}

// Singleton export
export const webVMBridge = new WebVMMemoryBridge();