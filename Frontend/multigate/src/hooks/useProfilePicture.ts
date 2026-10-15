import { useCallback, useEffect, useState } from 'react';

/**
 * useProfilePicture — shared profile-picture state for any surface.
 *
 * Wraps GET/POST /api/profile/picture (auth headers included), file →
 * dataURL, and the cross-window swap event. Uploads COLLECT into the
 * user's gallery (never replace); server tracks the current pointer.
 */
const EVENT = 'foveai_profile_picture_updated';

export function useProfilePicture(apiKey: string | undefined, owner?: 'user' | 'ai_persona') {
  const [url, setUrl] = useState<string | null>(null);
  const [count, setCount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  const baseHeaders = useCallback((): Record<string, string> => (
    apiKey ? { Authorization: `Bearer ${apiKey}` } : {}
  ), [apiKey]);
  // owner='ai_persona' → the shared persona-portrait endpoints (same UX, shared storage)
  const base = owner === 'ai_persona' ? '/api/profile/persona_picture' : '/api/profile/picture';
  const auth = useCallback((): RequestInit => ({ headers: baseHeaders() }), [baseHeaders]);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch(`${base}`, {
        ...auth(),
        signal: AbortSignal.timeout(5000),
      });
      if (!r.ok) return;
      const d = await r.json();
      if (d.url) { setUrl(d.url); setCount(d.total || 0); }
    } catch { /* best-effort */ }
  }, [auth, base]);

  useEffect(() => {
    if (!apiKey) { setUrl(null); setCount(0); return; }
    refresh();
  }, [apiKey, refresh]);

  // Instant swap when any surface uploads
  useEffect(() => {
    const onUpdate = (e: Event) => {
      const u = (e as CustomEvent).detail?.url;
      if (u) { setUrl(`${u}?t=${Date.now()}`); refresh(); }
    };
    window.addEventListener(EVENT, onUpdate);
    return () => window.removeEventListener(EVENT, onUpdate);
  }, [refresh]);

  const upload = useCallback(async (file: File): Promise<boolean> => {
    setBusy(true); setMsg('');
    try {
      const dataUrl: string = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result as string);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
      const r = await fetch(`${base}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
        },
        body: JSON.stringify({ data: dataUrl, name: 'profile' }),
      });
      const d = await r.json();
      if (!r.ok || !d.ok) throw new Error(d.error || `HTTP ${r.status}`);
      setUrl(`${d.url}?t=${Date.now()}`);
      setCount(d.total || 0);
      setMsg(`✓ Added to collection (#${d.total})`);
      window.dispatchEvent(new CustomEvent(EVENT, { detail: { url: d.url } }));
      return true;
    } catch (err: any) {
      setMsg(`✕ ${err.message}`);
      return false;
    } finally {
      setBusy(false);
    }
  }, [apiKey, base]);

  return { url, count, busy, msg, upload, refresh, setMsg };
}
