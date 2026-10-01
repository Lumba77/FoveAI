#!/usr/bin/env node

// Animation Organization Helper Script
// This script helps validate and organize the large collection of animation files.

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const animationsDir = __dirname;
const categories = {
  'Idle': ['idle', 'relax', 'stand', 'wait', 'breathe'],
  'Walk': ['walk', 'stroll', 'pace'],
  'Run': ['run', 'sprint', 'dash'],
  'Dance': ['dance', 'boogie', 'groove'],
  'Emotion': ['happy', 'sad', 'angry', 'excited', 'confused', 'surprised', 'bored'],
  'Combat': ['fight', 'punch', 'kick', 'block', 'sword', 'combat'],
  'Gestures': ['gesture', 'wave', 'nod', 'shake', 'point', 'clap'],
  'Special': ['jump', 'sit', 'lay', 'crouch', 'crawl', 'fall', 'roll']
};

function getFilesRecursive(dir) {
  let results = [];
  if (!fs.existsSync(dir)) return results;
  
  const list = fs.readdirSync(dir);
  list.forEach(file => {
    // Avoid recursing into node_modules or system files if any
    if (file === 'node_modules' || file.startsWith('.')) return;
    
    const fullPath = path.join(dir, file);
    const stat = fs.statSync(fullPath);
    if (stat && stat.isDirectory()) {
      results = results.concat(getFilesRecursive(fullPath));
    } else {
      results.push(fullPath);
    }
  });
  return results;
}

function analyzeFiles() {
  console.log(`Analyzing animation files in: ${animationsDir}...`);
  
  const allFiles = getFilesRecursive(animationsDir);
  const files = allFiles.filter(file => {
    const ext = path.extname(file).toLowerCase();
    return ext === '.fbx' || ext === '.bvh' || ext === '.vrma';
  });
  
  console.log(`Found ${files.length} animation files recursively.`);
  
  const categorized = {};
  Object.keys(categories).forEach(cat => categorized[cat] = []);
  categorized['Uncategorized'] = [];
  
  files.forEach(fullPath => {
    const file = path.basename(fullPath);
    const lowerFile = file.toLowerCase();
    let foundCategory = false;
    
    for (const [category, keywords] of Object.entries(categories)) {
      if (keywords.some(keyword => lowerFile.includes(keyword))) {
        categorized[category].push(fullPath);
        foundCategory = true;
        break;
      }
    }
    
    if (!foundCategory) {
      categorized['Uncategorized'].push(fullPath);
    }
  });
  
  // Print summary
  console.log('\n=== Animation File Summary ===');
  Object.entries(categorized).forEach(([category, catFiles]) => {
    if (catFiles.length > 0) {
      console.log(`${category}: ${catFiles.length} files`);
    }
  });
  
  // Print sample files for each category
  console.log('\n=== Sample Files by Category ===');
  Object.entries(categorized).forEach(([category, catFiles]) => {
    if (catFiles.length > 0) {
      console.log(`\n${category}:`);
      catFiles.slice(0, 3).forEach(fullPath => {
        const relPath = path.relative(animationsDir, fullPath).replace(/\\/g, '/');
        console.log(`  - ${relPath}`);
      });
      if (catFiles.length > 3) {
        console.log(`  ... and ${catFiles.length - 3} more`);
      }
    }
  });
  
  return categorized;
}

function generateManifest(categorized) {
  console.log('\n=== Generating Manifest Suggestions ===');
  
  const manifest = {
    "Greetings": [],
    "Idle": [],
    "Happy": [],
    "Sad": [],
    "Surprised": [],
    "Angry": [],
    "Thinking": [],
    "Dance": [],
    "Combat": [],
    "Gestures": []
  };
  
  // Map categorized files to manifest categories
  const publicDir = path.join(animationsDir, '..');
  
  const mapCategory = (sourceCat, targetKey, limit) => {
    if (categorized[sourceCat] && categorized[sourceCat].length > 0) {
      categorized[sourceCat].slice(0, limit).forEach(fullPath => {
        const relToPublic = path.relative(publicDir, fullPath).replace(/\\/g, '/');
        manifest[targetKey].push({
          name: path.parse(fullPath).name,
          url: `/${relToPublic}`
        });
      });
    }
  };

  mapCategory('Gestures', 'Greetings', 3);
  mapCategory('Idle', 'Idle', 5);
  mapCategory('Emotion', 'Happy', 3);
  mapCategory('Dance', 'Dance', 3);
  mapCategory('Combat', 'Combat', 3);
  mapCategory('Gestures', 'Gestures', 3);
  
  // Pretty print the manifest
  console.log(JSON.stringify(manifest, null, 2));
  
  return manifest;
}

function validateManifest(manifestFile) {
  if (!manifestFile) {
    manifestFile = path.join(animationsDir, 'animation_manifest.json');
  }
  console.log(`\n=== Validating Manifest: ${manifestFile} ===`);
  
  if (!fs.existsSync(manifestFile)) {
    console.log('Manifest file not found');
    return;
  }
  
  try {
    const manifest = JSON.parse(fs.readFileSync(manifestFile, 'utf8'));
    console.log('Manifest JSON parsed successfully.');
    
    let totalAnimations = 0;
    let missingCount = 0;
    const publicDir = path.join(animationsDir, '..');
    
    Object.entries(manifest).forEach(([category, animations]) => {
      console.log(`Category: ${category} (${animations.length} animations)`);
      animations.forEach(anim => {
        totalAnimations++;
        // Check if file exists. anim.url is like "/Animations/FBX/Arnold_Idle.fbx"
        // publicDir is public/
        // So path.join(publicDir, anim.url) -> public/Animations/FBX/Arnold_Idle.fbx
        const relativeUrl = decodeURIComponent(anim.url.startsWith('/') ? anim.url.slice(1) : anim.url);
        const diskPath = path.join(publicDir, relativeUrl);
        
        if (!fs.existsSync(diskPath)) {
          console.warn(`  ✗ [MISSING] ${anim.name}: URL "${anim.url}" -> Path "${diskPath}" not found on disk`);
          missingCount++;
        }
      });
    });
    
    console.log(`\nValidation complete. Total checked: ${totalAnimations} animations`);
    if (missingCount > 0) {
      console.warn(`⚠️  Warning: ${missingCount} files in the manifest are missing on disk!`);
    } else {
      console.log(`✓ All ${totalAnimations} files in the manifest exist on disk.`);
    }
    
  } catch (error) {
    console.error('Error validating manifest:', error.message);
  }
}

// Main execution
function main() {
  console.log('Animation Organization Helper');
  console.log('============================');
  
  const categorized = analyzeFiles();
  generateManifest(categorized);
  validateManifest();
  
  console.log('\n=== Recommendations ===');
  console.log('1. Keep all files in subfolders or the flat Animations/ directory');
  console.log('2. Use descriptive filenames that include animation type');
  console.log('3. Update animation_manifest.json to include desired animations');
  console.log('4. Use search-based file finding instead of folder navigation');
  console.log('5. Refer to README_ORGANIZATION.md for detailed guidelines');
}

// Check if run directly
const isDirectRun = process.argv[1] && (
  process.argv[1] === __filename || 
  process.argv[1] === path.basename(__filename) ||
  path.resolve(process.argv[1]) === path.resolve(__filename)
);

if (isDirectRun) {
  main();
}

export { analyzeFiles, generateManifest, validateManifest };