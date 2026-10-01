/**
 * GalleryTab — Image/Art upload & browse gallery for FoveAI
 * Reads from /Uploads/ via /api/uploads/list, uploads via /api/uploads/upload
 */
export class GalleryTab {
    private static container: HTMLElement | null = null;
    private static currentFolder = 'Images';
    private static files: any[] = [];
    private static folders: any[] = [];
    private static lightboxEl: HTMLElement | null = null;
    private static uploadInput: HTMLInputElement | null = null;

    public static render(container: HTMLElement) {
        this.container = container;
        container.innerHTML = `
            <div class="breadcrumb">GALLERY // ${this.currentFolder.toUpperCase()}</div>
            <div id="gallery-toolbar" style="display:flex; gap:8px; margin-bottom:12px; align-items:center; flex-wrap:wrap;">
                <button id="gallery-upload-btn" style="background:rgba(0,243,255,0.15); border:1px solid var(--neon-blue); color:var(--neon-blue); font-family:'Orbitron'; font-size:0.6rem; padding:8px 14px; cursor:pointer; border-radius:4px; letter-spacing:1px; text-transform:uppercase; display:flex; align-items:center; gap:6px;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                    UPLOAD
                </button>
                <button id="gallery-refresh-btn" style="background:transparent; border:1px solid var(--border); color:#fff; font-family:'Orbitron'; font-size:0.55rem; padding:8px 12px; cursor:pointer; border-radius:4px; letter-spacing:1px; text-transform:uppercase;">↻ REFRESH</button>
                <span id="gallery-count" style="font-family:'Share Tech Mono'; font-size:0.65rem; color:rgba(255,255,255,0.4); margin-left:auto;"></span>
            </div>
            <input type="file" id="gallery-file-input" multiple accept=".jpg,.jpeg,.png,.gif,.svg,.webp,.tiff,.tif,.bmp,.mp3,.wav,.flac,.ogg,.pdf,.mp4,.mpeg,.mpg,.webm,.mov,.avi,.mkv" style="display:none;">
            <div id="gallery-folder-bar" style="display:flex; gap:6px; margin-bottom:10px; flex-wrap:wrap;"></div>
            <div id="gallery-grid" style="display:grid; grid-template-columns:repeat(auto-fill, minmax(120px, 1fr)); gap:10px; overflow-y:auto; max-height:calc(100vh - 280px);"></div>
            <div id="gallery-empty" style="display:none; text-align:center; padding:40px; opacity:0.4; font-family:'Share Tech Mono'; font-size:0.8rem;">No files yet — upload your art!</div>
        `;

        // Wire buttons
        const uploadBtn = container.querySelector('#gallery-upload-btn');
        this.uploadInput = container.querySelector('#gallery-file-input') as HTMLInputElement;
        uploadBtn?.addEventListener('click', () => this.uploadInput?.click());
        this.uploadInput?.addEventListener('change', () => this.handleUpload());

        const refreshBtn = container.querySelector('#gallery-refresh-btn');
        refreshBtn?.addEventListener('click', () => this.load());

        // Create lightbox
        if (!document.getElementById('gallery-lightbox')) {
            const lb = document.createElement('div');
            lb.id = 'gallery-lightbox';
            lb.style.cssText = 'position:fixed;top:0;left:0;width:100vw;height:100vh;background:rgba(0,0,0,0.92);z-index:10000;display:none;align-items:center;justify-content:center;cursor:pointer;backdrop-filter:blur(10px);';
            lb.innerHTML = `<img id="gallery-lightbox-img" style="max-width:90vw;max-height:90vh;border-radius:8px;box-shadow:0 0 40px rgba(0,243,255,0.2);">`;
            lb.addEventListener('click', () => { lb.style.display = 'none'; });
            document.body.appendChild(lb);
            this.lightboxEl = lb;
        }

        this.load();
    }

    private static async load() {
        if (!this.container) return;
        try {
            const resp = await fetch(`/api/uploads/list?folder=${encodeURIComponent(this.currentFolder)}`);
            if (!resp.ok) throw new Error('Failed to load gallery');
            const data = await resp.json();
            this.files = data.files || [];
            this.folders = data.folders || [];
            this.renderGrid();
        } catch (e) {
            this.container.querySelector('#gallery-grid')!.innerHTML = `<div style="color:var(--neon-pink); font-size:0.75rem;">Error: ${e}</div>`;
        }
    }

    private static renderGrid() {
        if (!this.container) return;

        // Folder bar
        const folderBar = this.container.querySelector('#gallery-folder-bar')!;
        if (this.folders.length > 0) {
            folderBar.innerHTML = this.folders.map(f =>
                `<button class="gallery-folder-btn" data-folder="${f.name}" style="background:rgba(255,255,255,0.05); border:1px solid var(--border); color:var(--neon-blue); font-family:'Share Tech Mono'; font-size:0.6rem; padding:5px 10px; cursor:pointer; border-radius:3px;">📁 ${f.name}</button>`
            ).join('');
            folderBar.querySelectorAll('.gallery-folder-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    this.currentFolder = (btn as HTMLElement).getAttribute('data-folder')!;
                    this.load();
                });
            });
        } else {
            folderBar.innerHTML = '';
        }

        // Count
        const countEl = this.container.querySelector('#gallery-count')!;
        countEl.textContent = `${this.files.length} file${this.files.length !== 1 ? 's' : ''}`;

        // Grid
        const grid = this.container.querySelector('#gallery-grid')!;
        const empty = this.container.querySelector('#gallery-empty')! as HTMLElement;

        if (this.files.length === 0) {
            grid.innerHTML = '';
            empty.style.display = 'block';
            return;
        }
        empty.style.display = 'none';

        grid.innerHTML = this.files.map((f: any) => {
            if (f.type === 'image') {
                return `<div class="gallery-item" data-url="${f.url}" data-name="${f.name}" data-type="${f.type}" style="cursor:pointer;">
                    <div class="gallery-thumb" style="width:100%;aspect-ratio:1;background:url('${f.url}') center/cover;border-radius:6px;border:1px solid var(--border);transition:var(--transition);"></div>
                    <div style="font-size:0.5rem;font-family:'Share Tech Mono';color:rgba(255,255,255,0.5);margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${f.name}">${f.name}</div>
                </div>`;
            } else if (f.type === 'video') {
                return `<div class="gallery-item" data-url="${f.url}" data-name="${f.name}" data-type="${f.type}" style="cursor:pointer;">
                    <div class="gallery-thumb" style="width:100%;aspect-ratio:1;background:rgba(255,0,127,0.1);border-radius:6px;border:1px solid var(--border);display:flex;align-items:center;justify-content:center;font-size:1.5rem;">🎬</div>
                    <div style="font-size:0.5rem;font-family:'Share Tech Mono';color:rgba(255,255,255,0.5);margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${f.name}">${f.name}</div>
                </div>`;
            } else if (f.type === 'audio') {
                return `<div class="gallery-item" data-url="${f.url}" data-name="${f.name}" data-type="${f.type}">
                    <div class="gallery-thumb" style="width:100%;aspect-ratio:1;background:rgba(0,243,255,0.05);border-radius:6px;border:1px solid var(--border);display:flex;align-items:center;justify-content:center;font-size:1.5rem;">🎵</div>
                    <div style="font-size:0.5rem;font-family:'Share Tech Mono';color:rgba(255,255,255,0.5);margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${f.name}">${f.name}</div>
                    <audio controls style="width:100%;height:24px;margin-top:2px;" src="${f.url}"></audio>
                </div>`;
            } else {
                return `<div class="gallery-item" data-url="${f.url}" data-name="${f.name}" data-type="${f.type}">
                    <div class="gallery-thumb" style="width:100%;aspect-ratio:1;background:rgba(255,255,255,0.03);border-radius:6px;border:1px solid var(--border);display:flex;align-items:center;justify-content:center;font-size:1.5rem;">📄</div>
                    <div style="font-size:0.5rem;font-family:'Share Tech Mono';color:rgba(255,255,255,0.5);margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${f.name}">${f.name}</div>
                </div>`;
            }
        }).join('');

        // Wire clicks — images open lightbox, videos open in new tab
        grid.querySelectorAll('.gallery-item').forEach(item => {
            item.addEventListener('click', () => {
                const url = (item as HTMLElement).getAttribute('data-url');
                const type = (item as HTMLElement).getAttribute('data-type');
                if (type === 'image' && url && this.lightboxEl) {
                    const img = this.lightboxEl.querySelector('#gallery-lightbox-img') as HTMLImageElement;
                    if (img) img.src = url;
                    this.lightboxEl.style.display = 'flex';
                } else if (url) {
                    window.open(url, '_blank');
                }
            });
        });
    }

    private static async handleUpload() {
        if (!this.uploadInput || !this.uploadInput.files || this.uploadInput.files.length === 0) return;
        const files = this.uploadInput.files;
        let uploaded = 0;
        for (let i = 0; i < files.length; i++) {
            try {
                const formData = new FormData();
                formData.append('file', files[i]);
                const resp = await fetch(`/api/uploads/upload?folder=${encodeURIComponent(this.currentFolder)}`, {
                    method: 'POST',
                    body: formData,
                });
                if (resp.ok) uploaded++;
            } catch (e) {
                console.warn('Upload failed:', e);
            }
        }
        this.uploadInput.value = '';
        if (uploaded > 0 && (window as any).log) {
            (window as any).log(`📎 Uploaded ${uploaded} file${uploaded > 1 ? 's' : ''} to ${this.currentFolder}`, 'var(--neon-blue)');
        }
        this.load();
    }
}