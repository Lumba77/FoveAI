/**
 * SystemsTab.tsx — "Zabbix light": a live status board of every FoveAI
 * subsystem plus the remote-access stack. Polls /api/subsystems (server-side
 * probes, so remote clients see the PC's real states) every 5s and renders
 * service cards grouped by domain with the ignition palette:
 *   green = online, cyan = listening, yellow = dormant, grey = offline.
 */

import React, { useEffect, useState } from 'react';

interface Check {
  name: string;
  port: number;
  group?: 'stack' | 'web' | 'remote' | 'machine';
  state: 'online' | 'listening' | 'dormant' | 'offline';
  http_status?: number;
  model?: string;
  loaded?: boolean;
  load_state?: string;
  load_error?: string | null;
}

const GROUPS: Record<string, { title: string; icon: string }> = {
  stack:   { title: 'FOVEAI STACK',    icon: '🧠' },
  web:     { title: 'WEB SURFACES',    icon: '🌐' },
  remote:  { title: 'REMOTE ACCESS',   icon: '📡' },
  machine: { title: 'MACHINE',         icon: '📈' },
};

const STATE_STYLE: Record<string, { color: string; label: string }> = {
  online:    { color: '#50fa7b', label: 'ONLINE' },
  listening: { color: '#00eaff', label: 'LISTENING' },
  dormant:   { color: '#f1fa8c', label: 'DORMANT' },
  offline:   { color: '#666',    label: 'OFFLINE' },
};

function getToken(): string {
  try { return JSON.parse(localStorage.getItem('foveai_foveai_user') || '{}').apiKey || ''; }
  catch { return ''; }
}

export const SystemsTab: React.FC = () => {
  const [checks, setChecks] = useState<Check[]>([]);
  const [lastPoll, setLastPoll] = useState<Date | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const r = await fetch('/api/foveated/api/subsystems', {
          headers: { Authorization: `Bearer ${getToken()}` },
        });
        if (!r.ok) throw new Error(`${r.status}`);
        const data = await r.json();
        if (alive) { setChecks(data.checks || []); setLastPoll(new Date()); setError(''); }
      } catch (e: any) {
        if (alive) setError(e.message);
      }
    };
    poll();
    const t = setInterval(poll, 5000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const counts = checks.reduce((acc, c) => {
    acc[c.state] = (acc[c.state] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div style={{ height: '100%', overflowY: 'auto', background: '#0a0a0f', color: '#e0e0e0', padding: 16 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <span style={{ fontSize: '1.3rem' }}>🛰️</span>
        <div>
          <div style={{ fontWeight: 700, fontSize: '1rem', color: '#00eaff' }}>Systems Board</div>
          <div style={{ fontSize: '0.72rem', color: '#777' }}>
            {error ? `probe error: ${error}` : lastPoll ? `polled ${lastPoll.toLocaleTimeString()} · ${checks.length} services` : 'probing…'}
          </div>
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', gap: 10, fontSize: '0.72rem' }}>
          {Object.entries(counts).map(([s, n]) => (
            <span key={s} style={{ color: STATE_STYLE[s]?.color }}>{n} {STATE_STYLE[s]?.label.toLowerCase()}</span>
          ))}
        </div>
      </div>

      {/* Groups */}
      {Object.entries(GROUPS).map(([g, meta]) => {
        const items = checks.filter(c => (c.group || 'stack') === g);
        if (!items.length) return null;
        return (
          <div key={g} style={{ marginBottom: 18 }}>
            <div style={{ fontSize: '0.7rem', letterSpacing: '1.5px', color: '#888', marginBottom: 8 }}>
              {meta.icon} {meta.title}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))', gap: 8 }}>
              {items.map(c => {
                const st = STATE_STYLE[c.state] || STATE_STYLE.offline;
                return (
                  <div key={c.name} style={{
                    background: 'rgba(255,255,255,0.025)', border: '1px solid rgba(255,255,255,0.07)',
                    borderLeft: `3px solid ${st.color}`, borderRadius: 6, padding: '9px 12px',
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                      <span style={{ fontSize: '0.83rem', fontWeight: 600 }}>{c.name}</span>
                      <span style={{ fontSize: '0.65rem', color: st.color, fontWeight: 700 }}>{st.label}</span>
                    </div>
                    <div style={{ fontSize: '0.68rem', color: '#777', marginTop: 3 }}>
                      :{c.port}{c.http_status ? ` · http ${c.http_status}` : ''}
                    </div>
                    {c.model && (
                      <div style={{ fontSize: '0.68rem', color: '#9aa', marginTop: 3 }}>
                        {c.model} {c.load_state ? `· ${c.load_state}` : ''}
                      </div>
                    )}
                    {c.load_error && (
                      <div style={{ fontSize: '0.68rem', color: '#ff6b6b', marginTop: 3 }}>⚠ {c.load_error}</div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
};
