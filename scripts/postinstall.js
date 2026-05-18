#!/usr/bin/env node
// SoMatic npm postinstall.
//
// 1. Locate a Python 3.10+ interpreter on PATH.
// 2. Create a package-local virtualenv at <packageRoot>/.venv.
// 3. pip install <packageRoot>[vision] into the venv (unless opted out).
// 4. Print a single concise next-step hint.
//
// Opt-outs:
//   SOMATIC_SKIP_POSTINSTALL=1       skip the whole script.
//   SOMATIC_SKIP_PYTHON_BOOTSTRAP=1  skip venv + pip install, keep the shim.
//   SOMATIC_SKIP_VISION=1            install without the [vision] extra
//                                    (no onnxruntime/numpy/huggingface_hub).
"use strict";

const { spawnSync } = require("node:child_process");
const path = require("node:path");

const packageRoot = path.resolve(__dirname, "..");
const venvDir = path.join(packageRoot, ".venv");
const venvPython = process.platform === "win32"
  ? path.join(venvDir, "Scripts", "python.exe")
  : path.join(venvDir, "bin", "python");

function log(msg) {
  console.log(`[somatic] ${msg}`);
}

if (process.env.SOMATIC_SKIP_POSTINSTALL === "1") {
  log("Skipping postinstall (SOMATIC_SKIP_POSTINSTALL=1).");
  process.exit(0);
}

const pythonCandidates = process.platform === "win32"
  ? ["py", "python", "python3"]
  : ["python3", "python"];

let bootPython = null;
for (const candidate of pythonCandidates) {
  const probe = spawnSync(candidate, ["--version"], { stdio: "ignore", shell: false });
  if (!probe.error && probe.status === 0) {
    bootPython = candidate;
    break;
  }
}

if (!bootPython) {
  log("Python 3.10+ was not found on PATH. Install Python, then run `somatic bootstrap`.");
  process.exit(0);
}

if (process.env.SOMATIC_SKIP_PYTHON_BOOTSTRAP === "1") {
  log("Skipping virtualenv bootstrap (SOMATIC_SKIP_PYTHON_BOOTSTRAP=1).");
  process.exit(0);
}

log("Creating package-local virtualenv at .venv ...");
const venv = spawnSync(bootPython, ["-m", "venv", venvDir], { stdio: "inherit", shell: false });
if (venv.status !== 0) {
  log("Could not create the virtualenv. Run `somatic bootstrap` for diagnostics.");
  process.exit(0);
}

spawnSync(venvPython, ["-m", "pip", "install", "--upgrade", "pip"], {
  stdio: "inherit",
  shell: false,
});

const installTarget = process.env.SOMATIC_SKIP_VISION === "1"
  ? packageRoot
  : `${packageRoot}[vision]`;

const extraNote = installTarget.endsWith("[vision]") ? " + [vision] extra" : "";
log(`Installing SoMatic core${extraNote} into .venv ...`);
const install = spawnSync(venvPython, ["-m", "pip", "install", installTarget], {
  stdio: "inherit",
  shell: false,
});

if (install.status !== 0) {
  log("Python dependency install failed. Run `somatic bootstrap` for diagnostics.");
  process.exit(0);
}

log("Install complete.");
log("Next steps:");
log("  somatic doctor          # verify the install");
log("  somatic vision init     # fetch the YOLO ONNX weights (AGPL-3.0; see `somatic license`)");
