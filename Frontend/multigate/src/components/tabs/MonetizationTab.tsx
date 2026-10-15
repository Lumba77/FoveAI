import React, { useState, useEffect, useRef } from 'react';

interface AgentStats {
  agent_id: string;
  name: string;
  status: string;
  type: string;
  is_live?: boolean;
  has_credentials?: boolean;
  total_tasks_completed: number;
  total_earnings: number;
  last_search?: string;
  current_task?: {
    task_id: string;
    type: string;
    progress?: number;
    notes?: string;
    opportunity?: {
      name?: string;
      type?: string;
    };
  };
}

interface RiskStatus {
  daily_loss_limit: number;
  max_concurrent_positions: number;
  current_positions: number;
  positions_remaining: number;
}

interface SwarmSummary {
  pending_tasks: number;
  approved_tasks: number;
  completed_tasks: number;
  treasury?: {
    grinding_share_pct: number;
    reserve_share_pct: number;
    dispense_share_pct: number;
    balances: {
      grinding_usd: number;
      reserve_usd: number;
      dispense_usd: number;
      total_yield_usd: number;
    };
    payout?: {
      address: string;
      network: string;
      min_dispense_threshold: number;
    };
    reinvest?: {
      min_reinvest_threshold: number;
    };
  };
}

interface AuditEntry {
  timestamp: string;
  action: string;
  user_id?: string;
  details?: any;
}

interface StrategyIdea {
  id: string;
  title: string;
  description: string;
  category: string;
  estimated_revenue_month: number;
  complexity: number | string;
  score?: number;
  certified?: boolean;
  cert_status?: string;
}

interface StrategyPlan {
  idea_id: string;
  idea_title: string;
  timeline_days: number;
  estimated_cost: number;
  estimated_revenue: number;
  phases: Array<{
    name: string;
    duration_days: number;
    tasks: string[];
  }>;
}

export const MonetizationTab: React.FC = () => {
  // Live Vitals
  const [wallet, setWallet] = useState<string>('');
  const [cetBalance, setCetBalance] = useState<number>(0);
  const [solBalance, setSolBalance] = useState<number>(0);
  const [earnings, setEarnings] = useState<number>(0);
  const [hasCoinExKeys, setHasCoinExKeys] = useState<boolean>(false);
  const [risk, setRisk] = useState<RiskStatus>({
    daily_loss_limit: 100,
    max_concurrent_positions: 3,
    current_positions: 0,
    positions_remaining: 3,
  });

  // Swarm fleet & tasks
  const [agents, setAgents] = useState<AgentStats[]>([]);
  const [swarm, setSwarm] = useState<SwarmSummary>({
    pending_tasks: 0,
    approved_tasks: 0,
    completed_tasks: 0,
  });
  const [selectedAgent, setSelectedAgent] = useState<AgentStats | null>(null);

  // New Agent Form
  const [newAgentName, setNewAgentName] = useState<string>('');
  const [newAgentType, setNewAgentType] = useState<string>('crypto_trading');
  const [isDeploying, setIsDeploying] = useState<boolean>(false);

  // Idea Lab
  const [ideas, setIdeas] = useState<StrategyIdea[]>([]);
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [certifyingMap, setCertifyingMap] = useState<Record<string, boolean>>({});
  const [activePlan, setActivePlan] = useState<StrategyPlan | null>(null);
  const [isLoadingPlan, setIsLoadingPlan] = useState<boolean>(false);

  // Credentials & Config Form
  const [apiKey, setApiKey] = useState<string>('');
  const [apiSecret, setApiSecret] = useState<string>('');
  const [walletInput, setWalletInput] = useState<string>('');
  const [dailyLossInput, setDailyLossInput] = useState<number>(100);
  const [maxPositionsInput, setMaxPositionsInput] = useState<number>(3);
  const [configNotice, setConfigNotice] = useState<string>('');

  // Treasury split inputs
  const [grindingPct, setGrindingPct] = useState<number>(40);
  const [reservePct, setReservePct] = useState<number>(30);
  const [dispensePct, setDispensePct] = useState<number>(30);
  const [payoutAddress, setPayoutAddress] = useState<string>('');

  // Audit Log
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([]);

  // System status toast
  const [toastMessage, setToastMessage] = useState<string>('');
  const toastTimeoutRef = useRef<number | null>(null);

  const notify = (msg: string) => {
    setToastMessage(msg);
    if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    toastTimeoutRef.current = window.setTimeout(() => setToastMessage(''), 4000);
  };

  // Fetch status
  const fetchStatus = async () => {
    try {
      const res = await fetch('/monetize/status');
      if (!res.ok) return;
      const data = await res.json();

      setWallet(data.wallet || '');
      setCetBalance(data.cet_balance || 0);
      setSolBalance(data.balance || 0);
      setEarnings(data.earnings || 0);
      setHasCoinExKeys(Boolean(data.has_coinex_keys || data.coinex_configured));
      if (data.risk) setRisk(data.risk);
      if (data.agents) {
        setAgents(data.agents);
        // Update selected agent telemetry if open
        if (selectedAgent) {
          const fresh = data.agents.find((a: AgentStats) => a.agent_id === selectedAgent.agent_id);
          if (fresh) setSelectedAgent(fresh);
        }
      }
      if (data.swarm) {
        setSwarm(data.swarm);
        if (data.swarm.treasury) {
          const t = data.swarm.treasury;
          setGrindingPct(Math.round(t.grinding_share_pct * 100));
          setReservePct(Math.round(t.reserve_share_pct * 100));
          setDispensePct(Math.round(t.dispense_share_pct * 100));
          if (t.payout?.address && t.payout.address !== 'Not configured') {
            setPayoutAddress(t.payout.address);
          }
        }
      }
      if (data.audit) setAuditLog(data.audit);
    } catch (err) {
      console.warn('Monetize status poll error:', err);
    }
  };

  // Fetch Ideas
  const fetchIdeas = async () => {
    try {
      const res = await fetch('/monetize/ideas');
      if (!res.ok) return;
      const data = await res.json();
      if (data.ideas) setIdeas(data.ideas);
    } catch (err) {
      console.warn('Monetize ideas fetch error:', err);
    }
  };

  useEffect(() => {
    fetchStatus();
    fetchIdeas();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  // Swarm Control
  const handleSwarmControl = async (action: 'start' | 'pause') => {
    try {
      notify(`Triggering swarm ${action.toUpperCase()}...`);
      const res = await fetch('/monetize/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
      const data = await res.json();
      notify(`Swarm state set to: ${data.status?.toUpperCase() || action.toUpperCase()}`);
      fetchStatus();
    } catch (err) {
      notify(`Swarm control error: ${String(err)}`);
    }
  };

  // Deploy Agent
  const handleDeployAgent = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!newAgentName.trim()) {
      notify('Please enter an agent name.');
      return;
    }
    setIsDeploying(true);
    try {
      const res = await fetch('/monetize/add_agent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newAgentName.trim(), type: newAgentType }),
      });
      const data = await res.json();
      notify(`Agent ${newAgentName} deployed [${data.agent_id}]!`);
      setNewAgentName('');
      fetchStatus();
    } catch (err) {
      notify(`Agent deployment error: ${String(err)}`);
    } finally {
      setIsDeploying(false);
    }
  };

  // Remove Agent
  const handleRemoveAgent = async (agentId: string, name: string) => {
    if (!confirm(`Are you sure you want to terminate and remove agent "${name}"?`)) return;
    try {
      const res = await fetch('/monetize/remove_agent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agentId }),
      });
      if (res.ok) {
        notify(`Agent ${name} terminated.`);
        if (selectedAgent?.agent_id === agentId) setSelectedAgent(null);
        fetchStatus();
      }
    } catch (err) {
      notify(`Error removing agent: ${String(err)}`);
    }
  };

  // Save Config
  const handleSaveConfig = async () => {
    try {
      const payload: any = {
        apiKey: apiKey || (hasCoinExKeys ? '********' : ''),
        apiSecret: apiSecret || (hasCoinExKeys ? '********' : ''),
        wallet: walletInput.trim() || wallet,
        maxLoss: dailyLossInput,
        maxPositions: maxPositionsInput,
      };
      const res = await fetch('/monetize/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setConfigNotice('Configuration saved & synchronized successfully!');
        setTimeout(() => setConfigNotice(''), 4000);
        fetchStatus();
      }
    } catch (err) {
      setConfigNotice(`Save failed: ${String(err)}`);
    }
  };

  // Save Treasury Splits
  const handleSaveTreasury = async () => {
    try {
      const res = await fetch('/monetize/treasury/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          grindingPct: grindingPct / 100,
          reservePct: reservePct / 100,
          dispensePct: dispensePct / 100,
          payoutAddress: payoutAddress.trim(),
          minReinvest: 2.0,
          minDispense: 10.0,
        }),
      });
      if (res.ok) {
        notify('Treasury distribution updated!');
        fetchStatus();
      }
    } catch (err) {
      notify(`Treasury update failed: ${String(err)}`);
    }
  };

  // Scan Ideas
  const handleScanIdeas = async () => {
    if (isScanning) return;
    setIsScanning(true);
    notify('Scanning knowledge base and market signals for strategies...');
    try {
      const res = await fetch('/monetize/ideas/scan', { method: 'POST' });
      const data = await res.json();
      notify(`Discovered ${data.discovered_count ?? 0} new income strategies!`);
      await fetchIdeas();
    } catch (err) {
      notify(`Idea scanning failed: ${String(err)}`);
    } finally {
      setIsScanning(false);
    }
  };

  // Certify Idea
  const handleCertifyIdea = async (ideaId: string) => {
    setCertifyingMap(prev => ({ ...prev, [ideaId]: true }));
    notify(`Triggering local AI verification simulation for ${ideaId}...`);
    try {
      const res = await fetch('/monetize/ideas/certify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idea_id: ideaId }),
      });
      const data = await res.json();
      notify(`Strategy ${ideaId} certified: ${data.status?.toUpperCase()} (${data.score ?? 0}/100)`);
      await fetchIdeas();
    } catch (err) {
      notify(`Certification error: ${String(err)}`);
    } finally {
      setCertifyingMap(prev => ({ ...prev, [ideaId]: false }));
    }
  };

  // Plan Idea
  const handleViewPlan = async (ideaId: string) => {
    setIsLoadingPlan(true);
    try {
      const res = await fetch(`/monetize/ideas/plan?idea_id=${ideaId}`);
      const data = await res.json();
      setActivePlan(data);
    } catch (err) {
      notify(`Plan retrieval error: ${String(err)}`);
    } finally {
      setIsLoadingPlan(false);
    }
  };

  // Deploy Idea into form
  const handlePreFillIdea = (title: string, category: string) => {
    setNewAgentName(title.slice(0, 24));
    let mappedType = 'crypto_trading';
    if (category.includes('affiliate')) mappedType = 'affiliate_marketing';
    else if (category.includes('ad')) mappedType = 'ad_revenue';
    else if (category.includes('content')) mappedType = 'content_creation';
    else if (category.includes('free')) mappedType = 'freelancing';
    setNewAgentType(mappedType);
    notify(`Loaded "${title}" into Agent Forge form. Click DEPLOY to launch!`);
  };

  const activeAgentsCount = agents.filter(a =>
    ['executing', 'searching', 'analyzing'].includes((a.status || '').toLowerCase())
  ).length;

  return (
    <div style={{ padding: '24px', height: '100%', overflowY: 'auto', color: 'var(--text-main, #dfe7ff)' }}>
      {/* Header Banner */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <div>
          <div style={{ fontFamily: 'Orbitron, sans-serif', fontSize: '0.8rem', color: 'var(--accent-cyan, #00f3ff)', letterSpacing: '2px', textTransform: 'uppercase' }}>
            Open XRL Cognitive Swarm · Monetary Engine
          </div>
          <h2 style={{ fontFamily: 'Orbitron, sans-serif', margin: '4px 0 0 0', fontSize: '1.4rem', color: '#fff', letterSpacing: '1px' }}>
            LUMAX MONETIZING SWARM
          </h2>
        </div>
        {toastMessage && (
          <div style={{ background: 'rgba(0, 243, 255, 0.15)', border: '1px solid var(--accent-cyan, #00f3ff)', color: 'var(--accent-cyan, #00f3ff)', padding: '8px 16px', borderRadius: '4px', fontFamily: 'Share Tech Mono, monospace', fontSize: '0.8rem', animation: 'fadeIn 0.2s ease-out' }}>
            ⚡ {toastMessage}
          </div>
        )}
      </div>

      {/* Top HUD Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px', marginBottom: '20px' }}>
        {/* Earnings Card */}
        <div style={{ background: 'rgba(7, 11, 29, 0.7)', border: '1px solid rgba(0, 243, 255, 0.2)', borderRadius: '6px', padding: '16px', backdropFilter: 'blur(8px)', boxShadow: '0 8px 24px rgba(0,0,0,0.4)' }}>
          <div style={{ fontFamily: 'Orbitron, sans-serif', fontSize: '0.7rem', color: '#39ff14', letterSpacing: '2px', textTransform: 'uppercase', marginBottom: '6px' }}>
            Live Holdings & Earnings
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#39ff14', fontFamily: 'Share Tech Mono, monospace' }}>
            {cetBalance > 0 ? `${cetBalance.toFixed(2)} CET` : `${solBalance.toFixed(4)} SOL`}
          </div>
          <div style={{ marginTop: '8px', fontSize: '0.8rem', opacity: 0.8, display: 'flex', justifyContent: 'space-between', fontFamily: 'Share Tech Mono, monospace' }}>
            <span>Wallet: <strong style={{ color: 'var(--accent-cyan, #00f3ff)' }}>{wallet ? `${wallet.slice(0, 6)}...${wallet.slice(-4)}` : 'Disconnected'}</strong></span>
            <span>Yield: <strong style={{ color: '#39ff14' }}>${(swarm.treasury?.balances.total_yield_usd || earnings || 0).toFixed(2)} USD</strong></span>
          </div>
        </div>

        {/* Risk Card */}
        <div style={{ background: 'rgba(7, 11, 29, 0.7)', border: '1px solid rgba(255, 0, 127, 0.25)', borderRadius: '6px', padding: '16px', backdropFilter: 'blur(8px)', boxShadow: '0 8px 24px rgba(0,0,0,0.4)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
            <span style={{ fontFamily: 'Orbitron, sans-serif', fontSize: '0.7rem', color: '#ff007f', letterSpacing: '2px', textTransform: 'uppercase' }}>
              Risk Engine
            </span>
            <span style={{ background: risk.current_positions > 0 ? 'rgba(57, 255, 20, 0.2)' : 'rgba(0, 243, 255, 0.2)', border: `1px solid ${risk.current_positions > 0 ? '#39ff14' : '#00f3ff'}`, color: risk.current_positions > 0 ? '#39ff14' : '#00f3ff', padding: '2px 8px', borderRadius: '3px', fontSize: '0.65rem', fontFamily: 'Orbitron, sans-serif', fontWeight: 700 }}>
              {risk.current_positions > 0 ? 'OPERATIONAL' : 'STANDBY'}
            </span>
          </div>
          <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#fff', fontFamily: 'Share Tech Mono, monospace', marginTop: '6px' }}>
            Max Loss: <span style={{ color: '#ffaa00' }}>${risk.daily_loss_limit}</span>
          </div>
          <div style={{ marginTop: '8px', fontSize: '0.8rem', opacity: 0.8, fontFamily: 'Share Tech Mono, monospace' }}>
            Positions Active: <strong style={{ color: 'var(--accent-cyan, #00f3ff)' }}>{risk.current_positions}</strong> / Remaining: <strong style={{ color: '#39ff14' }}>{risk.positions_remaining}</strong>
          </div>
        </div>

        {/* Treasury Allocation Card */}
        <div style={{ background: 'rgba(7, 11, 29, 0.7)', border: '1px solid rgba(167, 139, 250, 0.25)', borderRadius: '6px', padding: '16px', backdropFilter: 'blur(8px)', boxShadow: '0 8px 24px rgba(0,0,0,0.4)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
            <span style={{ fontFamily: 'Orbitron, sans-serif', fontSize: '0.7rem', color: '#a78bfa', letterSpacing: '2px', textTransform: 'uppercase' }}>
              Treasury Split & Reserve
            </span>
            <button
              onClick={handleSaveTreasury}
              style={{ background: 'rgba(167, 139, 250, 0.2)', border: '1px solid #a78bfa', color: '#a78bfa', borderRadius: '3px', fontSize: '0.6rem', padding: '2px 8px', fontFamily: 'Orbitron, sans-serif', cursor: 'pointer', fontWeight: 700 }}
            >
              SAVE SPLIT
            </button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', marginTop: '10px', textAlign: 'center', fontFamily: 'Share Tech Mono, monospace' }}>
            <div style={{ background: 'rgba(167, 139, 250, 0.1)', padding: '6px', borderRadius: '4px', border: '1px solid rgba(167, 139, 250, 0.2)' }}>
              <div style={{ fontSize: '0.65rem', opacity: 0.7 }}>GRIND ({grindingPct}%)</div>
              <div style={{ fontSize: '1rem', color: '#39ff14', fontWeight: 700 }}>${(swarm.treasury?.balances.grinding_usd || 0).toFixed(2)}</div>
            </div>
            <div style={{ background: 'rgba(167, 139, 250, 0.1)', padding: '6px', borderRadius: '4px', border: '1px solid rgba(167, 139, 250, 0.2)' }}>
              <div style={{ fontSize: '0.65rem', opacity: 0.7 }}>RESERVE ({reservePct}%)</div>
              <div style={{ fontSize: '1rem', color: '#00f3ff', fontWeight: 700 }}>${(swarm.treasury?.balances.reserve_usd || 0).toFixed(2)}</div>
            </div>
            <div style={{ background: 'rgba(167, 139, 250, 0.1)', padding: '6px', borderRadius: '4px', border: '1px solid rgba(167, 139, 250, 0.2)' }}>
              <div style={{ fontSize: '0.65rem', opacity: 0.7 }}>DISPENSE ({dispensePct}%)</div>
              <div style={{ fontSize: '1rem', color: '#ffaa00', fontWeight: 700 }}>${(swarm.treasury?.balances.dispense_usd || 0).toFixed(2)}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Grid: Swarm Controls + Fleet List */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '20px', marginBottom: '24px' }}>
        {/* Left: Swarm Orchestration & Forge */}
        <div style={{ background: 'rgba(7, 11, 29, 0.75)', border: '1px solid rgba(0, 243, 255, 0.16)', borderRadius: '6px', padding: '20px', backdropFilter: 'blur(8px)' }}>
          <h4 style={{ fontFamily: 'Orbitron, sans-serif', margin: '0 0 16px 0', fontSize: '0.9rem', color: 'var(--accent-cyan, #00f3ff)', letterSpacing: '2px', textTransform: 'uppercase' }}>
            Swarm Control & Deployment
          </h4>
          
          <div style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
            <button
              onClick={() => handleSwarmControl('start')}
              style={{ flex: 1, padding: '12px', background: 'rgba(57, 255, 20, 0.15)', border: '1px solid #39ff14', color: '#39ff14', fontFamily: 'Orbitron, sans-serif', fontSize: '0.85rem', fontWeight: 700, borderRadius: '4px', cursor: 'pointer', transition: 'all 0.2s', letterSpacing: '1px' }}
            >
              🚀 START SWARM
            </button>
            <button
              onClick={() => handleSwarmControl('pause')}
              style={{ flex: 1, padding: '12px', background: 'rgba(255, 0, 127, 0.15)', border: '1px solid #ff007f', color: '#ff007f', fontFamily: 'Orbitron, sans-serif', fontSize: '0.85rem', fontWeight: 700, borderRadius: '4px', cursor: 'pointer', transition: 'all 0.2s', letterSpacing: '1px' }}
            >
              ⏸️ PAUSE SWARM
            </button>
          </div>

          <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '16px' }}>
            <h5 style={{ fontFamily: 'Orbitron, sans-serif', margin: '0 0 12px 0', fontSize: '0.8rem', color: '#dfe7ff', letterSpacing: '1px' }}>
              ⚡ Forge New Income Agent
            </h5>
            <form onSubmit={handleDeployAgent} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <input
                type="text"
                placeholder="Agent Name (e.g. CET-Arbitrage-Alpha)..."
                value={newAgentName}
                onChange={e => setNewAgentName(e.target.value)}
                style={{ padding: '10px 14px', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(0, 243, 255, 0.3)', borderRadius: '4px', color: '#fff', fontFamily: 'Share Tech Mono, monospace', fontSize: '0.85rem', outline: 'none' }}
              />
              <select
                value={newAgentType}
                onChange={e => setNewAgentType(e.target.value)}
                style={{ padding: '10px 14px', background: '#070b1d', border: '1px solid rgba(0, 243, 255, 0.3)', borderRadius: '4px', color: '#fff', fontFamily: 'Share Tech Mono, monospace', fontSize: '0.85rem', outline: 'none' }}
              >
                <option value="crypto_trading">Crypto Trading Agent (CoinEx / CET Grinder)</option>
                <option value="affiliate_marketing">Affiliate Marketing Scout</option>
                <option value="ad_revenue">Ad Revenue Optimizer</option>
                <option value="content_creation">Content Creation & Creative Asset Agent</option>
                <option value="freelancing">Freelance Dispatch Agent</option>
                <option value="staking">Automated Staking Worker</option>
              </select>
              <button
                type="submit"
                disabled={isDeploying}
                style={{ padding: '12px', background: 'var(--accent-cyan, #00f3ff)', border: 'none', color: '#000', fontFamily: 'Orbitron, sans-serif', fontWeight: 800, fontSize: '0.85rem', borderRadius: '4px', cursor: isDeploying ? 'wait' : 'pointer', letterSpacing: '1px', transition: 'all 0.2s' }}
              >
                {isDeploying ? 'FORGING AGENT...' : 'DEPLOY AGENT'}
              </button>
            </form>
          </div>
        </div>

        {/* Right: Active Fleet & HUD Monitor */}
        <div style={{ background: 'rgba(7, 11, 29, 0.75)', border: '1px solid rgba(0, 243, 255, 0.16)', borderRadius: '6px', padding: '20px', backdropFilter: 'blur(8px)', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <h4 style={{ fontFamily: 'Orbitron, sans-serif', margin: 0, fontSize: '0.9rem', color: 'var(--accent-cyan, #00f3ff)', letterSpacing: '2px', textTransform: 'uppercase' }}>
              Active Swarm Fleet ({agents.length})
            </h4>
            <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: '0.75rem', color: 'rgba(255,255,255,0.6)' }}>
              Active: <strong style={{ color: '#39ff14' }}>{activeAgentsCount}</strong> | Pending: <strong style={{ color: '#ffaa00' }}>{swarm.pending_tasks}</strong> | Done: <strong style={{ color: '#00f3ff' }}>{swarm.completed_tasks}</strong>
            </div>
          </div>

          {/* Agents list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '220px', overflowY: 'auto', paddingRight: '4px' }}>
            {agents.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '30px 20px', color: 'rgba(255,255,255,0.4)', fontFamily: 'Share Tech Mono, monospace' }}>
                No active agents deployed. Use the forge panel to create your first income agent.
              </div>
            ) : (
              agents.map(a => {
                const status = (a.status || 'idle').toLowerCase();
                const isSelected = selectedAgent?.agent_id === a.agent_id;
                const statusColor = status === 'executing' ? '#39ff14' : status === 'searching' ? '#ffaa00' : status === 'analyzing' ? '#00f3ff' : status === 'paused' ? 'rgba(255,255,255,0.4)' : '#ff007f';
                const statusIcon = status === 'executing' ? '⚡' : status === 'searching' ? '🔍' : status === 'analyzing' ? '🧠' : status === 'paused' ? '⏸' : '💤';

                return (
                  <div
                    key={a.agent_id}
                    onClick={() => setSelectedAgent(a)}
                    style={{ background: isSelected ? 'rgba(0, 243, 255, 0.12)' : 'rgba(0,0,0,0.3)', border: `1px solid ${isSelected ? 'var(--accent-cyan, #00f3ff)' : 'rgba(255,255,255,0.08)'}`, borderRadius: '4px', padding: '10px 12px', cursor: 'pointer', transition: 'all 0.15s', position: 'relative' }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <strong style={{ fontFamily: 'Orbitron, sans-serif', fontSize: '0.85rem', color: '#fff' }}>{a.name}</strong>
                        {a.is_live ? (
                          <span style={{ background: 'rgba(57,255,20,0.15)', border: '1px solid #39ff14', color: '#39ff14', fontSize: '0.55rem', padding: '1px 5px', borderRadius: '2px', fontFamily: 'Orbitron, sans-serif', fontWeight: 700 }}>LIVE</span>
                        ) : (
                          <span style={{ background: 'rgba(255,0,127,0.15)', border: '1px solid #ff007f', color: '#ff007f', fontSize: '0.55rem', padding: '1px 5px', borderRadius: '2px', fontFamily: 'Orbitron, sans-serif', fontWeight: 700 }}>SIM</span>
                        )}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: '0.75rem', color: statusColor }}>
                          {statusIcon} {status.toUpperCase()}
                        </span>
                        <button
                          onClick={e => {
                            e.stopPropagation();
                            handleRemoveAgent(a.agent_id, a.name);
                          }}
                          style={{ background: 'none', border: 'none', color: '#ff007f', cursor: 'pointer', fontSize: '0.9rem', fontWeight: 700, padding: '2px 6px' }}
                          title="Terminate Agent"
                        >
                          ✖
                        </button>
                      </div>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '6px', fontSize: '0.7rem', color: 'rgba(255,255,255,0.6)', fontFamily: 'Share Tech Mono, monospace' }}>
                      <span>Earned: <strong style={{ color: '#39ff14' }}>${(a.total_earnings || 0).toFixed(2)} USD</strong></span>
                      <span>Tasks: <strong>{a.total_tasks_completed}</strong></span>
                      <span style={{ opacity: 0.5 }}>{a.agent_id}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Realtime Agent Monitor HUD */}
          {selectedAgent && (
            <div style={{ marginTop: '16px', background: 'rgba(0,0,0,0.5)', border: '1px solid var(--accent-cyan, #00f3ff)', borderRadius: '4px', padding: '14px', fontFamily: 'Share Tech Mono, monospace', fontSize: '0.8rem', animation: 'fadeIn 0.2s ease-out' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.12)', paddingBottom: '8px', marginBottom: '10px' }}>
                <span style={{ fontFamily: 'Orbitron, sans-serif', fontSize: '0.8rem', color: 'var(--accent-cyan, #00f3ff)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  📺 TELEMETRY HUD: <strong style={{ color: '#39ff14' }}>{selectedAgent.name}</strong>
                </span>
                <button
                  onClick={() => setSelectedAgent(null)}
                  style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.6)', cursor: 'pointer', fontSize: '1rem' }}
                >
                  ✖
                </button>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px', marginBottom: '10px' }}>
                <div>ID: <span style={{ color: 'var(--accent-cyan, #00f3ff)' }}>{selectedAgent.agent_id}</span></div>
                <div>Status: <span style={{ color: '#39ff14' }}>{selectedAgent.status.toUpperCase()}</span></div>
                <div>Tasks Completed: <span style={{ color: '#ffaa00' }}>{selectedAgent.total_tasks_completed}</span></div>
                <div>Generated: <span style={{ color: '#39ff14', fontWeight: 700 }}>${(selectedAgent.total_earnings || 0).toFixed(4)} USD</span></div>
              </div>

              <div style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '4px', padding: '10px', fontSize: '0.75rem' }}>
                <div style={{ color: 'var(--accent-cyan, #00f3ff)', fontWeight: 700, marginBottom: '4px' }}>CURRENT ACTIVE TASK:</div>
                <div style={{ opacity: 0.9 }}>
                  {selectedAgent.current_task ? (
                    <>
                      [{selectedAgent.current_task.task_id}] {selectedAgent.current_task.opportunity?.name || selectedAgent.current_task.type} — {selectedAgent.current_task.notes || 'In progress'} ({Math.round(selectedAgent.current_task.progress || 0)}%)
                    </>
                  ) : (
                    'Awaiting next task allocation from Swarm Orchestrator...'
                  )}
                </div>
                <div style={{ color: 'var(--accent-cyan, #00f3ff)', fontWeight: 700, marginTop: '8px', marginBottom: '2px' }}>LAST TELEMETRY SEARCH:</div>
                <div style={{ opacity: 0.6 }}>{selectedAgent.last_search || 'None recorded'}</div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Idea Lab & Strategy Engine */}
      <div style={{ background: 'rgba(7, 11, 29, 0.75)', border: '1px solid rgba(57, 255, 20, 0.25)', borderRadius: '6px', padding: '20px', backdropFilter: 'blur(8px)', marginBottom: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '12px' }}>
          <div>
            <h4 style={{ fontFamily: 'Orbitron, sans-serif', margin: 0, fontSize: '0.95rem', color: '#39ff14', letterSpacing: '2px' }}>
              💡 IDEA LAB & STRATEGY ENGINE
            </h4>
            <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.6)', marginTop: '4px', fontFamily: 'Share Tech Mono, monospace' }}>
              Autonomous market research, certainty certification, and deployment pipelines.
            </div>
          </div>
          <button
            onClick={handleScanIdeas}
            disabled={isScanning}
            style={{ padding: '8px 18px', background: 'rgba(57, 255, 20, 0.15)', border: '1px solid #39ff14', color: '#39ff14', fontFamily: 'Orbitron, sans-serif', fontSize: '0.75rem', fontWeight: 700, borderRadius: '4px', cursor: isScanning ? 'wait' : 'pointer', letterSpacing: '1px' }}
          >
            {isScanning ? 'SCANNING SIGNALS...' : 'SCAN FOR STRATEGIES'}
          </button>
        </div>

        {/* Ideas Table */}
        <div style={{ maxHeight: '320px', overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontFamily: 'Share Tech Mono, monospace', fontSize: '0.8rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.12)', opacity: 0.7, fontSize: '0.7rem', letterSpacing: '1px' }}>
                <th style={{ padding: '8px 10px' }}>STRATEGY & SCOPE</th>
                <th style={{ padding: '8px 10px' }}>EST. REVENUE</th>
                <th style={{ padding: '8px 10px' }}>COMPLEXITY</th>
                <th style={{ padding: '8px 10px' }}>CERTIFICATION</th>
                <th style={{ padding: '8px 10px', textAlign: 'right' }}>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {ideas.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', padding: '30px', color: 'rgba(255,255,255,0.4)' }}>
                    No strategy ideas found. Click "SCAN FOR STRATEGIES" to discover new monetization vectors.
                  </td>
                </tr>
              ) : (
                ideas.map(idea => {
                  const isCertifying = certifyingMap[idea.id];
                  const certified = Boolean(idea.certified);
                  return (
                    <tr key={idea.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', transition: 'background 0.2s' }}>
                      <td style={{ padding: '10px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                          <span style={{ background: 'rgba(0, 243, 255, 0.15)', border: '1px solid var(--accent-cyan, #00f3ff)', color: 'var(--accent-cyan, #00f3ff)', fontSize: '0.6rem', padding: '1px 6px', borderRadius: '3px', textTransform: 'uppercase' }}>
                            {idea.category.replace('_', ' ')}
                          </span>
                          <strong style={{ fontFamily: 'Orbitron, sans-serif', color: '#fff', fontSize: '0.85rem' }}>{idea.title}</strong>
                        </div>
                        <div style={{ fontSize: '0.7rem', opacity: 0.7, maxWidth: '500px', lineHeight: 1.3 }}>{idea.description}</div>
                      </td>
                      <td style={{ padding: '10px', color: '#39ff14', fontWeight: 700 }}>
                        ${(Number(idea.estimated_revenue_month) || 0).toFixed(0)}/mo
                      </td>
                      <td style={{ padding: '10px' }}>
                        <span style={{ color: Number(idea.complexity) > 3 ? '#ffaa00' : '#39ff14' }}>
                          {String(idea.complexity)}
                        </span>
                      </td>
                      <td style={{ padding: '10px' }}>
                        {certified ? (
                          <span style={{ background: idea.cert_status === 'failed' ? 'rgba(255,0,127,0.15)' : 'rgba(57,255,20,0.15)', border: `1px solid ${idea.cert_status === 'failed' ? '#ff007f' : '#39ff14'}`, color: idea.cert_status === 'failed' ? '#ff007f' : '#39ff14', padding: '2px 6px', borderRadius: '3px', fontSize: '0.65rem' }}>
                            CERTIFIED ({idea.cert_status?.toUpperCase()})
                          </span>
                        ) : (
                          <span style={{ opacity: 0.5, fontSize: '0.7rem' }}>UNVERIFIED</span>
                        )}
                      </td>
                      <td style={{ padding: '10px', textAlign: 'right' }}>
                        <div style={{ display: 'flex', gap: '6px', justifyContent: 'flex-end' }}>
                          <button
                            onClick={() => handleCertifyIdea(idea.id)}
                            disabled={isCertifying}
                            style={{ padding: '4px 8px', background: 'rgba(255, 255, 255, 0.08)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', fontFamily: 'Orbitron, sans-serif', fontSize: '0.65rem', borderRadius: '3px', cursor: 'pointer' }}
                          >
                            {isCertifying ? 'VERIFYING...' : 'CERTIFY'}
                          </button>
                          <button
                            onClick={() => handleViewPlan(idea.id)}
                            disabled={isLoadingPlan}
                            style={{ padding: '4px 8px', background: 'rgba(0, 243, 255, 0.1)', border: '1px solid var(--accent-cyan, #00f3ff)', color: 'var(--accent-cyan, #00f3ff)', fontFamily: 'Orbitron, sans-serif', fontSize: '0.65rem', borderRadius: '3px', cursor: 'pointer' }}
                          >
                            {isLoadingPlan ? 'PLAN...' : 'PLAN'}
                          </button>
                          <button
                            onClick={() => handlePreFillIdea(idea.title, idea.category)}
                            style={{ padding: '4px 10px', background: '#39ff14', border: 'none', color: '#000', fontFamily: 'Orbitron, sans-serif', fontSize: '0.65rem', fontWeight: 800, borderRadius: '3px', cursor: 'pointer' }}
                          >
                            DEPLOY
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Inline Strategy Plan Modal / Viewer */}
        {activePlan && (
          <div style={{ marginTop: '16px', background: 'rgba(0,0,0,0.6)', border: '1px solid var(--accent-cyan, #00f3ff)', borderRadius: '6px', padding: '16px', fontFamily: 'Share Tech Mono, monospace', animation: 'fadeIn 0.2s ease-out' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '8px', marginBottom: '12px' }}>
              <h4 style={{ fontFamily: 'Orbitron, sans-serif', margin: 0, fontSize: '0.9rem', color: 'var(--accent-cyan, #00f3ff)' }}>
                📋 IMPLEMENTATION BLUEPRINT: {activePlan.idea_title}
              </h4>
              <button
                onClick={() => setActivePlan(null)}
                style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.6)', cursor: 'pointer', fontSize: '1.1rem' }}
              >
                ✖
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', marginBottom: '14px' }}>
              <div style={{ background: 'rgba(255,255,255,0.05)', padding: '8px', borderRadius: '4px' }}>
                <div style={{ fontSize: '0.7rem', opacity: 0.7 }}>TIMELINE</div>
                <div style={{ fontSize: '1.1rem', color: '#00f3ff', fontWeight: 700 }}>{activePlan.timeline_days} Days</div>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.05)', padding: '8px', borderRadius: '4px' }}>
                <div style={{ fontSize: '0.7rem', opacity: 0.7 }}>INITIAL CAPITAL</div>
                <div style={{ fontSize: '1.1rem', color: '#ffaa00', fontWeight: 700 }}>${activePlan.estimated_cost} USD</div>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.05)', padding: '8px', borderRadius: '4px' }}>
                <div style={{ fontSize: '0.7rem', opacity: 0.7 }}>PROJECTED REVENUE</div>
                <div style={{ fontSize: '1.1rem', color: '#39ff14', fontWeight: 700 }}>${activePlan.estimated_revenue} USD/mo</div>
              </div>
            </div>

            {activePlan.phases && activePlan.phases.length > 0 && (
              <div>
                <div style={{ color: 'var(--accent-cyan, #00f3ff)', fontWeight: 700, marginBottom: '8px', fontSize: '0.8rem' }}>EXECUTION PHASES:</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {activePlan.phases.map((ph, idx) => (
                    <div key={idx} style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '4px', padding: '10px' }}>
                      <div style={{ fontWeight: 700, color: '#fff', marginBottom: '4px' }}>
                        Phase {idx + 1}: {ph.name} ({ph.duration_days} days)
                      </div>
                      <ul style={{ margin: 0, paddingLeft: '20px', opacity: 0.8, fontSize: '0.75rem' }}>
                        {ph.tasks.map((task, tIdx) => (
                          <li key={tIdx}>{task}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bottom Grid: API & Treasury Config + Audit Log */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '20px' }}>
        {/* Credentials & Security Config */}
        <div style={{ background: 'rgba(7, 11, 29, 0.75)', border: '1px solid rgba(255, 0, 127, 0.2)', borderRadius: '6px', padding: '20px', backdropFilter: 'blur(8px)' }}>
          <h4 style={{ fontFamily: 'Orbitron, sans-serif', margin: '0 0 16px 0', fontSize: '0.9rem', color: '#ff007f', letterSpacing: '2px', textTransform: 'uppercase' }}>
            API & Security Settings
          </h4>

          {configNotice && (
            <div style={{ background: 'rgba(57, 255, 20, 0.15)', border: '1px solid #39ff14', color: '#39ff14', padding: '8px 12px', borderRadius: '4px', fontFamily: 'Share Tech Mono, monospace', fontSize: '0.75rem', marginBottom: '12px' }}>
              {configNotice}
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '14px' }}>
            <div>
              <label style={{ fontSize: '0.7rem', opacity: 0.7, display: 'block', marginBottom: '4px', fontFamily: 'Share Tech Mono, monospace' }}>CoinEx Access ID</label>
              <input
                type="password"
                placeholder={hasCoinExKeys ? '•••••••• (Stored securely)' : 'Enter CoinEx Access ID'}
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                style={{ width: '100%', padding: '8px 12px', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255, 0, 127, 0.3)', borderRadius: '4px', color: '#fff', fontFamily: 'Share Tech Mono, monospace', fontSize: '0.8rem', outline: 'none' }}
              />
            </div>
            <div>
              <label style={{ fontSize: '0.7rem', opacity: 0.7, display: 'block', marginBottom: '4px', fontFamily: 'Share Tech Mono, monospace' }}>CoinEx Secret Key</label>
              <input
                type="password"
                placeholder={hasCoinExKeys ? '•••••••• (Stored securely)' : 'Enter CoinEx Secret Key'}
                value={apiSecret}
                onChange={e => setApiSecret(e.target.value)}
                style={{ width: '100%', padding: '8px 12px', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255, 0, 127, 0.3)', borderRadius: '4px', color: '#fff', fontFamily: 'Share Tech Mono, monospace', fontSize: '0.8rem', outline: 'none' }}
              />
            </div>
            <div>
              <label style={{ fontSize: '0.7rem', opacity: 0.7, display: 'block', marginBottom: '4px', fontFamily: 'Share Tech Mono, monospace' }}>Solana Wallet Address</label>
              <input
                type="text"
                placeholder={wallet || 'Enter Solana address'}
                value={walletInput}
                onChange={e => setWalletInput(e.target.value)}
                style={{ width: '100%', padding: '8px 12px', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(57, 255, 20, 0.3)', borderRadius: '4px', color: '#fff', fontFamily: 'Share Tech Mono, monospace', fontSize: '0.8rem', outline: 'none' }}
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
              <div>
                <label style={{ fontSize: '0.7rem', opacity: 0.7, display: 'block', marginBottom: '4px', fontFamily: 'Share Tech Mono, monospace' }}>Daily Loss Limit ($)</label>
                <input
                  type="number"
                  value={dailyLossInput}
                  onChange={e => setDailyLossInput(Number(e.target.value))}
                  style={{ width: '100%', padding: '8px 12px', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255, 0, 127, 0.3)', borderRadius: '4px', color: '#fff', fontFamily: 'Share Tech Mono, monospace', fontSize: '0.8rem', outline: 'none' }}
                />
              </div>
              <div>
                <label style={{ fontSize: '0.7rem', opacity: 0.7, display: 'block', marginBottom: '4px', fontFamily: 'Share Tech Mono, monospace' }}>Max Concurrent Positions</label>
                <input
                  type="number"
                  value={maxPositionsInput}
                  onChange={e => setMaxPositionsInput(Number(e.target.value))}
                  style={{ width: '100%', padding: '8px 12px', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255, 0, 127, 0.3)', borderRadius: '4px', color: '#fff', fontFamily: 'Share Tech Mono, monospace', fontSize: '0.8rem', outline: 'none' }}
                />
              </div>
            </div>
            <button
              onClick={handleSaveConfig}
              style={{ padding: '10px', background: '#ff007f', border: 'none', color: '#fff', fontFamily: 'Orbitron, sans-serif', fontWeight: 700, borderRadius: '4px', cursor: 'pointer', marginTop: '6px' }}
            >
              SAVE CONFIGURATION
            </button>
          </div>
        </div>

        {/* Live Audit Log Stream */}
        <div style={{ background: 'rgba(7, 11, 29, 0.75)', border: '1px solid rgba(0, 243, 255, 0.16)', borderRadius: '6px', padding: '20px', backdropFilter: 'blur(8px)', display: 'flex', flexDirection: 'column' }}>
          <h4 style={{ fontFamily: 'Orbitron, sans-serif', margin: '0 0 12px 0', fontSize: '0.9rem', color: 'var(--accent-cyan, #00f3ff)', letterSpacing: '2px', textTransform: 'uppercase' }}>
            Live Audit Stream
          </h4>
          <div style={{ flex: 1, minHeight: '200px', maxHeight: '280px', overflowY: 'auto', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '4px', padding: '12px', fontFamily: 'Share Tech Mono, monospace', fontSize: '0.75rem', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {auditLog.length === 0 ? (
              <div style={{ color: 'rgba(255,255,255,0.4)', textAlign: 'center', marginTop: '30px' }}>
                [System] Swarm listening... Awaiting next transaction audit.
              </div>
            ) : (
              auditLog.map((entry, idx) => (
                <div key={idx} style={{ lineHeight: 1.4, borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '4px' }}>
                  <span style={{ color: 'var(--accent-cyan, #00f3ff)' }}>[{new Date(entry.timestamp).toLocaleTimeString()}]</span>{' '}
                  <strong style={{ color: '#39ff14' }}>{entry.action}</strong>{' '}
                  <span style={{ opacity: 0.6, fontSize: '0.7rem' }}>by {entry.user_id || 'system'}</span>
                  {entry.details?.total_usd !== undefined && (
                    <span style={{ color: '#ffaa00', marginLeft: '6px' }}>+${Number(entry.details.total_usd).toFixed(4)} USD</span>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
