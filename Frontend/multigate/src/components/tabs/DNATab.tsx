import React, { useRef } from 'react';

export const DNATab: React.FC = () => {
  const handleIframeLoad = (e: React.SyntheticEvent<HTMLIFrameElement, Event>) => {
    try {
      const iframeDoc = e.currentTarget.contentDocument;
      if (iframeDoc) {
        // Inject a style block to force a transparent background and light text
        // without breaking the complex UI layout of Promethease.
        const style = iframeDoc.createElement('style');
        style.innerHTML = `
          body, html {
            background: transparent !important;
            background-color: transparent !important;
            color: rgba(255, 255, 255, 0.9) !important;
          }
          .ui-widget-content, .dataTables_wrapper, table.dataTable {
            background: rgba(0, 0, 0, 0.4) !important;
            color: inherit !important;
          }
          .ui-widget-header {
            background: rgba(0, 0, 0, 0.6) !important;
            color: var(--accent-cyan, #00f3ff) !important;
            border-color: rgba(255,255,255,0.1) !important;
          }
          a {
            color: var(--accent-cyan, #00f3ff) !important;
          }
        `;
        iframeDoc.head.appendChild(style);
        
        // Inherit parent CSS variables
        const parentStyle = window.getComputedStyle(document.documentElement);
        iframeDoc.documentElement.style.setProperty('--accent-cyan', parentStyle.getPropertyValue('--accent-cyan'));
      }
    } catch (err) {
      console.warn("Could not theme DNA iframe. CORS or cross-origin might be blocking.", err);
    }
  };

  return (
    <div style={{ flex: 1, width: '100%', height: '100%', overflow: 'hidden', background: 'transparent' }}>
      <iframe
        src="/dna/index.html"
        onLoad={handleIframeLoad}
        style={{ width: '100%', height: '100%', border: 'none', background: 'transparent' }}
        title="DNA Promethease Report"
      />
    </div>
  );
};
