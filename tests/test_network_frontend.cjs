const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const frontend = path.resolve(__dirname, '../Frontend/multigate');
const ts = require(path.join(frontend, 'node_modules/typescript'));
const source = fs.readFileSync(path.join(frontend, 'vite.config.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true },
}).outputText;

function configFor(env = {}) {
  const module = { exports: {} };
  vm.runInNewContext(compiled, {
    module,
    exports: module.exports,
    process: { cwd: () => frontend, env: {} },
    require: (name) => {
      if (name === 'vite') return { defineConfig: (factory) => factory, loadEnv: () => env };
      if (name === '@vitejs/plugin-react') return () => ({ name: 'react-test' });
      return require(name);
    },
  });
  return module.exports.default({ mode: 'test' });
}

function initializer(file, variable) {
  const text = fs.readFileSync(path.join(frontend, 'src', file), 'utf8');
  const tree = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let result;
  function visit(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(tree) === variable) result = node.initializer;
    ts.forEachChild(node, visit);
  }
  visit(tree);
  assert.ok(result, `${variable} exists in ${file}`);
  return result;
}

test('browser endpoints follow localhost, LAN changes and HTTPS origins', () => {
  const proxy = initializer('IgnitionButton.tsx', 'PROXY_URL');
  assert.equal(proxy.right.text, '/api/foveated');
  for (const file of ['IgnitionButton.tsx', 'IgnitionScreen.tsx']) {
    assert.equal(initializer(file, 'IGNITION_URL').text, '/ignition');
  }
  for (const origin of ['http://localhost:5177', 'http://192.0.2.10:5177', 'http://192.0.2.20:5177', 'https://foveai.example']) {
    for (const endpoint of [`${proxy.right.text}/api/status`, '/ignition', '/api/lmstudio/v1/models']) {
      assert.equal(new URL(endpoint, origin).origin, origin);
    }
  }
  assert.ok(fs.readFileSync(path.join(frontend, 'src/App.tsx'), 'utf8').includes("fetch('/api/lmstudio/v1/models')"));
});

test('server-side proxy targets remain loopback and preserve URL paths', () => {
  const proxy = configFor().server.proxy;
  assert.equal(proxy['/api/foveated'].target, 'http://127.0.0.1:8400');
  assert.equal(proxy['/api/foveated'].rewrite('/api/foveated/api/status'), '/api/status');
  assert.equal(proxy['/api/lmstudio'].target, 'http://127.0.0.1:1234');
  assert.equal(proxy['/api/lmstudio'].rewrite('/api/lmstudio/v1/models'), '/v1/models');
});

test('unconfigured ignition fails explicitly rather than contacting the STT port', () => {
  const config = configFor();
  assert.equal(config.server.proxy['/ignition'], undefined);
  let handler;
  config.plugins.find((plugin) => plugin.name === 'ignition-availability').configureServer({
    middlewares: { use: (route, callback) => { assert.equal(route, '/ignition'); handler = callback; } },
  });
  let status;
  let body;
  handler({}, { writeHead: (code) => { status = code; }, end: (text) => { body = text; } });
  assert.equal(status, 503);
  assert.match(JSON.parse(body).error, /not configured/);
  assert.equal(config.plugins[0].name, 'xarel-password-gate');
});

test('explicit upstream overrides remain supported', () => {
  const proxy = configFor({ XRLF_MEMORY_PROXY_URL: 'http://proxy.internal:8400/', LM_STUDIO_URL: 'http://models.internal:1234', FOVEAI_IGNITION_URL: 'http://ignition.internal:9000' }).server.proxy;
  assert.equal(proxy['/api/foveated'].target, 'http://proxy.internal:8400');
  assert.equal(proxy['/api/lmstudio'].target, 'http://models.internal:1234');
  assert.equal(proxy['/ignition'].target, 'http://ignition.internal:9000');
});
