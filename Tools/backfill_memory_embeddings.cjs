'use strict';

/**
 * Tools/backfill_memory_embeddings.js
 * Backfills MiniLM dense vector embeddings (384-dim) for all existing messages in memory_data.
 */

const fs = require('fs');
const path = require('path');
const Datastore = require('../foveated-memory/node_modules/nedb-promises');
const embedder = require('../foveated-memory/core/embedder');

const BASE_DIR = path.resolve(__dirname, '..', 'memory_data');

async function main() {
    console.log('🔍 Scanning memory_data for unembedded messages...');
    const dirs = fs.readdirSync(BASE_DIR);
    let totalUpdated = 0;

    for (const d of dirs) {
        const dbPath = path.join(BASE_DIR, d, 'memory.db');
        if (!fs.existsSync(dbPath)) continue;

        const db = Datastore.create({ filename: dbPath, autoload: true });
        const docs = await db.find({ embedding: { $exists: false } });
        if (!docs || docs.length === 0) continue;

        console.log(`📦 Workspace [${d}]: embedding ${docs.length} messages...`);
        const texts = docs.map(doc => {
            if (typeof doc.content === 'string') return doc.content;
            if (Array.isArray(doc.content)) {
                return doc.content
                    .filter(p => p && typeof p === 'object' && typeof p.text === 'string')
                    .map(p => p.text).join('\n');
            }
            return String(doc.content || '');
        });

        // Batch encode in chunks of 32
        for (let i = 0; i < docs.length; i += 32) {
            const chunkDocs = docs.slice(i, i + 32);
            const chunkTexts = texts.slice(i, i + 32);
            const vectors = await embedder.encode(chunkTexts);

            if (vectors && vectors.length === chunkDocs.length) {
                for (let j = 0; j < chunkDocs.length; j++) {
                    const vec = Array.from(vectors[j]);
                    await db.update(
                        { _id: chunkDocs[j]._id },
                        { $set: { embedding: vec } }
                    );
                    totalUpdated++;
                }
            } else {
                console.warn(`⚠️ Batch encoding failed for chunk in ${d}`);
            }
        }
    }

    console.log(`✅ Successfully backfilled embeddings for ${totalUpdated} messages!`);
    embedder.shutdown();
    process.exit(0);
}

main().catch(err => {
    console.error('Fatal error during embedding backfill:', err);
    embedder.shutdown();
    process.exit(1);
});
