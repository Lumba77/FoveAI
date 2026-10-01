import { createServer } from 'vite'
const s = await createServer({ configFile: '/home/lumba/FoveAI/Frontend/multigate/vite.config.ts', root: '/home/lumba/FoveAI/Frontend/multigate', server: { port: 5199 }, logLevel: 'warn' })
const mk = (i) => (req, res, next) => { if ((req.url||'').includes('webvm')) console.log('AT', i, req.url); next() }
for (let i = 1; i <= 6; i++) s.middlewares.stack.splice(i, 0, { route: '', handle: mk(i) })
await s.listen()
console.log('PROBE READY')
