/**
    * COMMS BRIDGE - Avatar handles user's email, SMS, and phone calls.
        * Connects through the user's phone via the Mobile_Vessel bridge,
            * or directly via Gmail / Outlook APIs for email.
 *
 * Voice: Can answer calls for the user(with consent) using VoiceClone.
 * SMS: Read / respond to text messages via phone bridge.
 * Email: Read / write email via Gmail API or IMAP.
 */
export interface Email { id: string; from: string; subject: string; snippet: string; body: string; date: string; }
export interface SmsMessage { from: string; body: string; timestamp: number; read: boolean; }
export interface CallInfo { number: string; name: string | null; timestamp: number; duration: number; missed: boolean; }

const API = '/api/comms';

export class CommsBridge {
    private log: (m: string, c: string) => void;

    constructor(logFn?: (m: string, c: string) => void) {
        this.log = logFn || ((m, c) => console.log('[Comms] ' + m));
    }

    // ── EMAIL ──
    async listEmails(maxResults = 10): Promise<Email[]> {
        try {
            const r = await fetch(`${API}/email/list?max=${maxResults}`);
            return r.ok ? ((await r.json()).emails || []) : [];
        } catch { return []; }
    }

    async sendEmail(to: string, subject: string, body: string): Promise<boolean> {
        try {
            const r = await fetch(`${API}/email/send`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ to, subject, body }),
            });
            if (r.ok) this.log(`Email sent to ${to}`, '#0f0');
            return r.ok;
        } catch { return false; }
    }

    async readEmail(id: string): Promise<string | null> {
        try {
            const r = await fetch(`${API}/email/read?id=${encodeURIComponent(id)}`);
            return r.ok ? ((await r.json()).body || null) : null;
        } catch { return null; }
    }

    // ── SMS (via phone bridge) ──
    async listSms(maxResults = 10): Promise<SmsMessage[]> {
        try {
            const r = await fetch(`${API}/sms/list?max=${maxResults}`);
            return r.ok ? ((await r.json()).messages || []) : [];
        } catch { return []; }
    }

    async sendSms(to: string, body: string): Promise<boolean> {
        try {
            const r = await fetch(`${API}/sms/send`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ to, body }),
            });
            if (r.ok) this.log(`SMS sent to ${to}`, '#0f0');
            return r.ok;
        } catch { return false; }
    }

    // ── CALLS ──
    async getRecentCalls(): Promise<CallInfo[]> {
        try {
            const r = await fetch(`${API}/calls/recent`);
            return r.ok ? ((await r.json()).calls || []) : [];
        } catch { return []; }
    }

    /** Answer a call and speak as the user (uses VoiceClone for TTS). */
    async answerCall(callId: string, greeting: string, useUserVoice = true): Promise<boolean> {
        try {
            const r = await fetch(`${API}/calls/answer`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ callId, greeting, useUserVoice }),
            });
            if (r.ok) this.log('Answered call as user', '#0f0');
            return r.ok;
        } catch { return false; }
    }

    // ── WHATSAPP / TELEGRAM BRIDGE ──
    /** Send a WhatsApp message (via linked phone). */
    async sendWhatsApp(to: string, body: string): Promise<boolean> {
        try {
            const r = await fetch(`${API}/whatsapp/send`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ to, body }),
            });
            return r.ok;
        } catch { return false; }
    }

    getContext(): string {
        return '[COMMS BRIDGE] Email (read/send), SMS, calls, WhatsApp available. Can answer phone as user (voice cloned).';
    }
}
