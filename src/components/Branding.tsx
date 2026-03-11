import React, { useEffect } from 'react';

/**
 * C0mr4deBranding: Aggressively removes Blink branding and adds a 
 * personalized watermark to the application.
 */
export function C0mr4deBranding() {
    useEffect(() => {
        // 1. Inject Styles to hide Blink and style c0mr4de
        const styleId = 'c0mr4de-branding-styles';
        if (!document.getElementById(styleId)) {
            const style = document.createElement('style');
            style.id = styleId;
            style.innerHTML = `
        /* Hide Blink artifacts */
        #blink-badge, 
        .blink-badge,
        [class*="blink-badge"],
        a[href*="blink.new"],
        iframe[src*="blink"],
        div[style*="fixed"] > a[href*="blink"],
        div[style*="absolute"] > a[href*="blink"],
        div[style*="position: fixed"] > a[href*="blink"],
        div[style*="z-index: 2147483647"] {
          display: none !important;
          visibility: hidden !important;
          opacity: 0 !important;
          pointer-events: none !important;
          z-index: -9999 !important;
        }

        /* Personalized Watermark Style */
        .c0mr4de-watermark {
          position: fixed;
          bottom: 1rem;
          right: 1rem;
          font-family: 'Geist Mono', monospace;
          font-size: 0.65rem;
          color: hsl(var(--muted-foreground));
          opacity: 0.4;
          letter-spacing: 0.2em;
          text-transform: uppercase;
          pointer-events: none;
          z-index: 100;
          display: flex;
          align-items: center;
          gap: 0.5rem;
          mix-blend-mode: difference;
        }

        .c0mr4de-dot {
          width: 4px;
          height: 4px;
          background-color: hsl(var(--primary));
          border-radius: 50%;
          animation: c0mr4de-pulse 2s infinite;
        }

        @keyframes c0mr4de-pulse {
          0%, 100% { opacity: 0.3; }
          50% { opacity: 1; }
        }
      `;
            document.head.appendChild(style);
        }

        // 2. Continuous Cleanup - ensure new badges are removed
        const cleanup = () => {
            // Find elements containing "Blink" text that look like badges
            const nodes = document.querySelectorAll('div, a, span');
            nodes.forEach(node => {
                if (node.textContent?.toLowerCase().includes('made with blink')) {
                    (node as HTMLElement).style.display = 'none';
                    // Try to hide parents if they are fixed/absolute containers
                    let parent = node.parentElement;
                    while (parent && parent !== document.body) {
                        const pos = window.getComputedStyle(parent).position;
                        if (pos === 'fixed' || pos === 'absolute') {
                            parent.style.display = 'none';
                            break;
                        }
                        parent = parent.parentElement;
                    }
                }
            });

            // Targeted removal of the specific fixed anchor if it exists
            document.querySelectorAll('a[href*="blink.new"]').forEach(el => {
                const parent = el.parentElement;
                if (parent) {
                    parent.style.display = 'none';
                }
            });
        };

        const observer = new MutationObserver(cleanup);
        observer.observe(document.body, { childList: true, subtree: true });

        cleanup();
        return () => observer.disconnect();
    }, []);

    return (
        <div className="c0mr4de-watermark">
            <span className="c0mr4de-dot"></span>
            OPERATOR: C0MR4DE TERMINAL
        </div>
    );
}
