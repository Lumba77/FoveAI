/**
 * AgentBridge — Frontend client for /api/agent/* endpoints
 * 
 * Bridges the XR_Vessel dashboard to the autonomous agent backend
 * (compagent.py). Provides real-time status, control, and activity
 * streaming for Jen's autonomous persona.
 */

export type LogFn = (msg: string, color?: string) => void;

export interface AgentStatus {
    running: boolean;
    mode: string;           // 'companion' | 'developer' | 'off'
    loop_count: number;
    uptime_seconds: number;
    safety: {
        cpu_pct: number;
        ram_pct: number;
        error_rate: number;
        consecutive_loops: number;
        max_consecutive_loops: number;
        braked: boolean;
        brake_reason: string | null;
    };
    queue_size: number;
    last_thought_at: string | null;
    last_action_at: string | null;
}

export interface AgentMessage {
    id: string;
    role: string;
    content: string;
    timestamp: string;
    read: boolean;
}

export interface AgentThought {
    id: string;
    content: string;
    timestamp: string;
    tags: string[];
}

export interface AgentAction {
    id: string;
    type: string;
    description: string;
    timestamp: string;
    result: string | null;
}

export interface AgentPlan {
    id: string;
    title: string;
    description: string;
    status: string;         // 'active' | 'completed' | 'aborted'
    created_at: string;
    steps: Array<{
        description: string;
        completed: boolean;
    }>;
}

export interface AgentContext {
    summary: string;
    active_plan_count: number;
    pending_message_count: number;
    unread_message_count: number;
    journal_entry_count: number;
    creative_work_count: number;
    idle_life_summary: string | null;
}

export interface QueueStats {
    total_enqueued: number;
    total_processed: number;
    current_queue_size: number;
    avg_process_time_ms: number;
}

export interface AgentGoal {
    id: number;
    title: string;
    description: string;
    priority: number;
    status: string;          // 'active' | 'completed' | 'abandoned'
    progress_pct: number;
    created_at: string;
    completed_at: string | null;
    notes: string | null;
}

export class AgentBridge {
    private log: LogFn;
    private baseUrl: string;
    private statusPollInterval: ReturnType<typeof setInterval> | null = null;
    private statusCallbacks: Array<(status: AgentStatus) => void> = [];

    constructor(logFn: LogFn, baseUrl?: string) {
        this.log = logFn;
        this.baseUrl = baseUrl || '';
    }

    // ── Control ──────────────────────────────────────────────

    /** Start the autonomous agent loop */
    async start(): Promise<{ success: boolean; message: string }> {
        const url = `${this.baseUrl}/api/agent/start`;
        this.log(`[AgentBridge] Starting autonomous loop...`, '#00f3ff');
        const res = await fetch(url, { method: 'POST' });
        if (!res.ok) throw new Error(`agent start failed: ${res.status}`);
        return await res.json();
    }

    /** Stop the autonomous agent loop */
    async stop(): Promise<{ success: boolean; message: string }> {
        const url = `${this.baseUrl}/api/agent/stop`;
        this.log(`[AgentBridge] Stopping autonomous loop...`, '#ff007f');
        const res = await fetch(url, { method: 'POST' });
        if (!res.ok) throw new Error(`agent stop failed: ${res.status}`);
        return await res.json();
    }

    // ── Status ───────────────────────────────────────────────

    /** Get current agent status (loop state, safety, vitals) */
    async getStatus(): Promise<AgentStatus> {
        const url = `${this.baseUrl}/api/agent/status`;
        const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
        if (!res.ok) throw new Error(`agent status failed: ${res.status}`);
        return await res.json();
    }

    /** Start polling status every `intervalMs` milliseconds */
    startStatusPolling(intervalMs: number = 3000): void {
        if (this.statusPollInterval) return;
        this.statusPollInterval = setInterval(async () => {
            try {
                const status = await this.getStatus();
                this.statusCallbacks.forEach(cb => cb(status));
            } catch (err) {
                // Silently skip — backend may be restarting
            }
        }, intervalMs);
        this.log(`[AgentBridge] Status polling started (${intervalMs}ms)`, '#39ff14');
    }

    /** Stop status polling */
    stopStatusPolling(): void {
        if (this.statusPollInterval) {
            clearInterval(this.statusPollInterval);
            this.statusPollInterval = null;
            this.log(`[AgentBridge] Status polling stopped`, '#ff007f');
        }
    }

    /** Register a callback for status updates */
    onStatus(callback: (status: AgentStatus) => void): void {
        this.statusCallbacks.push(callback);
    }

    // ── Activity Feeds ───────────────────────────────────────

    /** Get recent autonomous messages */
    async getMessages(limit: number = 20): Promise<AgentMessage[]> {
        const url = `${this.baseUrl}/api/agent/messages?limit=${limit}`;
        const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
        if (!res.ok) throw new Error(`agent messages failed: ${res.status}`);
        const data = await res.json();
        return data.messages || [];
    }

    /** Mark messages as read */
    async markMessages(messageIds: string[]): Promise<void> {
        const url = `${this.baseUrl}/api/agent/messages/mark`;
        await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(messageIds),
        });
    }

    /** Get recent thoughts */
    async getThoughts(limit: number = 20): Promise<AgentThought[]> {
        const url = `${this.baseUrl}/api/agent/thoughts?limit=${limit}`;
        const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
        if (!res.ok) throw new Error(`agent thoughts failed: ${res.status}`);
        const data = await res.json();
        return data.thoughts || [];
    }

    /** Get recent actions */
    async getActions(limit: number = 20): Promise<AgentAction[]> {
        const url = `${this.baseUrl}/api/agent/actions?limit=${limit}`;
        const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
        if (!res.ok) throw new Error(`agent actions failed: ${res.status}`);
        const data = await res.json();
        return data.actions || [];
    }

    /** Get active plans */
    async getPlans(): Promise<AgentPlan[]> {
        const url = `${this.baseUrl}/api/agent/plans`;
        const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
        if (!res.ok) throw new Error(`agent plans failed: ${res.status}`);
        const data = await res.json();
        return data.plans || [];
    }

    /** Get a specific plan by ID */
    async getPlan(planId: string): Promise<AgentPlan | null> {
        const url = `${this.baseUrl}/api/agent/plan/${encodeURIComponent(planId)}`;
        const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
        if (!res.ok) {
            if (res.status === 404) return null;
            throw new Error(`agent plan fetch failed: ${res.status}`);
        }
        return await res.json();
    }

    // ── Context & Memory ─────────────────────────────────────

    /** Get agent context summary */
    async getContext(): Promise<AgentContext> {
        const url = `${this.baseUrl}/api/agent/context`;
        const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
        if (!res.ok) throw new Error(`agent context failed: ${res.status}`);
        return await res.json();
    }

    /** Read a memory value by key */
    async getMemory(key: string): Promise<any> {
        const url = `${this.baseUrl}/api/agent/memory/${encodeURIComponent(key)}`;
        const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
        if (!res.ok) {
            if (res.status === 404) return null;
            throw new Error(`agent memory read failed: ${res.status}`);
        }
        const data = await res.json();
        return data.value ?? null;
    }

    /** Set a memory value */
    async setMemory(key: string, value: any): Promise<{ success: boolean }> {
        const url = `${this.baseUrl}/api/agent/memory`;
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key, value }),
        });
        if (!res.ok) throw new Error(`agent memory set failed: ${res.status}`);
        return await res.json();
    }

    // ── Queue ─────────────────────────────────────────────────

    /** Get queue statistics */
    async getQueueStats(): Promise<QueueStats> {
        const url = `${this.baseUrl}/api/agent/queue/stats`;
        const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
        if (!res.ok) throw new Error(`agent queue stats failed: ${res.status}`);
        return await res.json();
    }

    // ── Message Enqueue (for user → agent communication) ─────

    /** Enqueue a message for the agent to process */
    async enqueueMessage(content: string, priority: number = 0): Promise<{ success: boolean; message_id: string }> {
        const url = `${this.baseUrl}/api/agent/message`;
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content, priority }),
        });
        if (!res.ok) throw new Error(`agent enqueue failed: ${res.status}`);
        return await res.json();
    }

    /** Create a plan for the agent */
    async createPlan(title: string, description: string, steps: string[]): Promise<{ success: boolean; plan_id: string }> {
        const url = `${this.baseUrl}/api/agent/plan`;
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, description, steps }),
        });
        if (!res.ok) throw new Error(`agent plan create failed: ${res.status}`);
        return await res.json();
    }

    // ── Goals ────────────────────────────────────────────────

    /** Get all goals, optionally filtered by status */
    async getGoals(status?: string): Promise<AgentGoal[]> {
        const params = status ? `?status=${encodeURIComponent(status)}` : '';
        const url = `${this.baseUrl}/api/agent/goals${params}`;
        const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
        if (!res.ok) throw new Error(`agent goals failed: ${res.status}`);
        const data = await res.json();
        return data.goals || [];
    }

    /** Get active goals only */
    async getActiveGoals(): Promise<AgentGoal[]> {
        const url = `${this.baseUrl}/api/agent/goals/active`;
        const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
        if (!res.ok) throw new Error(`agent active goals failed: ${res.status}`);
        const data = await res.json();
        return data.goals || [];
    }

    /** Get a specific goal by ID */
    async getGoal(goalId: number): Promise<AgentGoal | null> {
        const url = `${this.baseUrl}/api/agent/goals/${goalId}`;
        const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
        if (!res.ok) {
            if (res.status === 404) return null;
            throw new Error(`agent goal fetch failed: ${res.status}`);
        }
        return await res.json();
    }

    /** Create a new goal for the agent */
    async createGoal(title: string, description: string, priority: number = 5): Promise<{ success: boolean; goal_id: number }> {
        const url = `${this.baseUrl}/api/agent/goals`;
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, description, priority }),
        });
        if (!res.ok) throw new Error(`agent goal create failed: ${res.status}`);
        return await res.json();
    }

    /** Update goal progress */
    async updateGoalProgress(goalId: number, progressPct: number, notes?: string): Promise<{ success: boolean }> {
        const url = `${this.baseUrl}/api/agent/goals/${goalId}/progress`;
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ progress_pct: progressPct, notes }),
        });
        if (!res.ok) throw new Error(`agent goal progress update failed: ${res.status}`);
        return await res.json();
    }

    /** Mark a goal as completed */
    async completeGoal(goalId: number, notes?: string): Promise<{ success: boolean }> {
        const url = `${this.baseUrl}/api/agent/goals/${goalId}/complete`;
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notes }),
        });
        if (!res.ok) throw new Error(`agent goal complete failed: ${res.status}`);
        return await res.json();
    }

    /** Abandon a goal */
    async abandonGoal(goalId: number, reason?: string): Promise<{ success: boolean }> {
        const url = `${this.baseUrl}/api/agent/goals/${goalId}/abandon`;
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason }),
        });
        if (!res.ok) throw new Error(`agent goal abandon failed: ${res.status}`);
        return await res.json();
    }

    // ── Lifecycle ────────────────────────────────────────────

    /** Clean up polling and callbacks */
    destroy(): void {
        this.stopStatusPolling();
        this.statusCallbacks = [];
    }
}

/** Singleton instance for the XR_Vessel */
export const agentBridge = new AgentBridge(
    (msg, color) => {
        (window as any).log?.(msg, color);
    }
);