export class SoulBridge {
  private socket: WebSocket | null = null;
  private url: string;
  private messageCallback: ((data: any) => void) | null = null;
  private messageQueue: any[] = []; // Queue messages while connecting
  private _isConnecting: boolean = false;

  constructor() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    this.url = `${protocol}//${host}/ws/soul`;
  }

  public onMessage(callback: (data: any) => void) {
    this.messageCallback = callback;
  }

  public connect(customUrl?: string): Promise<void> {
    return new Promise((resolve, reject) => {
        if (this.isConnected) {
            console.log('[SoulBridge] Already connected, skipping connect');
            return resolve();
        }
        
        if (this._isConnecting) {
            console.log('[SoulBridge] Already connecting, waiting...');
            return;
        }
        
        this._isConnecting = true;
        
        if (customUrl) {
            this.url = customUrl;
        } else {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = window.location.host; 
            this.url = `${protocol}//${host}/ws/soul`;
        }
        
        console.log(`V2 [REL_PROXY] Connecting to FoveAI Soul at ${this.url}...`);
        this.socket = new WebSocket(this.url);

        this.socket.onopen = () => {
            console.log('[SoulBridge] Connected to FoveAI Soul');
            this._isConnecting = false;
            // Send queued messages after connection established
            this.send({ type: 'vessel_connect', vessel: 'WebXR' });
            this.flushQueue();
            resolve();
        };

        this.socket.onmessage = (event) => {
          const data = JSON.parse(event.data);
          this.handleMessage(data);
        };

        this.socket.onclose = () => {
            console.warn('[SoulBridge] Disconnected from FoveAI Soul. Retrying in 5s...');
            this._isConnecting = false;
            setTimeout(() => this.connect(), 5000);
        };

        this.socket.onerror = (error) => {
            console.error('[SoulBridge] WebSocket Error:', error);
            this._isConnecting = false;
            reject(error);
        };
    });
  }

  private handleMessage(data: any) {
    if (this.messageCallback) {
      this.messageCallback(data);
    }
  }

  public send(data: any): boolean {
    // If socket exists and is open, send immediately
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      try {
        this.socket.send(JSON.stringify(data));
        return true;
      } catch (e) {
        console.warn('[SoulBridge] Send error:', e);
        return false;
      }
    }
    
    // If connecting or disconnected, queue message
    if (this._isConnecting || (this.socket && this.socket.readyState === WebSocket.CONNECTING)) {
      this.messageQueue.push(data);
      console.log('[SoulBridge] Message queued while connecting');
      return true;
    }
    
    console.warn('[SoulBridge] Cannot send - not connected');
    return false;
  }
  
  private flushQueue() {
    while (this.messageQueue.length > 0) {
      const data = this.messageQueue.shift();
      if (this.socket && this.socket.readyState === WebSocket.OPEN) {
        try {
          this.socket.send(JSON.stringify(data));
          console.log('[SoulBridge] Sent queued message');
        } catch (e) {
          console.warn('[SoulBridge] Flush send error:', e);
        }
      }
    }
  }

  public get isConnected(): boolean {
    return this.socket !== null && this.socket.readyState === WebSocket.OPEN;
  }
  
  public get isConnecting(): boolean {
    return this._isConnecting;
  }
}

export const soulBridge = new SoulBridge();

// Export convenience functions
export async function connectToSoul(url?: string): Promise<void> {
    return soulBridge.connect(url);
}

export function sendToSoul(data: any): boolean {
    return soulBridge.send(data);
}