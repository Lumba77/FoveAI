/**
 * One-time migration: compress all existing messages in the memory DB
 * using the LLM-powered prepareForStorageAsync() pipeline.
 *
 * Usage: node migrate_compress.js [workspaceId] [--dry-run]
 *   workspaceId defaults to 'lumax'
 *   --dry-run: report what would change without writing
 */

'use strict';

const path = require('path');
const fs = require('fs');

// Load .env
(function loadEnv() {
    const envPath = path.resolve(__dirname, '..', '..', '.env');
    try {
        const raw = fs.readFileSync(envPath, 'utf8');
        for (const line of raw.split('\n')) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith('#')) continue;
            const eqIdx = trimmed.indexOf('=');
            if (eqIdx === -1) continue;
            const key = trimmed.slice(0, eqIdx).trim();
            const val = trimmed.slice(eqIdx + 1).trim().replace(/^["']|["']$/g, '');
            if (!(key in process.env)) process.env[key] = val;
        }
    } catch (e) {}
})();

const Datastore = require('nedb-promises');
const { prepareForStorageAsync, prepareForStorage } = require('./core/xrl-compressor');

const args = process.argv.slice(2);
const workspaceId = args.find(a => !a.startsWith('--')) || 'lumax';
const dryRun = args.includes('--dry-run');

const DB_DIR = path.join(__dirname, 'memory_data', workspaceId);
const DB_PATH = path.join(DB_DIR, 'memory.db');

if (!fs.existsSync(DB_PATH)) {
    console.error(`❌ Database not found: ${DB_PATH}`);
    process.exit(1);
}

async function main() {
    console.log(`🔍 Opening database: ${DB_PATH}`);
    console.log(`Mode: ${dryRun ? 'DRY RUN (no writes)' : 'LIVE (will modify DB)'}`);
    console.log('');

    const db = Datastore.create({ filename: DB_PATH, autoload: true });
    const all = await db.find({}).sort({ timestamp: 1 });

    console.log(`📊 Total messages: ${all.length}`);

    // Find messages that need compression (> 2000 chars)
    const needsCompression = [];
    const alreadySmall = [];

    for (const msg of all) {
        const content = msg.content;
        const text = typeof content === 'string' ? content : JSON.stringify(content || '');
        if (text.length > 2000) {
            needsCompression.push({ msg, textLen: text.length });
        } else {
            alreadySmall.push(msg);
        }
    }

    console.log(`   Already small (<2K chars): ${alreadySmall.length}`);
    console.log(`   Need compression (>2K chars): ${needsCompression.length}`);

    if (needsCompression.length === 0) {
        console.log('\n✅ No messages need compression. Database is clean!');
        process.exit(0);
    }

    // Show top 5 largest
    needsCompression.sort((a, b) => b.textLen - a.textLen);
    console.log('\n📏 Top 5 largest messages:');
    for (let i = 0; i < Math.min(5, needsCompression.length); i++) {
        const { msg, textLen } = needsCompression[i];
        const preview = (typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content || '')).slice(0, 80).replace(/\n/g, ' ');
        console.log(`   ${i + 1}. ${textLen.toLocaleString()} chars | ${msg.role} | ${msg.timestamp?.slice(0, 10) || '?'} | "${preview}..."`);
    }

    if (dryRun) {
        console.log('\n🔍 DRY RUN — no changes made. Remove --dry-run to apply.');
        process.exit(0);
    }

    // ── Compress each message ──────────────────────────────────────────
    console.log('\n🔄 Compressing messages...');
    let totalOriginal = 0;
    let totalCompressed = 0;
    let successCount = 0;
    let failCount = 0;

    for (let i = 0; i < needsCompression.length; i++) {
        const { msg, textLen } = needsCompression[i];
        const text = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content || '');

        process.stdout.write(`   [${i + 1}/${needsCompression.length}] ${textLen.toLocaleString()} chars → `);

        try {
            const compressed = await prepareForStorageAsync(text, 10000);
            totalOriginal += textLen;
            totalCompressed += compressed.length;

            const reduction = ((1 - compressed.length / textLen) * 100).toFixed(0);
            console.log(`${compressed.length.toLocaleString()} chars (${reduction}% reduction)`);

            // Update the database
            await db.update(
                { _id: msg._id },
                { $set: { content: compressed, _compressed: true, _original_len: textLen } }
            );
            successCount++;
        } catch (err) {
            console.log(`FAILED: ${err.message}`);
            failCount++;
        }
    }

    // ── Summary ────────────────────────────────────────────────────────
    const overallReduction = totalOriginal > 0
        ? ((1 - totalCompressed / totalOriginal) * 100).toFixed(1)
        : '0';

    console.log('\n═══════════════════════════════════════');
    console.log('📊 MIGRATION COMPLETE');
    console.log('═══════════════════════════════════════');
    console.log(`   Messages compressed: ${successCount}`);
    console.log(`   Failed: ${failCount}`);
    console.log(`   Total original:  ${totalOriginal.toLocaleString()} chars`);
    console.log(`   Total compressed: ${totalCompressed.toLocaleString()} chars`);
    console.log(`   Overall reduction: ${overallReduction}%`);
    console.log(`   Estimated tokens saved: ~${Math.round((totalOriginal - totalCompressed) / 4).toLocaleString()}`);

    // Compact the database
    console.log('\n💾 Compacting database...');
    await db.persistence.compactDatafile();
    console.log('✅ Done!');
}

main().catch(err => {
    console.error('❌ Migration failed:', err);
    process.exit(1);
});
