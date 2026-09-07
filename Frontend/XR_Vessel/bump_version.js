import fs from 'fs';
import path from 'path';

// Define the files and their regex patterns to find and replace the version
// NOTE: AvatarManager.ts and Dashboard.ts now derive VERSION from the global
// LINK_REVISION via (window as any).LINK_REVISION?.replace('OMEGA_', '') || "207"
// so they are NOT included here. Only index.html and main.ts need updating.
const filesToUpdate = [
    {
        path: 'index.html',
        regex: /src="\/src\/main\.ts\?v=(\d+)"/,
        replacement: 'src="/src/main.ts?v=$1"'
    },
    {
        path: 'index.html',
        regex: /const expectedVersion = "(\d+)";/,
        replacement: 'const expectedVersion = "$1";'
    },
    {
        path: 'index.html',
        regex: /window\.CACHE_BUSTER_VERSION = "(\d+)";/,
        replacement: 'window.CACHE_BUSTER_VERSION = "$1";'
    },
    {
        path: 'src/main.ts',
        regex: /(?:\(window as any\)\.)?LINK_REVISION\s*=\s*["']OMEGA_(\d+)["'];/,
        replacement: '(window as any).LINK_REVISION = "OMEGA_$1";'
    },
    {
        path: 'src/ContextManager.ts',
        regex: /LINK_REVISION\s*\|\|\s*["']OMEGA_(\d+)["']/,
        replacement: 'LINK_REVISION || "OMEGA_$1"'
    },
    // AvatarManager.ts and Dashboard.ts removed — they derive VERSION from LINK_REVISION
];

function getCurrentVersion() {
    const mainTsPath = path.join(process.cwd(), 'src/main.ts');
    if (fs.existsSync(mainTsPath)) {
        const content = fs.readFileSync(mainTsPath, 'utf8');
        const match = content.match(/(?:\(window as any\)\.)?LINK_REVISION\s*=\s*["']OMEGA_(\d+)["'];/);
        if (match && match[1]) {
            return match[1];
        }
    }
    return '000';
}

function updateFiles(newVersion) {
    let updatedCount = 0;
    
    filesToUpdate.forEach(fileDef => {
        const filePath = path.join(process.cwd(), fileDef.path);
        if (fs.existsSync(filePath)) {
            let content = fs.readFileSync(filePath, 'utf8');
            
            // Create a specific replace string where $1 is replaced by our new version
            const replaceStr = fileDef.replacement.replace('$1', newVersion);
            
            // Check if the pattern matches
            if (fileDef.regex.test(content)) {
                content = content.replace(fileDef.regex, replaceStr);
                fs.writeFileSync(filePath, content, 'utf8');
                console.log(`\x1b[32m[OK]\x1b[0m Updated version to ${newVersion} in ${fileDef.path}`);
                updatedCount++;
            } else {
                console.log(`\x1b[33m[WARN]\x1b[0m Could not find version pattern in ${fileDef.path}`);
            }
        } else {
            console.log(`\x1b[31m[ERROR]\x1b[0m File not found: ${fileDef.path}`);
        }
    });
    
    return updatedCount;
}

// Main execution – version bumping now requires an explicit argument
// This allows manual cache‑busting without accidental auto‑increments on every start.
const currentVersion = getCurrentVersion();
let newVersion = process.argv[2];

if (!newVersion) {
    // No argument – just report the current version (no file changes)
    console.log(`\x1b[33m[INFO]\x1b[0m Current version is OMEGA_${currentVersion}. Provide a version number to bump (e.g., 'npm run bump -- 212').`);
    process.exit(0);
}

// Ensure the supplied version is numeric and padded to three digits
if (/^\d+$/.test(newVersion)) {
    newVersion = String(parseInt(newVersion, 10)).padStart(3, '0');
}

console.log(`Updating version from OMEGA_${currentVersion} to OMEGA_${newVersion}...`);
const count = updateFiles(newVersion);
console.log(`\n\x1b[36mDone!\x1b[0m Updated ${count} files to version ${newVersion}.`);
// Exit without performing any file updates
process.exit(0);