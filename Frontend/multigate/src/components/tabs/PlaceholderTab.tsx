import React from 'react';

interface PlaceholderTabProps {
  title: string;
  icon: string;
  description?: string;
}

export const PlaceholderTab: React.FC<PlaceholderTabProps> = ({ title, icon, description }) => {
  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '40px',
      textAlign: 'center',
      background: 'rgba(0, 0, 0, 0.2)',
      borderRadius: '8px',
      border: '1px solid rgba(255, 255, 255, 0.05)',
      boxShadow: 'inset 0 0 50px rgba(0, 0, 0, 0.5)'
    }}>
      <div style={{ fontSize: '4rem', marginBottom: '20px', opacity: 0.8, textShadow: '0 0 20px rgba(0, 243, 255, 0.3)' }}>
        {icon}
      </div>
      <h2 style={{ fontFamily: 'Orbitron, sans-serif', fontSize: '1.5rem', color: 'var(--text-bright)', marginBottom: '10px', letterSpacing: '2px' }}>
        {title.toUpperCase()}
      </h2>
      <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem', maxWidth: '400px', lineHeight: '1.5' }}>
        {description || "This module is currently being calibrated in the Forge. Neural pathways for this subsystem will be operational soon."}
      </p>
      
      <div style={{
        marginTop: '30px',
        padding: '10px 20px',
        background: 'rgba(0, 243, 255, 0.05)',
        border: '1px solid rgba(0, 243, 255, 0.2)',
        borderRadius: '20px',
        color: 'var(--accent-cyan)',
        fontSize: '0.75rem',
        fontFamily: 'Orbitron, sans-serif',
        letterSpacing: '1px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px'
      }}>
        <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--accent-cyan)', boxShadow: '0 0 8px var(--accent-cyan)', animation: 'pulse 2s infinite' }} />
        UNDER CONSTRUCTION
      </div>
    </div>
  );
};
