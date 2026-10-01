# Forge Spec: Swarm Maintenance & Self-Sovereign Administration

## Objective
Enable the Drone Swarm to manage its own infrastructure (Cloudflare + Tailscale) without user intervention for 90+ days.

## Agentic Roles
### 1. The KeyMaster (Sentry Drone)
- **APIs:** Tailscale API (LUMAX_TS_API), Cloudflare API (LUMAX_CF_API).
- **Logic:** 
  - Check Tailscale node expiration.
  - Rotate Cloudflare Access tokens.
  - Update .env with new secrets.

### 2. The NetMarshal (Scout Drone Expansion)
- **APIs:** OS Subprocess, Cloudflare Tunnel JSON API.
- **Logic:**
  - Verify 1um6a.se is resolving to the local stack.
  - Auto-restart cloudflared or 	ailscale services on failure.
  - Log network "heals" to the WebUI.

## Timeline
- [ ] Phase 1: Enable .env writing permissions for Drones.
- [ ] Phase 2: Implement Tailscale Key Rotation script in Forge.
- [ ] Phase 3: Wire NetMarshal to the Swarm UI.
