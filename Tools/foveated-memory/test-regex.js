const content = "a.b.c.d.e.f.g.h.i.j.k.l.m.n.o.p.q.r.s.t.u.v.w.x.y.z.".repeat(1000) + "txt";
const start = Date.now();
const match = content.match(/([A-Za-z]:[\\/][^\s,\u201c\u201d"']+|[a-zA-Z0-9_/.-]+\.(?:py|ts|js|json|md|xml|kt|html|css))/);
console.log(`Matched in ${Date.now() - start}ms`);
