#!/usr/bin/env node
/**
 * XRS Token Counter — Measure token reduction across files
 * 
 * Usage:
 *   node xrs-tokens.cjs <filepath>              # Single file
 *   node xrs-tokens.cjs <filepath1> <filepath2>  # Multiple files
 *   node xrs-tokens.cjs <directory> --recursive  # All files in directory
 * 
 * Options:
 *   --depth <0-3>    Skeletonization depth (default: 2)
 *   --recursive      Scan directory recursively
 *   --csv            Output as CSV
 *   --json           Output as JSON array
 *   --summary        Show summary only
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const XRS_PATH = path.join(__dirname, 'xrs.cjs');

// Parse CLI args
const args = process.argv.slice(2);
let filePaths = [];
let depth = 2;
let recursive = false;
let outputCsv = false;
let outputJson = false;
let summaryOnly = false;

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--depth' && i + 1 < args.length) {
    depth = parseInt(args[i + 1], 10);
    i++;
  } else if (args[i] === '--recursive') {
    recursive = true;
  } else if (args[i] === '--csv') {
    outputCsv = true;
  } else if (args[i] === '--json') {
    outputJson = true;
  } else if (args[i] === '--summary') {
    summaryOnly = true;
  } else if (!args[i].startsWith('--')) {
    filePaths.push(args[i]);
  }
}

/**
 * Get all files in a directory (optionally recursive)
 */
function getFiles(dir, recurse) {
  let results = [];
  const list = fs.readdirSync(dir);
  
  for (const item of list) {
    const itemPath = path.join(dir, item);
    const stat = fs.statSync(itemPath);
    
    if (stat.isDirectory()) {
      if (recurse) {
        results = results.concat(getFiles(itemPath, recurse));
      }
    } else {
      // Only include source files
      const ext = path.extname(itemPath).toLowerCase();
      const sourceExts = ['.py', '.js', '.jsx', '.cjs', '.mjs', '.ts', '.tsx', '.html', '.htm', '.css', '.scss', '.less', '.json', '.md', '.yaml', '.yml', '.xml', '.svg', '.go', '.java', '.rs', '.cs', '.kt'];
      if (sourceExts.includes(ext)) {
        results.push(itemPath);
      }
    }
  }
  
  return results;
}

/**
 * Get token stats for a single file
 */
function getStats(filePath) {
  try {
    const result = execSync(`node "${XRS_PATH}" "${filePath}" --depth ${depth} --stats`, {
      encoding: 'utf8',
      maxBuffer: 10 * 1024 * 1024
    });
    
    // Extract JSON from the last line (xrs.cjs outputs skeleton text then JSON)
    const lines = result.trim().split('\n');
    const lastLine = lines[lines.length - 1].trim();
    const stats = JSON.parse(lastLine);
    return stats;
  } catch (err) {
    return {
      file: path.basename(filePath),
      language: 'unknown',
      depth,
      originalLines: 0,
      originalTokens: 0,
      skeletonTokens: 0,
      reduction: '0%',
      error: err.message
    };
  }
}

// Collect files
let filesToScan = [];
for (const fp of filePaths) {
  if (fs.statSync(fp).isDirectory()) {
    filesToScan = filesToScan.concat(getFiles(fp, recursive));
  } else {
    filesToScan.push(fp);
  }
}

if (filesToScan.length === 0) {
  console.error('Error: No files found to scan');
  process.exit(1);
}

// Scan all files
const results = [];
for (const fp of filesToScan) {
  const stats = getStats(fp);
  results.push(stats);
  
  if (!summaryOnly && !outputCsv && !outputJson) {
    const reduction = parseInt(stats.reduction);
    const bar = '█'.repeat(Math.floor(reduction / 5)) + '░'.repeat(20 - Math.floor(reduction / 5));
    console.log(`${bar} ${stats.reduction.padStart(4)} | ${stats.originalTokens.toString().padStart(6)} → ${stats.skeletonTokens.toString().padStart(4)} | ${path.basename(fp)}`);
  }
}

// Calculate summary
const totalOriginal = results.reduce((sum, r) => sum + r.originalTokens, 0);
const totalSkeleton = results.reduce((sum, r) => sum + r.skeletonTokens, 0);
const totalReduction = totalOriginal > 0 ? Math.round(((totalOriginal - totalSkeleton) / totalOriginal) * 100) : 0;
const avgReduction = results.length > 0 ? Math.round(results.reduce((sum, r) => sum + parseInt(r.reduction), 0) / results.length) : 0;

// Output
if (outputJson) {
  console.log(JSON.stringify({ files: results, summary: { totalFiles: results.length, totalOriginal, totalSkeleton, totalReduction: `${totalReduction}%`, avgReduction: `${avgReduction}%` } }, null, 2));
} else if (outputCsv) {
  console.log('file,language,depth,originalLines,originalTokens,skeletonTokens,reduction');
  for (const r of results) {
    console.log(`${r.file},${r.language},${r.depth},${r.originalLines},${r.originalTokens},${r.skeletonTokens},${r.reduction}`);
  }
} else {
  console.log('\n══════════════════════════════════════════════');
  console.log('  XRS Token Counter — Summary');
  console.log('══════════════════════════════════════════════');
  console.log(`  Files scanned:     ${results.length}`);
  console.log(`  Total original:    ${totalOriginal.toLocaleString()} tokens`);
  console.log(`  Total skeleton:    ${totalSkeleton.toLocaleString()} tokens`);
  console.log(`  Total reduction:   ${totalReduction}%`);
  console.log(`  Average reduction: ${avgReduction}%`);
  console.log('══════════════════════════════════════════════');
}