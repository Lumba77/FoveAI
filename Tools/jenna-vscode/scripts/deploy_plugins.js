const fs = require('fs');
const path = require('path');

// Determine Antigravity extensions path
const homeDir = require('os').homedir();
const antiGravityExtDir = path.join(homeDir, '.antigravity-ide', 'extensions');

// Check possible folder names
const possibleFolders = ['foveai.foveai-vibe-coder-0.3.2', 'lumax.jenna-copilot-0.2.0', 'lumax.jenna-copilot-0.2.1-universal'];
let targetPath = '';
for (const folder of possibleFolders) {
  const p = path.join(antiGravityExtDir, folder);
  if (fs.existsSync(p)) {
    targetPath = p;
    break;
  }
}

// Fallback search
if (!targetPath && fs.existsSync(antiGravityExtDir)) {
  const dirs = fs.readdirSync(antiGravityExtDir);
  const match = dirs.find(d => d.includes('foveai-vibe-coder') || d.includes('jenna-copilot'));
  if (match) targetPath = path.join(antiGravityExtDir, match);
}

if (!targetPath || !fs.existsSync(targetPath)) {
  console.log(`[DEPLOY] ⚠️ Target extension directory not found in ${antiGravityExtDir}`);
  process.exit(1);
}
console.log(`[DEPLOY] 🎯 Deploying to: ${targetPath}`);

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

console.log(`\n🚀 [DEPLOY] Pushing Jenna changes to Antigravity IDE...`);
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

  console.log(`\n🎉 [DEPLOY] Success! Reload your Antigravity IDE plugins area to see the changes.\n`);
} catch (error) {
  console.error(`\n❌ [DEPLOY] Error copying files:`, error.message);
  process.exit(1);
}
