import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
await page.goto('http://localhost:5177/', { waitUntil: 'domcontentloaded' });
await page.evaluate(() => {
  localStorage.setItem('foveai_foveai_user', JSON.stringify({ ok:true, username:'lumba', apiKey:'foveai_lumba', role:'admin', firstName:'Daniel', aiName:'Jen' }));
  try { sessionStorage.removeItem('foveai_ignited'); } catch {}
});
await page.reload({ waitUntil: 'networkidle' });
await page.waitForTimeout(4500);
await page.screenshot({ path: '/tmp/opencode/vault1.png' });
const ball = await page.$('.tb-ball');
if (ball) { await ball.click(); await page.waitForTimeout(2200); await page.screenshot({ path: '/tmp/opencode/vault2_core.png' }); }
if (ball) { await ball.click(); await page.waitForTimeout(2200); await page.screenshot({ path: '/tmp/opencode/vault3_armed.png' }); }
console.log('shots done');
await browser.close();
