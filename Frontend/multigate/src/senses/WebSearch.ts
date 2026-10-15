/**
        * WEB SEARCH - Avatar's own internet browser/search capability.
            * Simulates a virtual laptop so the avatar can search, browse pages,
 * double - check facts, find missing info, and help the user research.
 *
 * Backends: DuckDuckGo Instant Answer API(free), Brave Search(keyed),
 * Playwright / headless browser for full page reading.
 */
export interface SearchResult { title: string; url: string; snippet: string; }
export interface PageSnapshot { url: string; title: string; textContent: string; screenshots: string[]; }

const DDG = 'https://api.duckduckgo.com';
const BRAVE = 'https://api.search.brave.com/res/v1/web/search';

export class WebSearch {
    private braveKey: string | null = null;
    private log: (m: string, c: string) => void;

    constructor(braveApiKey?: string, logFn?: (m: string, c: string) => void) {
        this.braveKey = braveApiKey || null;
        this.log = logFn || ((m, _c) => console.log('[WebSearch] ' + m));
    }

    /** DuckDuckGo search (free, no key needed). */
    async searchDDG(query: string): Promise<SearchResult[]> {
        try {
            const r = await fetch(`${DDG}/?q=${encodeURIComponent(query)}&format=json&no_html=1&skip_disambig=1`);
            if (!r.ok) return [];
            const data = await r.json();
            const results: SearchResult[] = [];
            for (const item of data.RelatedTopics || []) {
                if (item.Text && item.FirstURL) {
                    results.push({ title: item.Text.split(' - ')[0] || item.Text, url: item.FirstURL, snippet: item.Text });
                }
            }
            if (data.AbstractText) {
                results.unshift({ title: data.Heading || 'Abstract', url: data.AbstractURL || '', snippet: data.AbstractText });
            }
            this.log(`Found ${results.length} results for "${query}"`, '#0af');
            return results.slice(0, 10);
        } catch (e: any) { return []; }
    }

    /** Brave Search (higher quality, needs API key). */
    async searchBrave(query: string): Promise<SearchResult[]> {
        if (!this.braveKey) return this.searchDDG(query);
        try {
            const r = await fetch(`${BRAVE}?q=${encodeURIComponent(query)}&count=10`, {
                headers: { 'Accept': 'application/json', 'X-Subscription-Token': this.braveKey },
            });
            if (!r.ok) return this.searchDDG(query);
            const data = await r.json();
            return ((data.web?.results || []) as any[]).map(item => ({
                title: item.title || '', url: item.url || '', snippet: item.description || '',
            }));
        } catch { return this.searchDDG(query); }
    }

    /** Fetch a web page and extract readable text (via backend scraper). */
    async readPage(url: string): Promise<PageSnapshot | null> {
        try {
            const r = await fetch(`/api/web/scrape?url=${encodeURIComponent(url)}`);
            if (!r.ok) return null;
            const data = await r.json();
            return { url: data.url || url, title: data.title || '', textContent: data.text || '', screenshots: data.screenshots || [] };
        } catch { return null; }
    }

    /** Get the web search context for LLM prompt. */
    getContext(): string {
        return '[WEB SEARCH] DuckDuckGo + Brave available. Can search internet, read pages, double-check facts.';
    }
}
