const fs = require('fs');
const path = require('path');
const homeDir = require('os').homedir();

// Extension host dirs to try, in priority order. The Devin IDE reads
// ~/.devin/extensions; older installs used Antigravity/Windsurf paths.
const candidateRoots = [
  path.join(homeDir, '.devin', 'extensions'),
  path.join(homeDir, '.antigravity', 'extensions'),
  path.join(homeDir, '.antigravity-ide', 'extensions'),
  path.join(homeDir, '.windsurf', 'extensions'),
  path.join(homeDir, '.vscode', 'extensions'),
];

function semverKey(dirName) {
  const m = dirName.match(/(\d+)\.(\d+)\.(\d+)/);
  return m ? (+m[1]) * 1e6 + (+m[2]) * 1e3 + (+m[3]) : 0;
}

// Find every installed foveai-vibe-coder dir across candidate roots,
// pick the highest version.
const matches = [];
for (const root of candidateRoots) {
  if (!fs.existsSync(root)) continue;
  for (const d of fs.readdirSync(root)) {
    if (/foveai-vibe-coder|jenna-copilot/i.test(d)) {
      matches.push({ root, dir: d, ver: semverKey(d) });
    }
  }
}

if (!matches.length) {
  console.log('[DEPLOY] ⚠️  No installed foveai-vibe-coder extension found in:');
  candidateRoots.forEach(r => console.log(`          ${r}`));
  process.exit(1);
}

matches.sort((a, b) => b.ver - a.ver);
const targetPath = path.join(matches[0].root, matches[0].dir);
console.log(`[DEPLOY] 🎯 Deploying to: ${targetPath}`);
if (matches.length > 1) {
  console.log(`[DEPLOY] (other versions present: ${matches.slice(1).map(m => m.dir).join(', ')})`);
}

function copyDirectorySync(src, dest) {
  if (!fs.existsSync(dest)) fs.mkdirSync(dest, { recursive: true });
  const entries = fs.readdirSync(src, { withFileTypes: true });

  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);

    if (entry.isDirectory()) {
      copyDirectorySync(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

console.log(`\n🚀 [DEPLOY] Pushing Jenna changes to Devin IDE extensions...`);
try {
  // Copy 'src' folder (HTML webviews)
  const srcDir = path.join(__dirname, '..', 'src');
  if (fs.existsSync(srcDir)) {
    copyDirectorySync(srcDir, path.join(targetPath, 'src'));
    console.log(`   ✅ Copied 'src' folder`);
  }

  // Copy 'dist' folder (compiled TypeScript)
  const distDir = path.join(__dirname, '..', 'dist');
  if (fs.existsSync(distDir)) {
    copyDirectorySync(distDir, path.join(targetPath, 'dist'));
    console.log(`   ✅ Copied 'dist' folder`);
  }

  console.log(`\n🎉 [DEPLOY] Success! Run "Developer: Reload Window" (or jenna.reloadWindow) to load the new build.\n`);
} catch (error) {
  console.error(`\n❌ [DEPLOY] Error copying files:`, error.message);
  process.exit(1);
}
