/**
 * stats.js — LumaxConProxy Traffic Statistics
 * Tracks tokens saved, requests intercepted, cost estimates.
 */

'use strict';

const state = {
    startTime:    Date.now(),
    intercepted:  0,
    tunneled:     0,
    passed:       0,
    tokensSaved:  0,
    costSavedUSD: 0,
    recentLog:    [], // last 100 entries
    byHost:       {},
};

// Rough cost: $15 per 1M tokens (GPT-4o input pricing as baseline)
const COST_PER_TOKEN = 15 / 1_000_000;

function record(type, host, tokensSaved = 0) {
    const entry = { time: Date.now(), type, host, tokensSaved };

    if (type === 'strip') {
        state.intercepted++;
        state.tokensSaved += tokensSaved;
        state.costSavedUSD += tokensSaved * COST_PER_TOKEN;
    } else if (type === 'tunnel') {
        state.tunneled++;
    } else {
        state.passed++;
    }

    // Per-host breakdown
    if (!state.byHost[host]) state.byHost[host] = { intercepted: 0, tokensSaved: 0 };
    if (type === 'strip') {
        state.byHost[host].intercepted++;
        state.byHost[host].tokensSaved += tokensSaved;
    }

    state.recentLog.unshift(entry);
    if (state.recentLog.length > 100) state.recentLog.pop();
}

function getSnapshot() {
    const uptime = Math.round((Date.now() - state.startTime) / 1000);
    return {
        uptime,
        intercepted:  state.intercepted,
        tunneled:     state.tunneled,
        passed:       state.passed,
        tokensSaved:  state.tokensSaved,
        costSavedUSD: state.costSavedUSD.toFixed(4),
        recentLog:    state.recentLog.slice(0, 20),
        byHost:       state.byHost,
    };
}

module.exports = { record, getSnapshot };
