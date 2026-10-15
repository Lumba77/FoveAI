/**
 * SCREEN WATCH - Avatar co-watches user's screen
 * Captures display via getDisplayMedia, downloads subtitles from OpenSubtitles
 */
export interface ScreenFrame {
  base64: string;
  timestamp: number;
  contentType: 'movie' | 'website' | 'image' | 'game' | 'code' | 'document' | 'unknown';
  text: string;
  subtitle: string | null;
  mediaTitle: string | null;
}
export interface ScreenWatchConfig {
  captureIntervalMs: number;
  jpegQuality: number;
  enableOcr: boolean;
  autoDownloadSubtitles: boolean;
  subtitleLang: string;
}
const DC: ScreenWatchConfig = {
  captureIntervalMs: 5000, jpegQuality: 0.7,
  enableOcr: true, autoDownloadSubtitles: true, subtitleLang: 'en',
};
const OS_SUB = 'https://api.opensubtitles.com/api/v1';

function classifyTitle(title: string): ScreenFrame['contentType'] {
  const t = title.toLowerCase();
  if (/youtube|netflix|prime\.video|plex|hbo|disney/i.test(t)) return 'movie';
  if (/github|vscode|stackoverflow|gitlab/i.test(t)) return 'code';
  if (/docs|notion|sheets/i.test(t)) return 'document';
  if (/photos|imgur/i.test(t)) return 'image';
  return 'unknown';
}
function parseSrt(srt: string): string[] {
  const r: string[] = [];
  for (const b of srt.split(/\n\n+/)) {
    const t = b.split('\n').slice(2).join(' ').replace(/<[^>]+>/g, '').trim();
    if (t) r.push(t);
  }
  return r;
}

export class ScreenWatch {
  private cfg = DC;
  private video: HTMLVideoElement | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private timer: number | null = null;
  private active = false;
  private last: ScreenFrame | null = null;
  private subs: string[] = [];
  private title: string | null = null;
  private log = (m: string, _c: string) => console.log('[SW] ' + m);

  constructor(cfg?: Partial<ScreenWatchConfig>, lf?: (m: string, c: string) => void) {
    if (cfg) this.cfg = { ...this.cfg, ...cfg };
    if (lf) this.log = lf;
  }

  async start(): Promise<boolean> {
    try {
      const s = await (navigator as any).mediaDevices.getDisplayMedia({
        video: { width: { ideal: 1920 }, height: { ideal: 1080 }, frameRate: { ideal: 5 } },
        audio: true,
      });
      this.video = document.createElement('video');
      this.video.autoplay = true; this.video.muted = true; this.video.playsInline = true;
      this.video.srcObject = s; await this.video.play();
      this.canvas = document.createElement('canvas');
      this.canvas.width = 1280; this.canvas.height = 720;
      this.ctx = this.canvas.getContext('2d'); this.active = true;
      this.timer = window.setInterval(() => this.capture(), this.cfg.captureIntervalMs);
      this.capture(); this.log('Screen Watch active', '#0f0');
      return true;
    } catch (e: any) {
      this.log('Denied: ' + e.message, '#f80');
      return false;
    }
  }

  stop(): void {
    this.active = false;
    if (this.timer) { clearInterval(this.timer); this.timer = null; }
    if (this.video && this.video.srcObject) {
      (this.video.srcObject as MediaStream).getTracks().forEach((t: any) => t.stop());
    }
    this.video = null; this.canvas = null; this.ctx = null;
  }

  getLastFrame(): ScreenFrame | null { return this.last; }

  private capture(): void {
    if (!this.active || !this.video || !this.ctx || !this.canvas) return;
    try {
      this.ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
      const b64 = this.canvas.toDataURL('image/jpeg', this.cfg.jpegQuality).split(',')[1] || '';
      const ct = classifyTitle(document.title);
      let sub: string | null = null;
      if (ct === 'movie' && this.subs.length) sub = this.matchSub();
      this.last = {
        base64: b64, timestamp: Date.now(), contentType: ct,
        text: '', subtitle: sub, mediaTitle: this.title,
      };
    } catch (e: any) {}
  }

  async downloadSubtitles(title: string, season?: number, episode?: number): Promise<boolean> {
    if (!this.cfg.autoDownloadSubtitles) return false;
    try {
      this.title = title;
      const p = new URLSearchParams({ query: title, languages: this.cfg.subtitleLang, order_by: 'download_count' });
      if (season !== undefined) p.set('season_number', String(season));
      if (episode !== undefined) p.set('episode_number', String(episode));
      const r = await fetch(OS_SUB + '/subtitles?' + p, { headers: { 'Content-Type': 'application/json' } });
      if (r.ok) {
        const d = await r.json();
        if (d.data && d.data.length) {
          const dr = await fetch(OS_SUB + '/subtitles/' + d.data[0].id + '/download', { headers: { 'Content-Type': 'application/json' } });
          if (dr.ok) {
            const sd = await dr.json();
            this.subs = sd.content ? parseSrt(sd.content) : [];
            return true;
          }
        }
      }
      return false;
    } catch (e: any) { return false; }
  }

  private matchSub(): string | null {
    if (!this.subs.length) return null;
    const elapsed = ((Date.now() - (this.last?.timestamp || Date.now())) / 1000);
    return this.subs[Math.floor(elapsed / 3) % this.subs.length] || null;
  }

  getContext(): string {
    if (!this.last) return '[SCREEN WATCH] Offline.';
    let l = '[SCREEN WATCH] ' + this.last.contentType.toUpperCase();
    if (this.last.mediaTitle) l += ' "' + this.last.mediaTitle + '"';
    if (this.last.subtitle) l += ' sub:"' + this.last.subtitle.substring(0, 80) + '"';
    const age = Math.round((Date.now() - this.last.timestamp) / 1000);
    l += ' (' + age + 's ago)';
    return l;
  }

  isRunning(): boolean { return this.active; }
  dispose(): void { this.stop(); }
}
