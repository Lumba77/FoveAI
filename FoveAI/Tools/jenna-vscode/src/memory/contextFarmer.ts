/**
 * contextFarmer.ts — Large Context Chunking & Farming Layer
 *
 * When inputs exceed ~4000 chars (1K tokens), this farmer:
 * 1. Chunks the content
 * 2. Compresses each chunk via the proxy (using the persona's own intelligence)
 * 3. Merges summaries into a composite context
 * 4. Returns the farmed context + extracted tasks
 *
 * This prevents 65K token dumps from overwhelming the model
 * while preserving semantic meaning.
 */

import { FoveatedClient } from './foveatedClient';

export interface FarmedContext {
  /** The composite, digestible context string */
  digest: string;
  /** Total original character length */
  originalLength: number;
  /** Characters after farming */
  farmedLength: number;
  /** Compression ratio */
  ratio: number;
  /** Task items extracted during farming */
  tasks: { text: string; done: boolean }[];
}

const CHUNK_SIZE = 4000;        // chars per chunk (~1000 tokens)
const OVERLAP = 200;             // char overlap between chunks to preserve boundaries
const MAX_CONCURRENT = 3;        // max parallel summarization calls
const SMALL_INPUT_THRESHOLD = 4000;

/**
 * Farm a large text input into a compressed, structured context.
 * If input is small (< 4K chars), returns it as-is with no chunking.
 */
export async function farmContext(
  input: string,
  client: FoveatedClient,
  workspaceId: string,
  persona: string
): Promise<FarmedContext> {
  const tasks: { text: string; done: boolean }[] = [];
  const originalLength = input.length;

  // Small inputs pass through unchanged
  if (originalLength <= SMALL_INPUT_THRESHOLD) {
    return {
      digest: input,
      originalLength,
      farmedLength: originalLength,
      ratio: 1,
      tasks,
    };
  }

  // 1. Chunk the input
  const chunks = chunkText(input, CHUNK_SIZE, OVERLAP);
  const summaries: string[] = [];

  // 2. Compress each chunk in parallel (limited concurrency)
  const queue = chunks.map((chunk, i) => ({ chunk, i }));
  
  for (let start = 0; start < queue.length; start += MAX_CONCURRENT) {
    const batch = queue.slice(start, start + MAX_CONCURRENT);
    const results = await Promise.allSettled(
      batch.map(({ chunk, i }) =>
        compressChunk(chunk, i, chunks.length, client, workspaceId, persona)
      )
    );
    results.forEach((r) => {
      if (r.status === 'fulfilled') {
        summaries.push(r.value.summary);
        if (r.value.tasks) tasks.push(...r.value.tasks);
      }
    });
  }

  // 3. Build composite digest
  const digest = [
    `[Context Farmed from ${chunks.length} chunks — originally ${originalLength} chars]`,
    '',
    ...summaries.map((s, i) => `[Chunk ${i + 1}/${summaries.length}]\n${s}`),
    '',
    '---',
    tasks.length > 0
      ? `\n[Tasks Extracted]\n${tasks.map((t, i) => `${i + 1}. ${t.text}`).join('\n')}`
      : '',
  ]
    .filter(Boolean)
    .join('\n');

  const farmedLength = digest.length;

  return {
    digest,
    originalLength,
    farmedLength,
    ratio: +(farmedLength / originalLength).toFixed(3),
    tasks,
  };
}

/**
 * Send a single chunk to the proxy for compression/summarization.
 * The proxy's own model compresses semantically — way better than regex.
 */
async function compressChunk(
  chunk: string,
  _index: number,
  _total: number,
  client: FoveatedClient,
  workspaceId: string,
  persona: string
): Promise<{ summary: string; tasks: { text: string; done: boolean }[] }> {
  const prompt = `Compress the following code/context into a concise summary preserving ALL key details: types, names, logic, errors, imports, and relationships. Output ONLY the compressed version — no greeting, no explanation.

Content:
${chunk}`;

  let summary = '';
  const messages = [{ role: 'user' as const, content: prompt }];

  try {
    const stream = client.chat(messages, {
      model: 'auto',
      workspaceId,
      stream: true,
      persona: persona as any,
      maxTokens: 512,
      temperature: 0.2,
      compressionLevel: 3,  // moderate compression (user can override via settings)
    });

    for await (const tok of stream) {
      summary += tok;
    }
  } catch {
    // If compression fails, just use the truncated original
    summary = chunk.slice(0, 1000) + '...';
  }

  // Extract any task-like lines
  const tasks: { text: string; done: boolean }[] = [];
  const taskRegex = /[-*]\s+\[([ xX])\]\s+(.+)/g;
  let m;
  while ((m = taskRegex.exec(chunk)) !== null) {
    tasks.push({ text: m[2].trim(), done: m[1].toLowerCase() === 'x' });
  }

  return { summary: summary.trim(), tasks };
}

/**
 * Split text into overlapping chunks.
 */
function chunkText(text: string, size: number, overlap: number): string[] {
  if (text.length <= size) return [text];
  const chunks: string[] = [];
  let start = 0;
  while (start < text.length) {
    const end = Math.min(start + size, text.length);
    chunks.push(text.slice(start, end));
    start += size - overlap;
  }
  return chunks;
}

