/**
 * CodeAgency — Frontend client for /api/code/* endpoints
 * 
 * Provides searchCode, readFile, exec, writeFile, gitStatus, listDir
 * methods that call the backend code_agency_routes.py API.
 * 
 * Used by main.ts to execute <code:...> and <self:search "query">
 * bracket tokens emitted by the LLM.
 */

export type LogFn = (msg: string, color?: string) => void;

export interface SearchResult {
    file: string;
    line: number;
    content: string;
    match: string;
}

export interface ExecResult {
    success: boolean;
    message: string;
    exitCode?: number;
}

export interface WriteResult {
    success: boolean;
    message: string;
    validationErrors?: string[];
}

export interface GitStatusResult {
    status: string;
    exitCode: number;
}

export interface ListDirEntry {
    path: string;
    size: number;
    isDir: boolean;
    modified: string;
}

export class CodeAgency {
    private log: LogFn;
    private baseUrl: string;

    constructor(logFn: LogFn, baseUrl?: string) {
        this.log = logFn;
        this.baseUrl = baseUrl || '';
    }

    /** Search codebase for a query string */
    async searchCode(query: string, glob?: string): Promise<SearchResult[]> {
        const params = new URLSearchParams({ q: query });
        if (glob) params.set('glob', glob);
        const url = `${this.baseUrl}/api/code/search?${params.toString()}`;
        this.log(`searchCode: ${url}`, '#00f3ff');
        const res = await fetch(url);
        if (!res.ok) throw new Error(`searchCode failed: ${res.status} ${res.statusText}`);
        const data = await res.json();
        return data.results || [];
    }

    /** Read a file from the codebase */
    async readFile(path: string, maxLines?: number): Promise<string | null> {
        const params = new URLSearchParams({ path });
        if (maxLines) params.set('maxLines', String(maxLines));
        const url = `${this.baseUrl}/api/code/read?${params.toString()}`;
        this.log(`readFile: ${url}`, '#00f3ff');
        const res = await fetch(url);
        if (!res.ok) {
            if (res.status === 404) return null;
            throw new Error(`readFile failed: ${res.status} ${res.statusText}`);
        }
        const data = await res.json();
        return data.content || null;
    }

    /** Execute a safe shell command */
    async exec(command: string): Promise<ExecResult> {
        const url = `${this.baseUrl}/api/code/exec`;
        this.log(`exec: ${command}`, '#00f3ff');
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command }),
        });
        if (!res.ok) throw new Error(`exec failed: ${res.status} ${res.statusText}`);
        return await res.json();
    }

    /** Write content to a file */
    async writeFile(path: string, content: string): Promise<WriteResult> {
        const url = `${this.baseUrl}/api/code/write`;
        this.log(`writeFile: ${path}`, '#00f3ff');
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path, content }),
        });
        if (!res.ok) throw new Error(`writeFile failed: ${res.status} ${res.statusText}`);
        return await res.json();
    }

    /** Get git status */
    async gitStatus(): Promise<GitStatusResult> {
        const url = `${this.baseUrl}/api/code/git/status`;
        this.log(`gitStatus`, '#00f3ff');
        const res = await fetch(url);
        if (!res.ok) throw new Error(`gitStatus failed: ${res.status} ${res.statusText}`);
        return await res.json();
    }

    /** List directory contents */
    async listDir(dir: string): Promise<ListDirEntry[]> {
        const params = new URLSearchParams({ dir });
        const url = `${this.baseUrl}/api/code/ls?${params.toString()}`;
        this.log(`listDir: ${url}`, '#00f3ff');
        const res = await fetch(url);
        if (!res.ok) throw new Error(`listDir failed: ${res.status} ${res.statusText}`);
        const data = await res.json();
        return data.files || [];
    }
}