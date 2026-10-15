import { GameController } from './GameController';

/**
 * Virtual gamepad bridge for the XR surface.
 *
 * Jen's pad lives on the hands/motor port (8410, foveai-gamepad.service). It
 * stays disconnected unless explicitly enabled, so it never competes with your
 * real controllers — including the Saitek ST-90 — until you ask for it.
 *
 * Enable either way:
 *   ?gamepad=1                       in the URL
 *   localStorage.setItem('foveai_gamepad', '1')
 *   FoveAI.gamepad.enable()          in the console
 */

const ENABLED = (): boolean => {
  try {
    if (new URLSearchParams(location.search).get('gamepad') === '1') return true;
    return localStorage.getItem('foveai_gamepad') === '1';
  } catch {
    return false;
  }
};

let controller: GameController | null = null;

async function enable(): Promise<boolean> {
  if (controller) return true;
  const gc = new GameController();
  const ok = await gc.connect();
  if (!ok) {
    // Name the failure instead of leaving a dead pad: the usual cause is that
    // foveai-gamepad.service is not running.
    console.warn('[GameCtrl] could not reach the gamepad service on 8410 — is foveai-gamepad.service active?');
    return false;
  }
  controller = gc;
  (window as any).FoveAI = (window as any).FoveAI || {};
  (window as any).FoveAI.gamepad = {
    press: (i: number) => controller?.press(i),
    release: (i: number) => controller?.release(i),
    stick: (x: number, y: number) => controller?.moveLeftStick(x, y),
    look: (x: number, y: number) => controller?.moveRightStick(x, y),
    disable: () => { controller?.disconnect(); controller = null; },
  };
  console.log('[GameCtrl] Jen\'s virtual controller is live — FoveAI.gamepad.press(0) to try A.');
  return true;
}

if (ENABLED()) void enable();

export const gamepadBridge = { enable, get connected() { return !!controller; } };
