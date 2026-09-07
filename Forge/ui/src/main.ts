import { ForgeCore } from './ForgeCore';
import { ForgeDashboard } from './components/ForgeDashboard';

(window as any).FORGE_VERSION = '1.0.0';
(window as any).FORGE_API = 'http://127.0.0.1:8100';

async function boot() {
  console.log('[FORGE] Booting AI-Native IDE...');
  const core = new ForgeCore();
  (window as any).forgeCore = core;
  await core.connect();
  const dashboard = new ForgeDashboard(core);
  (window as any).forgeDashboard = dashboard;
  const loader = document.getElementById('loading-screen');
  if (loader) { loader.classList.add('hidden'); setTimeout(() => loader.remove(), 600); }
  console.log('[FORGE] Ready');
}

boot().catch(err => {
  console.error('[FORGE] Boot failed:', err);
  const loader = document.getElementById('loading-screen');
  if (loader) loader.innerHTML = '<div style="color:#f44;text-align:center"><h2>Boot Failed</h2><p>'+err.message+'</p></div>';
});
