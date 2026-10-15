import { chromium } from 'playwright';
const base = 'http://localhost:5177';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
await page.goto(base, { waitUntil: 'networkidle', timeout: 20000 });
// get credentials from env? Ask server: auth via POST? inspect endpoints:
const r = await page.evaluate(async () => {
  const res = await fetch('/api/auth/login', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ username:'lumba', password:'xarel' }) });
  return { s: res.status, b: (await res.text()).slice(0,200) };
});
console.log('login attempt:', JSON.stringify(r));
await browser.close();
