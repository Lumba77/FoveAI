import React from 'react';
import { NEWS, type NewsEntry } from '../../news';

const TAG_COLORS: Record<NewsEntry['tag'], string> = {
  feature: 'var(--neon-green, #4dffa0)',
  fix: '#ffb347',
  infra: 'var(--accent-cyan, #00f3ff)',
  persona: 'var(--neon-pink, #ff007f)',
};

export const NewsTab: React.FC = () => (
  <div style={{ flex: 1, overflowY: 'auto', padding: '24px', maxWidth: '760px', margin: '0 auto', width: '100%' }}>
    <h3 style={{ fontFamily: 'Orbitron', color: 'var(--accent-cyan, #00f3ff)', letterSpacing: '3px', margin: '0 0 4px 0' }}>
      📰 LATEST NEWS
    </h3>
    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'Share Tech Mono', margin: '0 0 20px 0' }}>
      What changed in FoveAI — newest first.
    </p>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {NEWS.map((n, i) => (
        <div key={i} className="glass-card" style={{
          padding: '16px 18px',
          background: 'rgba(0,0,0,0.4)',
          border: '1px solid var(--border)',
          borderLeft: `3px solid ${TAG_COLORS[n.tag]}`,
          borderRadius: '4px',
        }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px', flexWrap: 'wrap' }}>
            <span style={{ fontFamily: 'Share Tech Mono', fontSize: '0.65rem', color: 'var(--text-muted)' }}>{n.date}</span>
            <span style={{
              fontFamily: 'Share Tech Mono', fontSize: '0.6rem', letterSpacing: '1px',
              color: TAG_COLORS[n.tag], border: `1px solid ${TAG_COLORS[n.tag]}`,
              padding: '1px 6px', borderRadius: '3px', textTransform: 'uppercase',
            }}>{n.tag}</span>
            <span style={{ color: '#fff', fontSize: '0.9rem', fontWeight: 600 }}>{n.title}</span>
          </div>
          <p style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.75)', lineHeight: 1.5, margin: '8px 0 0 0', fontFamily: 'Share Tech Mono' }}>
            {n.body}
          </p>
        </div>
      ))}
    </div>
  </div>
);
