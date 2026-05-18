#!/usr/bin/env node

const { spawnSync } = require("node:child_process");
const path = require("node:path");

const packageRoot = path.resolve(__dirname, "..");
const srcPath = path.join(packageRoot, "src");
const venvPython = process.platform === "win32"
  ? path.join(packageRoot, ".venv", "Scripts", "python.exe")
  : path.join(packageRoot, ".venv", "bin", "python");
const existingPythonPath = process.env.PYTHONPATH || "";
const env = {
  ...process.env,
  PYTHONPATH: existingPythonPath ? `${srcPath}${path.delimiter}${existingPythonPath}` : srcPath
};

const candidates = [
  venvPython,
  ...(process.platform === "win32"
  ? ["py", "python", "python3"]
  : ["python3", "python"])
];

const args = ["-m", "somatic.cli", ...process.argv.slice(2)];

for (const python of candidates) {
  const result = spawnSync(python, args, { stdio: "inherit", shell: false, env });
  if (result.error && result.error.code === "ENOENT") {
    continue;
  }
  if (result.error) {
    console.error(JSON.stringify({
      ok: false,
      error: {
        code: "python_launch_failed",
        message: result.error.message
      }
    }));
    process.exit(1);
  }
  process.exit(result.status === null ? 1 : result.status);
}

console.error(JSON.stringify({
  ok: false,
  error: {
    code: "python_not_found",
    message: "SoMatic requires Python 3.10+ on PATH. Install Python, then run this command again."
  }
}));
process.exit(1);
