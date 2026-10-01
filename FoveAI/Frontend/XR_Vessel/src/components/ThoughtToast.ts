export class ThoughtToast {
    private element: HTMLElement;
    private body: HTMLElement;
    private timeout: any = null;

    constructor() {
        this.element = document.createElement('div');
        this.element.id = 'thought-toast';
        this.element.className = 'thought-toast';
        this.element.innerHTML = `
            <div class="thought-toast-title">THOUGHT STREAM</div>
            <div id="thought-toast-body" class="thought-toast-body"></div>
        `;
        document.body.appendChild(this.element);
        this.body = this.element.querySelector('#thought-toast-body') as HTMLElement;
        this.applyStyles();
    }

    private applyStyles() {
        const style = document.createElement('style');
        style.textContent = `
            .thought-toast {
                position: fixed;
                left: 20px;
                bottom: 20px;
                width: min(500px, calc(100vw - 40px));
                max-height: 300px;
                background: rgba(10, 15, 25, 0.3);
                backdrop-filter: blur(15px);
                border: 1px solid rgba(0, 243, 255, 0.3);
                border-radius: 8px;
                padding: 15px;
                z-index: 9999;
                display: flex;
                flex-direction: column;
                gap: 8px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.4);
                opacity: 0;
                transform: translateY(20px);
                pointer-events: none;
                transition: all 0.4s cubic-bezier(0.19, 1, 0.22, 1);
            }

            .thought-toast.show {
                opacity: 1;
                transform: translateY(0);
                pointer-events: auto;
            }

            .thought-toast-title {
                font-family: 'Orbitron', sans-serif;
                font-size: 0.65rem;
                letter-spacing: 2px;
                color: var(--neon-blue);
                text-transform: uppercase;
                font-weight: 700;
            }

            .thought-toast-body {
                font-family: 'Share Tech Mono', monospace;
                font-size: 0.85rem;
                color: rgba(255, 255, 255, 0.9);
                line-height: 1.4;
                overflow-y: auto;
                white-space: pre-wrap;
            }
        `;
        document.head.appendChild(style);
    }

    public show(text: string, duration: number = 15000) {
        if (!text) return;
        
        // Don't show technical JSON or raw thinking if it's too messy
        // But the user might want to see JEN's raw thoughts.
        
        this.body.textContent = text;
        this.element.classList.add('show');
        
        if (this.timeout) clearTimeout(this.timeout);
        this.timeout = setTimeout(() => {
            this.element.classList.remove('show');
        }, duration);
    }
}

export const thoughtToast = new ThoughtToast();
