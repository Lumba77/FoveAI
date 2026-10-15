import { useEffect, useState } from 'react';

interface Plan {
  id: number;
  title: string;
  description: string;
  status: string;
  priority: number;
  steps: string[];
  origin?: string;
}

/**
 * TodoPanel — the right-side task rail. One substrate, no parallel store:
 * renders agent_plans ([TASK]/[CODER]/scheduled) live from the soul API,
 * open steps first. Polls every 30s.
 */
export function TodoPanel({ apiKey }: { apiKey?: string }) {
  const [plans, setPlans] = useState<Plan[]>([]);

  useEffect(() => {
    let dead = false;
    const load = () => {
      fetch('/api/soul/tasks', {
        headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : {},
        signal: AbortSignal.timeout(6000),
      })
        .then(r => (r.ok ? r.json() : null))
        .then(d => {
          if (!dead && d?.tasks) {
            const open = (d.tasks as Plan[]).filter(p =>
              p.status === 'active' || p.status === 'paused'
            );
            setPlans(open.sort((a, b) => b.priority - a.priority).slice(0, 6));
          }
        })
        .catch(() => {});
    };
    load();
    const iv = setInterval(load, 30000);
    return () => { dead = true; clearInterval(iv); };
  }, [apiKey]);

  if (!plans.length) return null;

  return (
    <div className="todo-rail">
      <div className="todo-rail-head">◈ TASKS</div>
      {plans.map(p => (
        <div key={p.id} className="todo-rail-plan" title={p.description || p.title}>
          <div className="todo-rail-title">{p.title.replace(/^\[(TASK|CODER)\]\s*/, '')}</div>
          {(p.steps || []).slice(0, 5).map((s, i) => (
            <div key={i} className={`todo-rail-step ${s.startsWith('[✓]') ? 'done' : ''}`}>{s}</div>
          ))}
          {!(p.steps || []).length && <div className="todo-rail-step pending">(decomposing…)</div>}
        </div>
      ))}
    </div>
  );
}
