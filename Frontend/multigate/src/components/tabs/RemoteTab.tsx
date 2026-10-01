import React, { useState, useEffect, useCallback } from 'react';

interface RemoteService {
  id: string;
  label: string;
  unit: string | null;
  scope: 'user' | 'system' | 'process';
  status: string;
  reachable: boolean | null;
}

const isUp = (s: RemoteService) => s.status === 'active' && s.reachable !== false;

export const RemoteTab: React.FC = () => {
  const [services, setServices] = useState<RemoteService[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState('');
  const [showDesktop, setShowDesktop] = useState(true);

  const host = window.location.hostname;

  const refresh = useCallback(async () => {
    try {
      const res = await fetch('/remote-api/services');
      if (res.ok) {
        const data = await res.json();
        setServices(data.services || []);
      }
    } catch (e) {
      console.warn('remote-api unavailable', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, [refresh]);

  const act = async (id: string, action: 'start' | 'stop' | 'restart') => {
    setBusy(`${id}:${action}`);
    setNotice('');
    try {
      const res = await fetch(`/remote-api/services/${id}/${action}`, { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        setNotice(`⚠ ${id}: ${data.error || data.detail || `HTTP ${res.status}`}`);
      }
    } catch (e) {
      setNotice(`⚠ ${id}: ${String(e)}`);
    } finally {
      setBusy(null);
      setTimeout(refresh, 1200);
    }
  };

  const svc = (id: string) => services.find(s => s.id === id);
  const novncUp = svc('novnc') ? isUp(svc('novnc')!) : true; // assume up until proven otherwise
  const sunshineUp = svc('sunshine') ? isUp(svc('sunshine')!) : false;
  const rdpWebUp = svc('remoteweb') ? isUp(svc('remoteweb')!) && svc('guacd')?.status === 'active' : false;

  const CONNECTIONS = [
    {
      icon: '⌨️', name: 'Web Terminal (ttyd)', type: 'Shell in the browser — no client needed',
      address: `http://${host}:7681`, action: 'link', note: 'Works from the Quest browser over WiFi. Sign in as lumba; password is the ttyd credential in /etc/default/ttyd.'
    },
    {
      icon: '🖥️', name: 'noVNC — Browser Desktop', type: 'Physical session (mirrors monitor)',
      address: `/novnc/vnc.html`, action: 'open', note: 'Embedded below — same session as the physical screen. Also reachable at novnc.xarel.net.'
    },
    {
      icon: '🪟', name: 'Web RDP — Browser Desktop', type: 'Separate virtual session, in-browser',
      address: `/rdp/`, action: rdpWebUp ? 'open' : 'info',
      note: rdpWebUp
        ? 'Fresh login session in the browser (guacd → xrdp). Sign in with your Linux account.'
        : svc('guacd')?.status === 'active'
          ? 'guacd is up — start "Web RDP client (:6081)" below, then this card opens /rdp/.'
          : 'Browser RDP needs guacd — run: sudo apt install -y guacd && sudo systemctl enable --now guacd'
    },
    {
      icon: '☀️', name: 'Sunshine Web UI', type: 'Pairing & settings console',
      address: `https://${host}:47990`, action: 'link', note: 'Pair Moonlight clients here (PIN tab). Forget old PC entries first — certs changed after migration.'
    },
    {
      icon: '🎮', name: 'Moonlight / Nightfall', type: 'Physical session, low latency (native app)',
      address: `Add PC: ${host}`, action: 'info', note: 'Browser client (moonlight-web) not installed yet — use the native app or the Quest client.'
    },
    {
      icon: '🪟', name: 'RDP (xrdp)', type: 'Separate virtual session (native client)',
      address: `${host}:3389`, action: 'info', note: 'Fresh login session — works from cold boot. Point any RDP client (Windows mstsc, Remmina, Microsoft RD on Quest) here.'
    },
    {
      icon: '🌐', name: 'Chrome Remote Desktop', type: 'Separate virtual session (Cinnamon)',
      address: 'https://remotedesktop.google.com/access', action: 'link', note: 'Host "foveai" is registered — start it from the service controls below, then connect from the console.'
    },
  ];

  const statusDot = (s: RemoteService) => {
    const up = isUp(s);
    return (
      <span
        title={`${s.status}${s.reachable === false ? ' (port not reachable)' : ''}`}
        style={{
          display: 'inline-block', width: '9px', height: '9px', borderRadius: '50%',
          background: up ? 'var(--neon-green, #39ff88)' : s.status === 'activating' ? '#ffb020' : '#ff4d6d',
          boxShadow: `0 0 6px ${up ? 'rgba(57,255,136,0.7)' : s.status === 'activating' ? 'rgba(255,176,32,0.7)' : 'rgba(255,77,109,0.5)'}`,
          marginRight: '8px', flexShrink: 0
        }}
      />
    );
  };

  return (
    <div style={{ display: 'flex', gap: '16px', height: '100%', width: '100%', padding: '16px', boxSizing: 'border-box', overflow: 'hidden', background: '#02050a' }}>

      {/* LEFT: Embedded desktop stream */}
      <div style={{ flex: '1.5', minWidth: 0, display: 'flex', flexDirection: 'column', height: '100%', background: 'rgba(5, 12, 22, 0.7)', border: '1px solid rgba(0, 229, 255, 0.15)', borderRadius: '8px', boxShadow: '0 8px 32px rgba(0, 0, 0, 0.6)', overflow: 'hidden' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', borderBottom: '1px solid rgba(0, 229, 255, 0.15)', background: '#0a1322' }}>
          <div style={{ fontFamily: 'Orbitron', fontSize: '0.68rem', color: 'var(--accent-cyan)', letterSpacing: '1px' }}>
            🖥️ LIVE DESKTOP — :0 PHYSICAL SESSION
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => setShowDesktop(v => !v)}
              style={{ background: 'rgba(0,0,0,0.5)', color: 'var(--accent-cyan)', border: '1px solid var(--accent-cyan)', borderRadius: '4px', padding: '4px 10px', fontSize: '0.65rem', cursor: 'pointer', fontFamily: 'Share Tech Mono' }}
            >
              {showDesktop ? '⏸ Hide Stream' : '▶ Show Stream'}
            </button>
            <a
              href="/novnc/vnc.html?autoconnect=true&resize=scale&reconnect=true"
              target="_blank"
              rel="noreferrer"
              style={{ background: 'rgba(0,0,0,0.5)', color: 'var(--accent-cyan)', border: '1px solid var(--accent-cyan)', borderRadius: '4px', padding: '4px 10px', fontSize: '0.65rem', cursor: 'pointer', fontFamily: 'Share Tech Mono', textDecoration: 'none' }}
            >
              ↗ Fullscreen
            </a>
          </div>
        </div>

        {showDesktop ? (
          novncUp ? (
            <iframe
              src="/novnc/vnc.html?autoconnect=true&resize=scale&reconnect=true"
              style={{ flex: 1, width: '100%', border: 'none', background: '#000' }}
              title="noVNC — physical desktop"
            />
          ) : (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '12px', color: 'var(--text-muted)', fontFamily: 'Share Tech Mono', fontSize: '0.8rem' }}>
              <div>noVNC service is not running.</div>
              <button
                onClick={() => act('novnc', 'start')}
                disabled={busy !== null}
                style={{ padding: '8px 18px', background: 'var(--accent-cyan)', color: '#000', border: 'none', borderRadius: '4px', fontWeight: 'bold', fontSize: '0.72rem', cursor: 'pointer' }}
              >
                {busy === 'novnc:start' ? 'STARTING…' : '▶ START noVNC'}
              </button>
            </div>
          )
        ) : (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontFamily: 'Share Tech Mono', fontSize: '0.75rem' }}>
            Stream hidden — click "Show Stream" to resume.
          </div>
        )}
      </div>

      {/* RIGHT: Connection options + service controls */}
      <div style={{ flex: '0.85', display: 'flex', flexDirection: 'column', gap: '12px', overflowY: 'auto', minWidth: '320px' }}>

        {/* Header */}
        <div style={{ background: 'rgba(0, 229, 255, 0.03)', border: '1px solid rgba(0, 229, 255, 0.2)', padding: '14px 16px', borderRadius: '8px' }}>
          <div className="breadcrumb" style={{ fontSize: '0.75rem', color: 'var(--accent-cyan)', letterSpacing: '1px' }}>
            REMOTE ACCESS
          </div>
          <div style={{ fontSize: '0.72rem', opacity: 0.8, color: 'var(--text-muted)', marginTop: '6px', lineHeight: '1.4' }}>
            All ways into this machine. Physical-session tools show the real screen; virtual-session tools spawn a fresh login.
          </div>
          <div style={{ fontSize: '0.65rem', color: 'var(--accent-cyan)', fontFamily: 'Share Tech Mono', marginTop: '8px', padding: '6px 8px', background: 'rgba(0,229,255,0.06)', border: '1px solid rgba(0,229,255,0.15)', borderRadius: '4px' }}>
            📡 LAN name: <strong>foveai.local</strong> — survives router IP changes
          </div>
        </div>

        {/* Connection options */}
        <div style={{ background: 'rgba(0, 229, 255, 0.02)', border: '1px solid rgba(0, 229, 255, 0.15)', padding: '14px 16px', borderRadius: '8px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ fontFamily: 'Orbitron', fontSize: '0.65rem', color: 'var(--accent-cyan)', letterSpacing: '1px' }}>
            🔗 CONNECTION OPTIONS
          </div>
          {CONNECTIONS.map((c) => (
            <div key={c.name} style={{ background: 'rgba(0,0,0,0.35)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '6px', padding: '10px 12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px' }}>
                <div style={{ fontSize: '0.78rem', color: '#e0f8ff', fontWeight: 600 }}>{c.icon} {c.name}</div>
                {c.action === 'open' && (
                  <a href={c.address} target="_blank" rel="noreferrer" style={{ fontSize: '0.62rem', color: 'var(--accent-cyan)', border: '1px solid var(--accent-cyan)', borderRadius: '4px', padding: '2px 8px', textDecoration: 'none', whiteSpace: 'nowrap' }}>Open ↗</a>
                )}
                {c.action === 'link' && (
                  <a href={c.address} target="_blank" rel="noreferrer" style={{ fontSize: '0.62rem', color: 'var(--accent-cyan)', border: '1px solid var(--accent-cyan)', borderRadius: '4px', padding: '2px 8px', textDecoration: 'none', whiteSpace: 'nowrap' }}>Open ↗</a>
                )}
              </div>
              <div style={{ fontSize: '0.62rem', color: 'var(--accent-purple)', fontFamily: 'Share Tech Mono', marginTop: '3px' }}>{c.type}</div>
              <div style={{ fontSize: '0.68rem', color: 'var(--accent-cyan)', fontFamily: 'Share Tech Mono', marginTop: '4px', wordBreak: 'break-all' }}>{c.address}</div>
              <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: '4px', lineHeight: '1.4' }}>{c.note}</div>
            </div>
          ))}
          {sunshineUp && (
            <a
              href={`https://${host}:47990`}
              target="_blank"
              rel="noreferrer"
              style={{ fontSize: '0.65rem', color: 'var(--accent-cyan)', textAlign: 'center', padding: '6px', border: '1px dashed rgba(0,229,255,0.3)', borderRadius: '6px', textDecoration: 'none' }}
            >
              ☀️ Sunshine Web UI — https://{host}:47990
            </a>
          )}
        </div>

        {/* Service controls */}
        <div style={{ background: 'rgba(157, 78, 221, 0.02)', border: '1px solid rgba(157, 78, 221, 0.2)', padding: '14px 16px', borderRadius: '8px', display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ fontFamily: 'Orbitron', fontSize: '0.65rem', color: 'var(--accent-purple)', letterSpacing: '1px' }}>
              ⚙️ SERVER SERVICES
            </div>
            <button
              onClick={refresh}
              style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.75rem' }}
              title="Refresh status"
            >
              ↻
            </button>
          </div>

          {loading ? (
            <div style={{ color: 'var(--text-muted)', fontFamily: 'Share Tech Mono', fontSize: '0.7rem', padding: '8px 0' }}>Probing services…</div>
          ) : services.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontFamily: 'Share Tech Mono', fontSize: '0.7rem', padding: '8px 0' }}>remote-api unreachable — is the Multigate dev server current?</div>
          ) : services.map((s) => (
            <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'rgba(0,0,0,0.35)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '6px', padding: '8px 10px' }}>
              {statusDot(s)}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: '0.72rem', color: '#e0f8ff', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.label}</div>
                <div style={{ fontSize: '0.58rem', color: 'var(--text-muted)', fontFamily: 'Share Tech Mono' }}>
                  {s.status}{s.reachable === false ? ' · port down' : ''}{s.scope === 'system' ? ' · system' : ''}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
                {s.status !== 'active' && (
                  <button
                    onClick={() => act(s.id, 'start')}
                    disabled={busy !== null}
                    style={{ padding: '3px 8px', background: 'rgba(57,255,136,0.12)', border: '1px solid rgba(57,255,136,0.4)', color: 'var(--neon-green, #39ff88)', borderRadius: '4px', fontSize: '0.62rem', cursor: 'pointer', fontFamily: 'Share Tech Mono' }}
                  >
                    {busy === `${s.id}:start` ? '…' : '▶'}
                  </button>
                )}
                <button
                  onClick={() => act(s.id, 'restart')}
                  disabled={busy !== null}
                  style={{ padding: '3px 8px', background: 'rgba(0,229,255,0.08)', border: '1px solid rgba(0,229,255,0.35)', color: 'var(--accent-cyan)', borderRadius: '4px', fontSize: '0.62rem', cursor: 'pointer', fontFamily: 'Share Tech Mono' }}
                >
                  {busy === `${s.id}:restart` ? '…' : '↻'}
                </button>
                {s.status === 'active' && (
                  <button
                    onClick={() => act(s.id, 'stop')}
                    disabled={busy !== null}
                    style={{ padding: '3px 8px', background: 'rgba(255,77,109,0.08)', border: '1px solid rgba(255,77,109,0.35)', color: '#ff4d6d', borderRadius: '4px', fontSize: '0.62rem', cursor: 'pointer', fontFamily: 'Share Tech Mono' }}
                  >
                    {busy === `${s.id}:stop` ? '…' : '⏹'}
                  </button>
                )}
              </div>
            </div>
          ))}

          {notice && (
            <div style={{ fontSize: '0.65rem', color: '#ffb020', fontFamily: 'Share Tech Mono', padding: '6px 8px', background: 'rgba(255,176,32,0.06)', border: '1px solid rgba(255,176,32,0.25)', borderRadius: '6px' }}>
              {notice}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default RemoteTab;
