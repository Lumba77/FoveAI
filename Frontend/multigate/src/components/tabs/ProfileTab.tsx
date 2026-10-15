import { useState, useEffect, useRef } from 'react';
import { useProfilePicture } from '../../hooks/useProfilePicture';

interface GalleryImage {
  file: string;
  url: string;
  added: string | null;
  visibility: string;
}

/**
 * ProfileTab — the user's own surface: portrait, identity, gallery.
 *
 * The gallery strip lists the user's collected images; any portrait can be
 * made the current profile picture (uploads COLLECT — nothing is replaced).
 */
export function ProfileTab({ currentUser }: { currentUser: { username: string; firstName?: string; lastName?: string; apiKey?: string } | null }) {
  const pfp = useProfilePicture(currentUser?.apiKey);
  const [gallery, setGallery] = useState<GalleryImage[]>([]);
  const [name, setName] = useState(currentUser?.firstName || '');
  const [saved, setSaved] = useState(false);
  const [pfpPointer, setPfpPointer] = useState<string>('');
  const fileRef = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    // mirror the current pointer name for gallery highlight
    if (pfp.url) setPfpPointer(decodeURIComponent(pfp.url.split('/').pop() || '').split('?')[0]);
  }, [pfp.url]);

  useEffect(() => {
    fetch('/api/tools/images', {
      headers: currentUser?.apiKey ? { Authorization: `Bearer ${currentUser.apiKey}` } : undefined as any,
      signal: AbortSignal.timeout(6000),
    })
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (d?.gallery) setGallery(d.gallery); })
      .catch(() => {});
  }, [currentUser?.apiKey, pfp.count]);

  // Self-service name patch (server allows displayName for non-admins)
  const saveName = async () => {
    try {
      const r = await fetch(`/api/auth/users/${currentUser?.username}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${currentUser?.apiKey}` },
        body: JSON.stringify({ displayName: name }),
      });
      if (r.ok) { setSaved(true); setTimeout(() => setSaved(false), 2000); }
    } catch { /* best-effort */ }
  };

  return (
    <div style={{ padding: '20px', height: '100%', overflowY: 'auto' }}>
      <div className="breadcrumb">PROFILE // USER_IDENTITY</div>
      <p style={{ fontSize: '0.75rem', opacity: 0.7, marginBottom: '16px', color: 'var(--neon-blue)' }}>
        Your portrait, names, and the collected picture gallery.
      </p>

      {/* Identity card: portrait + names */}
      <div style={{ display: 'flex', gap: '18px', marginBottom: '22px', alignItems: 'flex-start' }}>
        <div
          title="Click to upload a new portrait — joins your collection"
          onClick={() => fileRef.current?.click()}
          style={{
            width: 88, height: 118, borderRadius: 12, overflow: 'hidden', cursor: 'pointer', flexShrink: 0,
            boxShadow: 'inset 4px 4px 10px rgba(0,0,0,0.9), inset -2px -2px 5px rgba(255,255,255,0.05)',
            background: 'rgba(10,12,8,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
            border: '1px solid rgba(255, 184, 0, 0.25)',
          }}
        >
          {pfp.url ? (
            <img src={pfp.url} alt="Profile" style={{ width: '100%', height: '100%', objectFit: 'cover' }} key={pfp.url} />
          ) : (
            <div style={{ fontSize: '1.6rem', opacity: 0.4 }}>👤</div>
          )}
        </div>
        <div style={{ flex: 1 }}>
          <h4 style={{ fontFamily: 'Orbitron', margin: '0 0 8px', fontSize: '0.85rem', color: '#ffb800', letterSpacing: '1px' }}>
            USER IDENTITY {currentUser?.username?.toUpperCase()}
          </h4>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Display name..."
              style={{
                background: 'rgba(11,15,26,0.6)', border: '1px solid rgba(255, 184, 0, 0.3)',
                color: 'var(--text-primary)', padding: '6px 10px', borderRadius: 5, fontSize: '0.8rem', minWidth: 180,
              }}
            />
            <button
              onClick={saveName}
              style={{
                cursor: 'pointer', padding: '6px 14px', borderRadius: 5, fontSize: '0.75rem',
                border: '1px solid rgba(0, 243, 255, 0.4)', background: 'rgba(0, 243, 255, 0.08)', color: '#00f3ff',
              }}
            >
              Save
            </button>
            {saved && <span style={{ color: '#5dff8f', fontSize: '0.72rem' }}>✓ saved</span>}
          </div>
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            style={{ display: 'none' }}
            onChange={async (e) => {
              const f = e.target.files?.[0];
              if (f) await pfp.upload(f);
              if (e.target) e.target.value = '';
            }}
          />
          {pfp.msg && <div style={{ fontSize: '0.72rem', marginTop: 8, color: pfp.msg.startsWith('✓') ? '#5dff8f' : '#ff6b6b' }}>{pfp.msg}</div>}
        </div>
      </div>

      {/* Gallery strip — click any portrait to make it current */}
      <h4 style={{ fontFamily: 'Orbitron', margin: '0 0 8px', fontSize: '0.8rem', color: '#00f3ff', letterSpacing: '1px' }}>
        🖼️ YOUR COLLECTION ({gallery.length})
      </h4>
      <p style={{ fontSize: '0.7rem', opacity: 0.6, margin: '0 0 10px' }}>
        Every upload is kept. Click an image to make it your current portrait.
      </p>
      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
        {gallery.map(g => (
          <div
            key={g.file}
            title={pfp.url?.includes(g.file) ? 'Current portrait' : 'Click to use as portrait'}
            onClick={async () => {
              // PATCH the pointer: re-upload pointer via auth manager profilePicture isn't
              // exposed per-file UX yet — simplest flow: refetch + server picks latest current.
              // For now: selecting marks it visually; pointer flips via profile endpoint below.
              setPfpPointer(g.file);
              fetch('/api/profile/picture/select', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${currentUser?.apiKey}` },
                body: JSON.stringify({ file: g.file }),
              }).then(() => pfp.refresh()).catch(() => {});
            }}
            style={{
              width: 64, height: 84, borderRadius: 8, overflow: 'hidden', cursor: 'pointer',
              border: pfpPointer === g.file ? '2px solid #ffb800' : '1px solid rgba(255,255,255,0.12)',
              boxShadow: pfpPointer === g.file ? '0 0 12px rgba(255,184,0,0.25)' : 'none',
            }}
          >
            <img src={g.url} alt={g.file} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          </div>
        ))}
        {gallery.length === 0 && (
          <div style={{ fontSize: '0.72rem', opacity: 0.5 }}>No collected pictures yet — upload above.</div>
        )}
      </div>
    </div>
  );
}
