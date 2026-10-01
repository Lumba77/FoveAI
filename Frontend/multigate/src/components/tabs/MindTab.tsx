import React, { useState, useEffect } from 'react';

interface AgentStatus {
  running: boolean;
  mode: string;
  loop_interval: number;
  last_user_message_ago: number;
  total_autonomous_actions: number;
  total_user_messages: number;
  active_plans_count: number;
  can_act: boolean;
  queue_stats: { pending: number; total: number };
}

interface Cognition {
  focus: string;
  emotion: string;
  curiosity: number;
  energy: number;
}

interface Thought { id: number; timestamp: string; thought: string }
interface Action { id: number; timestamp: string; action_type: string; result: string; success: number }
interface Plan { id: number; title: string; status: string }
interface Goal { id: number; title: string; description?: string; priority?: number; status: string }
interface JournalEntry { id: number; timestamp: string; entry: string; mood?: string; category?: string }

const card: React.CSSProperties = {
  padding: '16px',
  background: 'rgba(0,0,0,0.4)',
  border: '1px solid var(--border)',
  borderRadius: '4px',
  boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
};

const h4: React.CSSProperties = {
  fontFamily: 'Orbitron',
  margin: '0 0 14px 0',
  fontSize: '0.8rem',
  color: 'var(--neon-blue)',
  letterSpacing: '2px',
};

const mono: React.CSSProperties = {
  fontFamily: 'Share Tech Mono',
  fontSize: '0.78rem',
};

const ago = (ts: string) => {
  const t = new Date(ts.replace(' ', 'T') + 'Z').getTime(); // db stores UTC naive
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

const Bar: React.FC<{ label: string; value: number; color: string }> = ({ label, value, color }) => (
  <div style={{ marginBottom: '10px' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', ...mono, fontSize: '0.7rem', opacity: 0.85, marginBottom: '4px' }}>
      <span>{label}</span><span>{Math.round(value * 100)}%</span>
    </div>
    <div style={{ background: 'rgba(0,0,0,0.5)', height: '6px', borderRadius: '3px', overflow: 'hidden' }}>
      <div style={{ height: '100%', width: `${Math.round(value * 100)}%`, background: color, transition: 'width 0.6s', boxShadow: `0 0 8px ${color}` }} />
    </div>
  </div>
);

export const MindTab: React.FC = () => {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [cognition, setCognition] = useState<Cognition | null>(null);
  const [soulName, setSoulName] = useState('');
  const [thoughts, setThoughts] = useState<Thought[]>([]);
  const [actions, setActions] = useState<Action[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [journal, setJournal] = useState<JournalEntry[]>([]);
  const [reachable, setReachable] = useState(true);

  useEffect(() => {
    let dead = false;
    const get = async (url: string) => {
      const r = await fetch(url);
      if (!r.ok) throw new Error(String(r.status));
      return r.json();
    };
    const poll = async () => {
      try {
        const [st, th, ac, pl, go, jr, soul] = await Promise.allSettled([
          get('/api/agent/status'),
          get('/api/agent/thoughts?limit=12'),
          get('/api/agent/actions?limit=8'),
          get('/api/agent/plans'),
          get('/api/agent/goals/active'),
          get('/api/agent/journal?limit=4'),
          get('/xrlf/soul/status'),
        ]);
        if (dead) return;
        if (st.status === 'fulfilled') { setStatus(st.value.agent); setReachable(true); }
        else setReachable(false);
        if (th.status === 'fulfilled') setThoughts(th.value.thoughts || []);
        if (ac.status === 'fulfilled') setActions(ac.value.actions || []);
        if (pl.status === 'fulfilled') setPlans(pl.value.plans || []);
        if (go.status === 'fulfilled') setGoals(go.value.goals || []);
        if (jr.status === 'fulfilled') setJournal(jr.value.entries || []);
        if (soul.status === 'fulfilled') {
          setCognition(soul.value.cognition || null);
          setSoulName(soul.value.soul?.name || '');
        }
      } catch { if (!dead) setReachable(false); }
    };
    poll();
    const iv = setInterval(poll, 15000);
    return () => { dead = true; clearInterval(iv); };
  }, []);

  return (
    <div style={{ padding: '20px', height: '100%', overflowY: 'auto' }}>
      <div className="breadcrumb">HER MIND — LIVE INTERIOR{soulName ? ` · ${soulName.toUpperCase()}` : ''}</div>
      <p style={{ fontSize: '0.75rem', opacity: 0.7, marginBottom: '20px', color: 'var(--neon-blue)' }}>
        The autonomous soul loop, direct from compagent :8405 — thoughts, goals, plans, journal. Refreshes every 15s.
      </p>

      {!reachable && (
        <div style={{ ...card, borderColor: 'var(--neon-pink)', marginBottom: '20px', ...mono, color: 'var(--neon-pink)' }}>
          ● SOUL SERVICE UNREACHABLE — compagent :8405 is down. Chat still works; her inner life is paused.
        </div>
      )}

      {/* STATUS STRIP */}
      <div style={{ ...card, marginBottom: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <h4 style={{ ...h4, margin: 0 }}>SOUL LOOP</h4>
            <span style={{ ...mono, color: status?.running ? 'var(--neon-green)' : 'var(--neon-pink)' }}>
              ● {status?.running ? 'RUNNING' : 'STOPPED'}
            </span>
            {status && (
              <span style={{ ...mono, opacity: 0.7 }}>
                {status.mode} · tick {status.loop_interval}s · {status.can_act ? 'idle, may act' : 'listening'}
              </span>
            )}
          </div>
          {status && (
            <div style={{ ...mono, opacity: 0.75, display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
              <span>actions <b style={{ color: 'var(--neon-green)' }}>{status.total_autonomous_actions}</b></span>
              <span>you said <b style={{ color: 'var(--neon-blue)' }}>{status.total_user_messages}</b></span>
              <span>outbox <b style={{ color: 'var(--neon-pink)' }}>{status.queue_stats.pending}</b></span>
              <span>plans <b style={{ color: 'var(--neon-blue)' }}>{status.active_plans_count}</b></span>
            </div>
          )}
        </div>
      </div>

      {/* COGNITION + GOALS + PLANS */}
      <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', marginBottom: '20px' }}>
        <div style={{ ...card, flex: 1, minWidth: '240px' }}>
          <h4 style={h4}>COGNITION</h4>
          {cognition ? (
            <>
              <div style={{ ...mono, marginBottom: '12px' }}>
                <span style={{ opacity: 0.6 }}>emotion </span>
                <span style={{ color: 'var(--neon-pink)', textTransform: 'uppercase' }}>{cognition.emotion}</span>
                <span style={{ opacity: 0.6 }}> · focus </span>
                <span style={{ color: 'var(--neon-blue)' }}>{cognition.focus}</span>
              </div>
              <Bar label="CURIOSITY" value={cognition.curiosity} color="var(--neon-blue)" />
              <Bar label="ENERGY" value={cognition.energy} color="var(--neon-green)" />
            </>
          ) : (
            <div style={{ ...mono, opacity: 0.5 }}>no cognition feed (runtime soul offline?)</div>
          )}
        </div>

        <div style={{ ...card, flex: 1, minWidth: '240px' }}>
          <h4 style={h4}>WANTS — ACTIVE GOALS</h4>
          {goals.length ? goals.map(g => (
            <div key={g.id} style={{ ...mono, padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
              <span style={{ color: 'var(--neon-green)' }}>◆</span> {g.title}
            </div>
          )) : (
            <div style={{ ...mono, opacity: 0.5 }}>no active goals — her dream cycle will mint some when it consolidates</div>
          )}
        </div>

        <div style={{ ...card, flex: 1, minWidth: '240px' }}>
          <h4 style={h4}>NOW DOING — PLANS</h4>
          {plans.length ? plans.map(p => (
            <div key={p.id} style={{ ...mono, padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
              <span style={{ color: 'var(--neon-blue)' }}>▸</span> {p.title}
              <span style={{ opacity: 0.5 }}> · {p.status}</span>
            </div>
          )) : (
            <div style={{ ...mono, opacity: 0.5 }}>no active plans</div>
          )}
        </div>
      </div>

      {/* THOUGHT STREAM + JOURNAL */}
      <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', marginBottom: '20px' }}>
        <div style={{ ...card, flex: 1.4, minWidth: '280px' }}>
          <h4 style={h4}>THOUGHT STREAM</h4>
          {thoughts.length ? thoughts.map(t => (
            <div key={t.id} style={{ ...mono, padding: '9px 0', borderBottom: '1px solid rgba(255,255,255,0.06)', lineHeight: 1.5 }}>
              <span style={{ opacity: 0.45 }}>{ago(t.timestamp)}</span>{' '}
              <span style={{ opacity: 0.92 }}>{t.thought}</span>
            </div>
          )) : (
            <div style={{ ...mono, opacity: 0.5 }}>no thoughts yet</div>
          )}
        </div>

        <div style={{ ...card, flex: 1, minWidth: '280px' }}>
          <h4 style={h4}>JOURNAL — HER STORY</h4>
          {journal.length ? journal.map(j => (
            <div key={j.id} style={{ ...mono, padding: '10px 0', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              <div style={{ marginBottom: '4px' }}>
                <span style={{ opacity: 0.45 }}>{ago(j.timestamp)}</span>
                {j.mood && <span style={{ color: 'var(--neon-pink)', marginLeft: '8px' }}>[{j.mood}]</span>}
              </div>
              <div style={{ opacity: 0.85, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
                {j.entry.length > 320 ? j.entry.slice(0, 320) + '…' : j.entry}
              </div>
            </div>
          )) : (
            <div style={{ ...mono, opacity: 0.5 }}>no journal entries yet</div>
          )}
        </div>
      </div>

      {/* ACTIONS */}
      <div style={{ ...card }}>
        <h4 style={h4}>RECENT ACTIONS</h4>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
          {actions.length ? actions.map(a => (
            <span key={a.id} title={a.result} style={{
              ...mono, fontSize: '0.72rem', padding: '4px 10px', borderRadius: '3px',
              border: `1px solid ${a.success ? 'var(--neon-green)' : 'var(--neon-pink)'}`,
              color: a.success ? 'var(--neon-green)' : 'var(--neon-pink)',
              background: 'rgba(0,0,0,0.3)', cursor: 'default',
            }}>
              {a.action_type} · {ago(a.timestamp)}
            </span>
          )) : (
            <span style={{ ...mono, opacity: 0.5 }}>none yet</span>
          )}
        </div>
      </div>
    </div>
  );
};
