const cp = require('child_process');
try {
  const commitOutput = cp.execSync('git --no-pager log -1 --format="%s###%cd" --date=relative', { 
    cwd: process.cwd(), 
    timeout: 2000,
    windowsHide: true,
    env: process.env
  }).toString().trim();
  console.log("OUTPUT:", commitOutput);
} catch (e) {
  console.error("ERROR:", e);
}
