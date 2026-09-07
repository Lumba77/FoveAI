const esbuild = require('esbuild');

const isWatch = process.argv.includes('--watch');
const isProd = process.env.NODE_ENV === 'production';

/** @type {import('esbuild').BuildOptions} */
const options = {
  entryPoints: ['src/extension.ts'],
  bundle: true,
  platform: 'node',
  target: 'node18',
  format: 'cjs',
  outfile: 'dist/extension.js',
  external: ['vscode'],           // VS Code API is provided by the host
  sourcemap: !isProd,
  minify: isProd,
  logLevel: 'info',
};

if (isWatch) {
  esbuild.context(options).then(ctx => {
    ctx.watch();
    console.log('[jenna] watching for changes...');
  });
} else {
  esbuild.build(options).then(() => {
    console.log('[jenna] build complete →', options.outfile);
  }).catch(() => process.exit(1));
}
