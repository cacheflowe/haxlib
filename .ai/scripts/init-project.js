#!/usr/bin/env node
/**
 * Agents Config Sync — New Project Bootstrapper
 *
 * Copies/merges the .ai/ harness (plus its supporting files) from this repo
 * into a target project directory (typically a sibling folder), following
 * the same steps documented in .ai/README.md's Quickstart section.
 *
 * Usage:
 *   node .ai/scripts/init-project.js <target-dir> [--update] [--force] [--no-sync] [--dry-run]
 *
 * Examples:
 *   node .ai/scripts/init-project.js ../my-new-project
 *   node .ai/scripts/init-project.js ../my-existing-project --update --dry-run
 *
 * Flags:
 *   --update    Target already has an older .ai/ toolkit — refresh only the harness-internal
 *               files (.ai/scripts/, .ai/_base.md, .ai/docs/) and add any new example
 *               skills/prompts that don't exist yet. Never touches .ai/AGENTS.md,
 *               .ai/mcp-servers.json, or existing .ai/skills|prompts files (those are
 *               adopter-owned).
 *   --force     Without --update: overwrite an existing .ai/ directory in the target instead of
 *               skipping it (a wholesale from-scratch reset). With --update: also overwrite
 *               existing example skills/prompts. Also lets the script proceed even if
 *               conflicting generated-target files are found (see below).
 *   --no-sync   Skip running `node .ai/scripts/sync.js` in the target after copying.
 *   --dry-run   Print what would happen without writing anything.
 *
 * IMPORTANT: If the target already has a `.ai/` directory and neither --update nor --force is
 * passed, this script copies/syncs NOTHING — it prints a loud warning telling you to rerun with
 * --update instead, so you never accidentally no-op a sync against a stale toolkit.
 *
 * Before copying anything, this script checks whether the target already has non-generated
 * files at paths the sync engine manages (AGENTS.md, CLAUDE.md, .mcp.json, etc.) — e.g. a
 * human-authored CLAUDE.md that predates the harness. If any are found, it warns and exits
 * (unless --force is passed) so you don't end up with a harness that silently can't compose
 * those files.
 *
 * Zero external dependencies. Works identically on macOS and Windows.
 */

let fs;
let path;
let cp;
let ROOT;
let TARGET;
let TARGET_ARG;
let FORCE;
let NO_SYNC;
let DRY_RUN;
let UPDATE;

async function initRuntime() {
  fs = await import("node:fs");
  path = await import("node:path");
  cp = await import("node:child_process");

  const scriptPath = path.resolve(process.argv[1] || ".");
  const scriptDir = path.dirname(scriptPath);
  ROOT = path.resolve(scriptDir, "../..");

  const args = process.argv.slice(2).filter((a) => !a.startsWith("--"));
  FORCE = process.argv.includes("--force");
  NO_SYNC = process.argv.includes("--no-sync");
  DRY_RUN = process.argv.includes("--dry-run");
  UPDATE = process.argv.includes("--update");

  if (!args[0]) {
    console.error("Usage: node .ai/scripts/init-project.js <target-dir> [--update] [--force] [--no-sync] [--dry-run]");
    process.exit(1);
  }

  TARGET_ARG = args[0];
  TARGET = path.resolve(process.cwd(), args[0]);

  if (path.resolve(TARGET) === path.resolve(ROOT)) {
    console.error("Target directory must not be the agents-config-sync repo itself.");
    process.exit(1);
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Ownership markers mirrored from .ai/scripts/sync.js — keep in sync with that file.
const AI_SYNC_MD_MARKER = "<!-- ai-sync-generated -->";
const AI_SYNC_TOML_MARKER = "# ai-sync-generated";

// Paths sync.js composes/generates or always (re)links. A real, non-generated file already
// sitting at one of these paths would be silently preserved (not overwritten) by sync.js.
const GENERATED_TARGETS = [
  { rel: "AGENTS.md", type: "md" },
  { rel: "CLAUDE.md", type: "md" },
  { rel: ".github/copilot-instructions.md", type: "md" },
  { rel: ".agents/context/AGENTS.md", type: "md" },
  { rel: ".codex/config.toml", type: "toml" },
  { rel: ".agents/mcp_config.json", type: "json-flag" },
  { rel: ".mcp.json", type: "always-symlink" },
  { rel: ".pi/mcp.json", type: "always-symlink" },
];

function log(msg) {
  console.log(msg);
}

function relRoot(p) {
  return path.relative(ROOT, p).split(path.sep).join("/");
}

function relTarget(p) {
  return path.relative(TARGET, p).split(path.sep).join("/");
}

function ensureDir(dir) {
  if (DRY_RUN) return;
  fs.mkdirSync(dir, { recursive: true });
}

// Harness internals — never hand-edited by adopters (see .ai/README.md), safe to refresh wholesale.
const AI_INTERNAL_PATHS = [".ai/scripts", ".ai/_base.md", ".ai/docs"];
// Adopter-owned — never touched by --update, even with --force.
const AI_NEVER_TOUCH_PATHS = [".ai/AGENTS.md", ".ai/mcp-servers.json", ".ai/.sync-manifest.json"];
// Example content — added if missing on update; only overwritten with --force.
const AI_EXAMPLE_DIRS = [".ai/skills", ".ai/prompts"];

/**
 * Refresh an existing, older .ai/ toolkit in place instead of replacing it wholesale.
 * - Harness-internal files (scripts/, _base.md, docs/) are always refreshed.
 * - New example skills/prompts are added; existing ones are left alone unless --force.
 * - AGENTS.md, mcp-servers.json, and the sync manifest are never touched.
 */
function updateAiDirectory() {
  log("  found existing .ai/ — refreshing harness-internal files only (--update)");

  for (const rel of AI_INTERNAL_PATHS) {
    const src = path.join(ROOT, rel);
    const dest = path.join(TARGET, rel);
    if (!fs.existsSync(src)) continue;
    log(`  update ${rel}${fs.statSync(src).isDirectory() ? "/" : ""}`);
    if (!DRY_RUN) {
      fs.rmSync(dest, { recursive: true, force: true });
      fs.cpSync(src, dest, { recursive: true });
    }
  }

  for (const rel of AI_EXAMPLE_DIRS) {
    const srcDir = path.join(ROOT, rel);
    if (!fs.existsSync(srcDir)) continue;
    ensureDir(path.join(TARGET, rel));
    for (const name of fs.readdirSync(srcDir)) {
      const srcFile = path.join(srcDir, name);
      const destFile = path.join(TARGET, rel, name);
      const relFile = `${rel}/${name}`;
      if (fs.existsSync(destFile) && !FORCE) {
        const same = fs.readFileSync(srcFile, "utf8") === fs.readFileSync(destFile, "utf8");
        log(
          same
            ? `  skip   ${relFile} (unchanged)`
            : `  skip   ${relFile} (customized — rerun with --force to overwrite)`,
        );
        continue;
      }
      log(fs.existsSync(destFile) ? `  update ${relFile}` : `  add    ${relFile} (new in this harness version)`);
      if (!DRY_RUN) fs.copyFileSync(srcFile, destFile);
    }
  }

  log(`  skip   ${AI_NEVER_TOUCH_PATHS.join(", ")} (adopter-owned — never touched)`);
}

/**
 * Short banner printed at the very end when .ai/ already existed and nothing was touched,
 * pointing at --update as the next step.
 */
function printExistingAiWarning() {
  const line = "=".repeat(78);
  console.error(`\n${line}`);
  console.error("⚠️   .ai/ ALREADY EXISTS IN THE TARGET — NOTHING WAS COPIED OR SYNCED.");
  console.error(line);
  console.error(`Rerun with --update to refresh the harness: npm run ai-init -- ${TARGET_ARG} --update`);
}

/** Copy a whole directory tree from source into the target, skipping if it already exists (unless --force). */
function copyDirIfAbsent(relPath) {
  const src = path.join(ROOT, relPath);
  const dest = path.join(TARGET, relPath);
  if (!fs.existsSync(src)) {
    log(`  skip   ${relPath}/ (not found in source)`);
    return;
  }
  if (fs.existsSync(dest) && !FORCE) {
    log(`  skip   ${relPath}/ (already exists in target — rerun with --force to overwrite)`);
    return;
  }
  log(`  copy   ${relPath}/`);
  if (!DRY_RUN) {
    fs.rmSync(dest, { recursive: true, force: true });
    fs.cpSync(src, dest, { recursive: true });
  }
}

/** Copy a single file into the target, skipping if it already exists (unless --force). */
function copyFileIfAbsent(relPath) {
  const src = path.join(ROOT, relPath);
  const dest = path.join(TARGET, relPath);
  if (!fs.existsSync(src)) {
    log(`  skip   ${relPath} (not found in source)`);
    return;
  }
  if (fs.existsSync(dest) && !FORCE) {
    log(`  skip   ${relPath} (already exists in target — rerun with --force to overwrite)`);
    return;
  }
  log(`  copy   ${relPath}`);
  if (!DRY_RUN) {
    ensureDir(path.dirname(dest));
    fs.copyFileSync(src, dest);
  }
}

/** Merge the "Cross-AI Tooling" block from the source .gitignore into the target's .gitignore. */
function mergeGitignore() {
  const srcPath = path.join(ROOT, ".gitignore");
  const destPath = path.join(TARGET, ".gitignore");
  if (!fs.existsSync(srcPath)) {
    log("  skip   .gitignore (no source .gitignore found)");
    return;
  }

  const srcContent = fs.readFileSync(srcPath, "utf8");
  const marker = "# Cross-AI Tooling";
  const startIdx = srcContent.indexOf(marker);
  if (startIdx === -1) {
    log("  skip   .gitignore (Cross-AI Tooling block not found in source)");
    return;
  }
  // Block runs from the marker line to the first blank line that follows.
  const afterMarker = srcContent.slice(startIdx);
  const blankLineIdx = afterMarker.indexOf("\n\n");
  const block = (blankLineIdx === -1 ? afterMarker : afterMarker.slice(0, blankLineIdx)).trimEnd();

  const destContent = fs.existsSync(destPath) ? fs.readFileSync(destPath, "utf8") : "";
  if (destContent.includes(marker)) {
    log("  skip   .gitignore (Cross-AI Tooling block already present)");
    return;
  }

  log(fs.existsSync(destPath) ? "  merge  .gitignore (appending Cross-AI Tooling block)" : "  create .gitignore");
  if (!DRY_RUN) {
    const separator = destContent && !destContent.endsWith("\n") ? "\n\n" : destContent ? "\n" : "";
    fs.writeFileSync(destPath, destContent + separator + block + "\n");
  }
}

/**
 * Find pre-existing, non-generated files at paths the sync engine manages.
 * Returns the list of conflicting relative paths (empty if none).
 */
function findGeneratedFileConflicts() {
  const conflicts = [];

  for (const { rel, type } of GENERATED_TARGETS) {
    const dest = path.join(TARGET, rel);
    let stats;
    try {
      stats = fs.lstatSync(dest);
    } catch {
      continue; // doesn't exist — nothing to conflict with
    }
    if (stats.isSymbolicLink()) continue; // already a managed link, sync.js will refresh it

    let owned = false;
    try {
      if (type === "md") {
        owned = fs.readFileSync(dest, "utf8").includes(AI_SYNC_MD_MARKER);
      } else if (type === "toml") {
        owned = fs.readFileSync(dest, "utf8").includes(AI_SYNC_TOML_MARKER);
      } else if (type === "json-flag") {
        owned = JSON.parse(fs.readFileSync(dest, "utf8"))._ai_sync_generated === true;
      } else if (type === "always-symlink") {
        owned = false; // sync.js always wants this to be a symlink — a real file here is foreign
      }
    } catch {
      owned = false;
    }

    if (!owned) conflicts.push(rel);
  }

  return conflicts;
}

/** Merge the ai-sync npm scripts into the target's package.json (creating it if missing). */
function mergePackageJson() {
  const destPath = path.join(TARGET, "package.json");
  const exists = fs.existsSync(destPath);
  const pkg = exists ? JSON.parse(fs.readFileSync(destPath, "utf8")) : { private: true };

  pkg.scripts = pkg.scripts || {};
  let changed = !exists;

  if (!pkg.scripts["ai-sync"]) {
    pkg.scripts["ai-sync"] = "node .ai/scripts/sync.js";
    changed = true;
  }
  if (!pkg.scripts["ai-watch"]) {
    pkg.scripts["ai-watch"] = "node .ai/scripts/sync.js --watch";
    changed = true;
  }
  if (!pkg.scripts.postinstall) {
    pkg.scripts.postinstall = "node .ai/scripts/sync.js";
    changed = true;
  }

  if (!changed) {
    log("  skip   package.json (ai-sync scripts already present)");
    return;
  }

  log(exists ? "  merge  package.json (adding ai-sync scripts)" : "  create package.json");
  if (!DRY_RUN) {
    fs.writeFileSync(destPath, JSON.stringify(pkg, null, 2) + "\n");
  }
}

/** Merge (or create) the ai-sync VS Code task into the target's .vscode/tasks.json. */
function mergeVscodeTasks() {
  const destPath = path.join(TARGET, ".vscode", "tasks.json");
  const exists = fs.existsSync(destPath);
  const tasks = exists ? JSON.parse(fs.readFileSync(destPath, "utf8")) : { version: "2.0.0", tasks: [] };
  tasks.tasks = tasks.tasks || [];

  if (tasks.tasks.some((t) => t.label === "ai-sync")) {
    log("  skip   .vscode/tasks.json (ai-sync task already present)");
    return;
  }

  tasks.tasks.push({
    label: "ai-sync",
    type: "shell",
    command: "node .ai/scripts/sync.js",
    runOptions: { runOn: "folderOpen" },
    presentation: { reveal: "silent" },
  });

  log(exists ? "  merge  .vscode/tasks.json (adding ai-sync task)" : "  create .vscode/tasks.json");
  if (!DRY_RUN) {
    ensureDir(path.dirname(destPath));
    fs.writeFileSync(destPath, JSON.stringify(tasks, null, 2) + "\n");
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  await initRuntime();

  log(`Bootstrapping agents-config-sync into: ${TARGET}${DRY_RUN ? "  (dry run)" : ""}`);

  const conflicts = findGeneratedFileConflicts();
  if (conflicts.length > 0) {
    console.error("\n⚠️  Found existing file(s) at paths the sync engine manages — these look human-authored");
    console.error("   (no ai-sync marker), so `sync.js` would preserve them as-is and NOT compose/link them:");
    conflicts.forEach((rel) => console.error(`     - ${rel}`));
    if (!FORCE) {
      console.error("\nRename or remove these files, or pass --force to proceed anyway.");
      process.exit(1);
    }
    console.error("\nContinuing because --force was passed. The files above will still NOT be overwritten by");
    console.error("sync.js (it never clobbers non-generated files) — resolve them manually if needed.\n");
  }

  ensureDir(TARGET);

  log("\nStep 1: Copy the core toolkit");
  const aiExists = fs.existsSync(path.join(TARGET, ".ai"));
  let skippedExistingAi = false;

  if (UPDATE && aiExists) {
    updateAiDirectory();
  } else if (aiExists && !FORCE) {
    skippedExistingAi = true;
    log("  skip   .ai/ (already exists — see note at the end)");
  } else {
    copyDirIfAbsent(".ai");
  }
  copyDirIfAbsent(".githooks");
  copyFileIfAbsent(".gitattributes");
  copyDirIfAbsent(".vscode");

  log("\nStep 2: Merge shared files");
  mergeGitignore();
  mergePackageJson();
  mergeVscodeTasks();

  if (skippedExistingAi) {
    log("\nStep 3: (skipped — .ai/ already exists)");
  } else if (!DRY_RUN && !NO_SYNC) {
    log("\nStep 3: Run the sync");
    try {
      cp.execSync("node .ai/scripts/sync.js", { cwd: TARGET, stdio: "inherit" });
    } catch (err) {
      console.error("❌ Sync failed to run automatically. Run it manually with:");
      console.error(`  cd ${relTarget(TARGET) || "."} && node .ai/scripts/sync.js`);
    }
  } else if (DRY_RUN) {
    log("\nStep 3: (skipped — dry run) would run `node .ai/scripts/sync.js` in target");
  } else {
    log("\nStep 3: (skipped — --no-sync) run `node .ai/scripts/sync.js` in target when ready");
  }

  if (skippedExistingAi) {
    printExistingAiWarning();
  } else {
    log("\n✅ Done. Remember to run `git config core.hooksPath .githooks` in the target to enable git-hook auto-sync.");
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
