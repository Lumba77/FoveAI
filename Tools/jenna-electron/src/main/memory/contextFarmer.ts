/**
 * contextFarmer.ts — Ported from jenna-vscode (no VS Code dependency)
 * Large Context Chunking & Farming Layer
 */

import { FoveatedClient } from './foveatedClient';

export interface FarmedContext {
  digest: string;
  originalLength: number;
  farmedLength: number;
  ratio: number;
  tasks: { text: string; done: boolean }[];
}

const CHUNK_SIZE = 4000;
const OVERLAP = 200;
const MAX_CONCURRENT = 3;
const SMALL_INPUT_THRESHOLD = 4000;

export async function farmContext(
  input: string,
  client: FoveatedClient,
  workspaceId: string,
  persona: string
): Promise<FarmedContext> {
  const tasks: { text: string; done: boolean }[] = [];
  const originalLength = input.length;

  if (originalLength <= SMALL_INPUT_THRESHOLD) {
    return { digest: input, originalLength, farmedLength: originalLength, ratio: 1, tasks };
  }

  const chunks = chunkText(input, CHUNK_SIZE, OVERLAP);
  const summaries: string[] = [];
  const queue = chunks.map((chunk, i) => ({ chunk, i }));

  for (let start = 0; start < queue.length; start += MAX_CONCURRENT) {
    const batch = queue.slice(start, start + MAX_CONCURRENT);
    const results = await Promise.allSettled(
      batch.map(({ chunk, i }) => compressChunk(chunk, i, chunks.length, client, workspaceId, persona))
    );
    results.forEach((r) => {
      if (r.status === 'fulfilled') {
        summaries.push(r.value.summary);
        if (r.value.tasks) tasks.push(...r.value.tasks);
      }
    });
  }

  const digest = [
    `[Context Farmed from ${chunks.length} chunks — originally ${originalLength} chars]`,
    '',
    ...summaries.map((s, i) => `[Chunk ${i + 1}/${summaries.length}]\n${s}`),
    '',
    '---',
    tasks.length > 0
      ? `\n[Tasks Extracted]\n${tasks.map((t, i) => `${i + 1}. ${t.text}`).join('\n')}`
      : '',
  ].filter(Boolean).join('\n');

  return { digest, originalLength, farmedLength: digest.length, ratio: +(digest.length / originalLength).toFixed(3), tasks };
}

async function compressChunk(
  chunk: string, _index: number, _total: number,
  client: FoveatedClient, workspaceId: string, persona: string
): Promise<{ summary: string; tasks: { text: string; done: boolean }[] }> {
  const prompt = `Compress the following code/context into a concise summary preserving ALL key details: types, names, logic, errors, imports, and relationships. Output ONLY the compressed version — no greeting, no explanation.\n\nContent:\n${chunk}`;
  let summary = '';
  try {
    for await (const tok of client.chat([{ role: 'user', content: prompt }], {
      model: 'auto', workspaceId, stream: true,
      persona: persona as any, maxTokens: 512, temperature: 0.2, compressionLevel: 5,
    })) {
      summary += tok;
    }
  } catch { summary = chunk.slice(0, 1000) + '...'; }

  const tasks: { text: string; done: boolean }[] = [];
  const taskRegex = /[-*]\s+\[([ xX])\]\s+(.+)/g;
  let m;
  while ((m = taskRegex.exec(chunk)) !== null) {
    tasks.push({ text: m[2].trim(), done: m[1].toLowerCase() === 'x' });
  }
  return { summary: summary.trim(), tasks };
}

function chunkText(text: string, size: number, overlap: number): string[] {
  if (text.length <= size) return [text];
  const chunks: string[] = [];
  let start = 0;
  while (start < text.length) {
    chunks.push(text.slice(start, Math.min(start + size, text.length)));
    start += size - overlap;
  }
  return chunks;
}
