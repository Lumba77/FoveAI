'use strict';
/**
 * _xrlf_health_check.cjs — Check XRLF server health + reactor state.
 * Writes a report file (terminal mangles one-liner output).
 * Usage: node _xrlf_health_check.cjs
 */
const fs = require('fs');
const REPORT = 'c:/Users/danie/program/LUMAX/_xrlf_health_report.txt';
const out = [];

function checkHealth() {
  return new Promise((resolve) => {
    try {
      const req = require('http').get('http://127.0.0.1:8400/health', { timeout: 4000 }, (res) => {
        let body = '';
        res.on('data', (c) => (body += c));
        res.on('end', () => {
          out.push('HEALTH ' + res.statusCode + ' ' + body.slice(0, 500));
          resolve();
        });
      });
      req.on('error', (e) => { out.push('HEALTH_ERROR ' + e.message); resolve(); });
    } catch (e) { out.push('HEALTH_EXC ' + e.message); resolve(); }
  });
}

function checkModels() {
  return new Promise((resolve) => {
    try {
      const req = require('http').get('http://127.0.0.1:8400/v1/models', { timeout: 4000 }, (res) => {
        let body = '';
        res.on('data', (c) => (body += c));
        res.on('end', () => {
          out.push('MODELS ' + res.statusCode + ' ' + body.slice(0, 500));
          resolve();
        });
      });
      req.on('error', (e) => { out.push('MODELS_ERROR ' + e.message); resolve(); });
    } catch (e) { out.push('MODELS_EXC ' + e.message); resolve(); }
  });
}

(async () => {
  out.push('CHECK ' + new Date().toISOString());
  await checkHealth();
  await checkModels();
  fs.writeFileSync(REPORT, out.join('\n'), 'utf8');
  console.log('done');
})();

