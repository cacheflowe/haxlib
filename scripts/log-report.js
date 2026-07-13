#!/usr/bin/env node
/*
 * log-report.js — zero-dependency log usage reporter
 * ---------------------------------------------------
 * Scans one log file or a whole directory of logs, counts how often each
 * search term appears, groups the counts (by day / by file / not at all),
 * and prints an ASCII-bar report. Can also write a standalone HTML report
 * (inline SVG charts, no external assets) that's easy to hand to a client.
 *
 * Pure Node core modules only — no npm install, runs the same on Windows,
 * macOS and Linux. Designed to be copied between projects: point it at a
 * different log folder and give it a different set of search terms (either
 * on the command line or via a JSON config file).
 *
 * QUICK START (cd into the touchdesigner/ directory first)
 *   node scripts/log-report.js --config scripts/log-report.config.json
 *   node scripts/log-report.js --logs logs --find "app_state=chill" --find "app_state=attract"
 *   node scripts/log-report.js --config scripts/log-report.config.json --html report.html
 *
 * OPTIONS
 *   --logs <path>     Log file OR directory to scan. Directories are scanned
 *                     non-recursively for *.txt / *.log files. Default: cwd.
 *   --find <term>     A search term. Repeatable. Plain substring by default.
 *   --label <text>    Optional label for the *preceding* --find (else the term
 *                     itself is used as the label).
 *   --regex           Treat every --find term as a JS regular expression.
 *   --state <regex>   Enable state timeline analysis. The regex needs one
 *                     capture group holding the state value, e.g.
 *                     "app_state=(\\w+)". Reports entry count AND total time
 *                     spent in each state (time = gap until the next entry,
 *                     computed within each file so overnight gaps don't count).
 *   --group <mode>    day | file | none. Default: day.
 *   --since <date>    Only include lines on/after this day (YYYY-MM-DD).
 *   --until <date>    Only include lines on/before this day (YYYY-MM-DD).
 *   --config <path>   JSON config (see log-report.config.json). A relative
 *                     "logs" path in the config is resolved relative to the
 *                     config file. CLI flags win.
 *   --html <path>     Also write a standalone HTML report to <path>.
 *   --csv <path>      Also write a CSV (term,group,count) to <path>.
 *   --ext <list>      Comma-separated file extensions to scan. Default: txt,log
 *   -h, --help        Show this help.
 */

import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);

// ---------------------------------------------------------------------------
// Argument parsing
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const opts = {
    logs: null,
    terms: [], // { label, match, regex }
    regex: false,
    state: null,
    group: null,
    since: null,
    until: null,
    config: null,
    html: null,
    csv: null,
    ext: null,
    help: false,
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    switch (a) {
      case "--logs":
        opts.logs = next();
        break;
      case "--find":
        opts.terms.push({ match: next(), label: null });
        break;
      case "--label": {
        const last = opts.terms[opts.terms.length - 1];
        if (last) last.label = next();
        else console.warn("Warning: --label with no preceding --find, ignored.");
        break;
      }
      case "--regex":
        opts.regex = true;
        break;
      case "--state":
        opts.state = next();
        break;
      case "--since":
        opts.since = next();
        break;
      case "--until":
        opts.until = next();
        break;
      case "--group":
        opts.group = next();
        break;
      case "--config":
        opts.config = next();
        break;
      case "--html":
        opts.html = next();
        break;
      case "--csv":
        opts.csv = next();
        break;
      case "--ext":
        opts.ext = next();
        break;
      case "-h":
      case "--help":
        opts.help = true;
        break;
      default:
        console.warn(`Warning: unknown argument "${a}" ignored.`);
    }
  }
  return opts;
}

// ---------------------------------------------------------------------------
// Config resolution: JSON config provides defaults, CLI flags override.
// ---------------------------------------------------------------------------

function loadConfig(configPath) {
  const raw = fs.readFileSync(configPath, "utf8");
  let cfg;
  try {
    cfg = JSON.parse(raw);
  } catch (err) {
    throw new Error(`Could not parse config "${configPath}": ${err.message}`);
  }
  return cfg;
}

function resolveSettings(opts) {
  const cfg = opts.config ? loadConfig(opts.config) : {};

  // Terms: CLI --find entries take precedence; otherwise use config.terms.
  let terms;
  if (opts.terms.length) {
    terms = opts.terms.map((t) => ({
      label: t.label || t.match,
      match: t.match,
      regex: opts.regex,
    }));
  } else if (Array.isArray(cfg.terms)) {
    terms = cfg.terms.map((t) => ({
      label: t.label || t.match,
      match: t.match,
      regex: t.regex != null ? !!t.regex : !!cfg.regex,
    }));
  } else {
    terms = [];
  }

  const extList = (opts.ext || cfg.ext || "txt,log")
    .split(",")
    .map((s) => s.trim().replace(/^\./, "").toLowerCase())
    .filter(Boolean);

  // State timeline config: CLI --state (regex only) overrides config.state.
  let state = null;
  if (opts.state) {
    state = { match: opts.state, labels: {}, maxGapSeconds: null };
  } else if (cfg.state && cfg.state.match) {
    state = {
      match: cfg.state.match,
      labels: cfg.state.labels || {},
      maxGapSeconds: cfg.state.maxGapSeconds != null ? cfg.state.maxGapSeconds : null,
    };
  }

  // Resolve the log path. A CLI --logs is relative to the current directory;
  // a config "logs" is relative to the config file itself, so a report runs
  // the same no matter which directory you launch it from.
  let logs;
  if (opts.logs) {
    logs = opts.logs;
  } else if (cfg.logs) {
    logs = path.isAbsolute(cfg.logs) ? cfg.logs : path.resolve(path.dirname(opts.config), cfg.logs);
  } else {
    logs = process.cwd();
  }

  return {
    title: cfg.title || "Log Usage Report",
    logs,
    group: opts.group || cfg.group || "day",
    since: opts.since || cfg.since || null,
    until: opts.until || cfg.until || null,
    terms,
    state,
    ext: extList,
    html: opts.html || null,
    csv: opts.csv || null,
  };
}

// ---------------------------------------------------------------------------
// Log discovery
// ---------------------------------------------------------------------------

function discoverFiles(logsPath, extList) {
  const stat = fs.statSync(logsPath); // throws with a clear ENOENT if missing
  if (stat.isFile()) return [logsPath];

  return fs
    .readdirSync(logsPath)
    .filter((name) => extList.includes(path.extname(name).slice(1).toLowerCase()))
    .map((name) => path.join(logsPath, name))
    .sort();
}

// Pull a YYYY-MM-DD day key out of a line (leading ISO date), falling back to
// the same token anywhere in the line, else null.
const DAY_RE = /(\d{4}-\d{2}-\d{2})/;
function dayOf(line) {
  const m = line.match(DAY_RE);
  return m ? m[1] : null;
}

// Parse a leading "YYYY-MM-DD HH:MM:SS[.ffffff]" timestamp to epoch ms.
// We only ever take differences, so the (fixed, UTC) zone is irrelevant.
const TS_RE = /(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?/;
function parseTimestamp(line) {
  const m = line.match(TS_RE);
  if (!m) return null;
  const frac = m[7] ? Number((m[7] + "000").slice(0, 3)) : 0;
  return Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6], frac);
}

// Human-friendly duration from milliseconds, e.g. "2h 14m", "8m 03s", "12s".
function formatDuration(ms) {
  const s = Math.round(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h}h ${String(m).padStart(2, "0")}m`;
  if (m) return `${m}m ${String(sec).padStart(2, "0")}s`;
  return `${sec}s`;
}

// ---------------------------------------------------------------------------
// Matching
// ---------------------------------------------------------------------------

function buildMatchers(terms) {
  return terms.map((t) => {
    if (t.regex) {
      const re = new RegExp(t.match); // caller owns flags via inline (?i) etc.
      return { ...t, test: (line) => re.test(line) };
    }
    return { ...t, test: (line) => line.indexOf(t.match) !== -1 };
  });
}

// ---------------------------------------------------------------------------
// Scan
// ---------------------------------------------------------------------------

async function scanFile(file, matchers, groupMode, counts, totals, filter, stateCtx) {
  const rl = readline.createInterface({
    input: fs.createReadStream(file, { encoding: "utf8" }),
    crlfDelay: Infinity,
  });

  const fileKey = path.basename(file);
  let lineCount = 0;

  // Per-file state timeline cursor. Reset at each file so the gap between the
  // last entry of one day's log and the first of the next is never counted.
  let prev = null; // { ms, value, groupKey }
  const maxGapMs = stateCtx && stateCtx.maxGapSeconds ? stateCtx.maxGapSeconds * 1000 : null;

  for await (const line of rl) {
    if (line.trim() === "") continue;

    // Date-range filter (inclusive), based on the line's own day stamp.
    const day = dayOf(line);
    if (filter.since && day && day < filter.since) continue;
    if (filter.until && day && day > filter.until) continue;

    lineCount++;

    let groupKey;
    if (groupMode === "file") groupKey = fileKey;
    else if (groupMode === "day") groupKey = day || fileKey;
    else groupKey = "__all__";

    for (const m of matchers) {
      if (m.test(line)) {
        totals[m.label] = (totals[m.label] || 0) + 1;
        if (!counts[m.label]) counts[m.label] = {};
        counts[m.label][groupKey] = (counts[m.label][groupKey] || 0) + 1;
      }
    }

    // --- State timeline: count entries and accumulate dwell time ---
    if (stateCtx) {
      const sm = line.match(stateCtx.re);
      if (sm) {
        const value = sm[1];
        const ms = parseTimestamp(line);
        // byGroup holds { count, ms } per group: count is attributed to the day
        // the state was entered, time to the day the (previous) state started.
        const bucket = (v, g) => {
          if (!stateCtx.stats[v]) stateCtx.stats[v] = { count: 0, ms: 0, byGroup: {} };
          if (!stateCtx.stats[v].byGroup[g]) stateCtx.stats[v].byGroup[g] = { count: 0, ms: 0 };
          return stateCtx.stats[v].byGroup[g];
        };
        // Close out the previous state: its dwell = now - its entry time.
        if (prev && ms != null && prev.ms != null) {
          const delta = ms - prev.ms;
          if (delta > 0 && (maxGapMs == null || delta <= maxGapMs)) {
            stateCtx.stats[prev.value].ms += delta;
            bucket(prev.value, prev.groupKey).ms += delta;
          }
        }
        const bg = bucket(value, groupKey); // also initializes stats[value]
        stateCtx.stats[value].count++;
        bg.count++;
        prev = { ms, value, groupKey };
      }
    }
  }
  return lineCount;
}

// ---------------------------------------------------------------------------
// Console rendering
// ---------------------------------------------------------------------------

const BAR_WIDTH = 40;

function bar(value, max, width = BAR_WIDTH) {
  if (max <= 0) return "";
  const filled = Math.round((value / max) * width);
  return "█".repeat(filled) + "░".repeat(width - filled);
}

function pad(str, len) {
  str = String(str);
  return str.length >= len ? str : str + " ".repeat(len - str.length);
}

function renderConsole(settings, result) {
  const { title } = settings;
  const { totals, counts, groups, state, filesScanned, linesScanned } = result;

  const line = "=".repeat(64);
  const out = [];
  out.push(line);
  out.push("  " + title);
  out.push(line);
  out.push(`  Files scanned : ${filesScanned}`);
  out.push(`  Lines scanned : ${linesScanned.toLocaleString()}`);
  if (groups.length) {
    out.push(`  Range         : ${groups[0]} → ${groups[groups.length - 1]}`);
  }
  if (settings.since || settings.until) {
    out.push(`  Date filter   : ${settings.since || "…"} → ${settings.until || "…"}`);
  }
  out.push("");

  const labels = Object.keys(totals);
  const sorted = [...labels].sort((a, b) => totals[b] - totals[a]);

  // ---- State timeline: count + total time (the headline for usage) ----
  if (state && state.values.length) {
    const vals = [...state.values].sort((a, b) => b.ms - a.ms);
    const totalMs = vals.reduce((s, v) => s + v.ms, 0);
    const totalCount = vals.reduce((s, v) => s + v.count, 0);
    const maxMs = vals.reduce((m, v) => Math.max(m, v.ms), 0);
    const stLabelW = Math.min(24, Math.max(8, ...vals.map((v) => v.label.length)));

    out.push("  TIME IN STATE");
    out.push("  " + "-".repeat(62));
    for (const v of vals) {
      const pct = totalMs ? ((v.ms / totalMs) * 100).toFixed(1) : "0.0";
      out.push(
        `  ${pad(v.label, stLabelW)}  ${bar(v.ms, maxMs)}  ${pad(formatDuration(v.ms), 9)} ${pad(pct + "%", 6)}  ${pad(v.count, 5)}x`,
      );
    }
    out.push("  " + "-".repeat(62));
    out.push(
      `  ${pad("TOTAL", stLabelW)}  ${" ".repeat(BAR_WIDTH)}  ${pad(formatDuration(totalMs), 9)}         ${totalCount}x`,
    );
    out.push("");
  }

  // ---- Term totals with bars ----
  if (labels.length) {
    out.push("  TOTALS");
    out.push("  " + "-".repeat(62));
    const grandTotal = labels.reduce((s, l) => s + totals[l], 0);
    const maxTotal = labels.reduce((m, l) => Math.max(m, totals[l]), 0);
    const labelW = Math.min(24, Math.max(8, ...labels.map((l) => l.length)));
    for (const l of sorted) {
      const v = totals[l];
      const pct = grandTotal ? ((v / grandTotal) * 100).toFixed(1) : "0.0";
      out.push(`  ${pad(l, labelW)}  ${bar(v, maxTotal)}  ${pad(v, 6)} ${pct}%`);
    }
    out.push("");
  }

  // ---- Per-group breakdown table (term counts) ----
  if (labels.length && settings.group !== "none" && groups.length) {
    out.push(`  BY ${settings.group.toUpperCase()}`);
    out.push("  " + "-".repeat(62));
    // Header
    const gW = Math.max(10, ...groups.map((g) => g.length));
    let header = "  " + pad(settings.group, gW);
    for (const l of sorted) header += "  " + pad(l, Math.max(6, l.length));
    out.push(header);
    for (const g of groups) {
      let row = "  " + pad(g, gW);
      for (const l of sorted) {
        const v = (counts[l] && counts[l][g]) || 0;
        row += "  " + pad(v, Math.max(6, l.length));
      }
      out.push(row);
    }
    out.push("");
  }

  // ---- Per-group state breakdown (one block per day: time, %, count) ----
  if (state && state.values.length && settings.group !== "none" && groups.length) {
    const order = [...state.values].sort((a, b) => b.ms - a.ms);
    const stLabelW = Math.min(24, Math.max(8, ...order.map((v) => v.label.length)));
    out.push(`  TIME IN STATE BY ${settings.group.toUpperCase()}`);
    out.push("  " + "=".repeat(62));
    for (const g of groups) {
      const perDay = order
        .map((v) => ({ label: v.label, bg: v.byGroup[g] || { count: 0, ms: 0 } }))
        .filter((r) => r.bg.count || r.bg.ms)
        .sort((a, b) => b.bg.ms - a.bg.ms);
      const dayMs = perDay.reduce((s, r) => s + r.bg.ms, 0);
      const dayCount = perDay.reduce((s, r) => s + r.bg.count, 0);
      const maxDayMs = perDay.reduce((m, r) => Math.max(m, r.bg.ms), 0);
      out.push(`  ${g}   (${formatDuration(dayMs)} logged, ${dayCount} entries)`);
      for (const r of perDay) {
        const pct = dayMs ? ((r.bg.ms / dayMs) * 100).toFixed(1) : "0.0";
        out.push(
          `    ${pad(r.label, stLabelW)}  ${bar(r.bg.ms, maxDayMs, 24)}  ${pad(formatDuration(r.bg.ms), 9)} ${pad(pct + "%", 6)}  ${pad(r.bg.count, 4)}x`,
        );
      }
      out.push("");
    }
  }

  out.push(line);
  return out.join("\n");
}

// ---------------------------------------------------------------------------
// HTML rendering (standalone, no external assets)
// ---------------------------------------------------------------------------

function esc(s) {
  return String(s).replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
}

const PALETTE = ["#4f6cff", "#00b3a4", "#ff9f40", "#ff5d73", "#8a63d2", "#3aa76d", "#d4a017"];
const colorOf = (i) => PALETTE[i % PALETTE.length];
const CHART_W = 720;

// Horizontal bar chart. items: [{ label, value, display, color }].
function hBarChart(items, ariaLabel) {
  const rowH = 34;
  const svgH = items.length * rowH + 10;
  const labelW = 160;
  const barArea = CHART_W - labelW - 130;
  const max = items.reduce((m, it) => Math.max(m, it.value), 0) || 1;
  let bars = "";
  items.forEach((it, i) => {
    const w = Math.max(2, (it.value / max) * barArea);
    const y = i * rowH + 8;
    bars += `
      <text x="${labelW - 10}" y="${y + 15}" text-anchor="end" class="lbl">${esc(it.label)}</text>
      <rect x="${labelW}" y="${y}" width="${w}" height="22" rx="4" fill="${it.color}"></rect>
      <text x="${labelW + w + 8}" y="${y + 15}" class="val">${esc(it.display)}</text>`;
  });
  return `<svg viewBox="0 0 ${CHART_W} ${svgH}" width="100%" role="img" aria-label="${esc(ariaLabel)}">${bars}</svg>`;
}

// Stacked column chart over groups. series: [{ label, color, value(group)->num }].
function stackedChart(groups, series, ariaLabel, fmt) {
  const colGap = 6;
  const chartHeight = 220;
  const axisPad = 28;
  const innerW = CHART_W - 40;
  const colW = Math.max(4, innerW / groups.length - colGap);
  const groupMax = Math.max(1, ...groups.map((g) => series.reduce((s, ser) => s + ser.value(g), 0)));
  let cols = "";
  groups.forEach((g, gi) => {
    const x = 20 + gi * (colW + colGap);
    let yCursor = chartHeight - axisPad;
    series.forEach((ser) => {
      const v = ser.value(g);
      if (!v) return;
      const h = (v / groupMax) * (chartHeight - axisPad - 10);
      yCursor -= h;
      cols += `<rect x="${x}" y="${yCursor}" width="${colW}" height="${h}" fill="${ser.color}"><title>${esc(g)} — ${esc(ser.label)}: ${esc(fmt(v))}</title></rect>`;
    });
    const short = g.length > 10 ? g.slice(5) : g; // drop year if YYYY-MM-DD
    cols += `<text x="${x + colW / 2}" y="${chartHeight - axisPad + 14}" text-anchor="middle" class="axis" transform="rotate(35 ${x + colW / 2} ${chartHeight - axisPad + 14})">${esc(short)}</text>`;
  });
  return `<svg viewBox="0 0 ${CHART_W} ${chartHeight + 20}" width="100%" role="img" aria-label="${esc(ariaLabel)}">
        <line x1="20" y1="${chartHeight - axisPad}" x2="${CHART_W - 20}" y2="${chartHeight - axisPad}" class="axisline"/>
        ${cols}</svg>`;
}

function renderHtml(settings, result) {
  const { title } = settings;
  const { totals, counts, groups, state, filesScanned, linesScanned } = result;
  const sections = [];
  let legendItems = []; // [{label, color}]

  // ---- State: time-in-state (headline) ----
  if (state && state.values.length) {
    const vals = [...state.values].sort((a, b) => b.ms - a.ms);
    const totalMs = vals.reduce((s, v) => s + v.ms, 0) || 1;
    const colored = vals.map((v, i) => ({ ...v, color: colorOf(i) }));
    legendItems = colored.map((v) => ({ label: v.label, color: v.color }));

    const items = colored.map((v) => ({
      label: v.label,
      value: v.ms,
      color: v.color,
      display: `${formatDuration(v.ms)} · ${((v.ms / totalMs) * 100).toFixed(1)}% · ${v.count}×`,
    }));
    sections.push(`<h2>Time in state</h2>${hBarChart(items, "Total time per state")}`);

    const bgOf = (v, g) => v.byGroup[g] || { count: 0, ms: 0 };

    if (settings.group !== "none" && groups.length) {
      const series = colored.map((v) => ({
        label: v.label,
        color: v.color,
        value: (g) => bgOf(v, g).ms,
      }));
      sections.push(
        `<h2>Time by ${esc(settings.group)}</h2>${stackedChart(groups, series, "Time in state by " + settings.group, formatDuration)}`,
      );

      // Per-day table: time (with entry count) per state, one row per day.
      let pd = `<table><thead><tr><th>${esc(settings.group)}</th>`;
      colored.forEach((v) => (pd += `<th>${esc(v.label)}</th>`));
      pd += `<th>total</th></tr></thead><tbody>`;
      groups.forEach((g) => {
        pd += `<tr><td>${esc(g)}</td>`;
        let dayMs = 0;
        colored.forEach((v) => {
          const b = bgOf(v, g);
          dayMs += b.ms;
          pd += `<td>${b.ms ? formatDuration(b.ms) : "–"}<span class="sub"> ${b.count}×</span></td>`;
        });
        pd += `<td>${formatDuration(dayMs)}</td></tr>`;
      });
      pd += `<tr class="total"><td>total</td>`;
      colored.forEach((v) => (pd += `<td>${formatDuration(v.ms)}<span class="sub"> ${v.count}×</span></td>`));
      pd += `<td>${formatDuration(colored.reduce((s, v) => s + v.ms, 0))}</td></tr></tbody></table>`;
      sections.push(`<h2>Time in state by ${esc(settings.group)}</h2>${pd}`);
    }

    // State totals table (time + count)
    let t = `<table><thead><tr><th>state</th><th>total time</th><th>entries</th></tr></thead><tbody>`;
    colored.forEach((v) => {
      t += `<tr><td>${esc(v.label)}</td><td>${formatDuration(v.ms)}</td><td>${v.count}</td></tr>`;
    });
    const tc = colored.reduce((s, v) => s + v.count, 0);
    t += `<tr class="total"><td>total</td><td>${formatDuration(colored.reduce((s, v) => s + v.ms, 0))}</td><td>${tc}</td></tr></tbody></table>`;
    sections.push(`<h2>State totals</h2>${t}`);
  }

  // ---- Terms: counts ----
  const labels = Object.keys(totals);
  const sorted = [...labels].sort((a, b) => totals[b] - totals[a]);
  if (labels.length) {
    const grandTotal = sorted.reduce((s, l) => s + totals[l], 0) || 1;
    const colored = sorted.map((l, i) => ({ label: l, color: colorOf(i) }));
    if (!legendItems.length) legendItems = colored;

    const items = sorted.map((l, i) => ({
      label: l,
      value: totals[l],
      color: colorOf(i),
      display: `${totals[l].toLocaleString()} · ${((totals[l] / grandTotal) * 100).toFixed(1)}%`,
    }));
    sections.push(`<h2>Totals</h2>${hBarChart(items, "Totals by term")}`);

    if (settings.group !== "none" && groups.length) {
      const series = sorted.map((l, i) => ({
        label: l,
        color: colorOf(i),
        value: (g) => (counts[l] && counts[l][g]) || 0,
      }));
      sections.push(
        `<h2>Counts by ${esc(settings.group)}</h2>${stackedChart(groups, series, "Counts by " + settings.group, (n) => String(n))}`,
      );
    }

    let table = `<table><thead><tr><th>${esc(settings.group === "none" ? "scope" : settings.group)}</th>`;
    sorted.forEach((l) => (table += `<th>${esc(l)}</th>`));
    table += "</tr></thead><tbody>";
    const rowGroups = settings.group === "none" ? ["__all__"] : groups;
    rowGroups.forEach((g) => {
      table += `<tr><td>${esc(g === "__all__" ? "all" : g)}</td>`;
      sorted.forEach((l) => (table += `<td>${(counts[l] && counts[l][g]) || 0}</td>`));
      table += "</tr>";
    });
    table += `<tr class="total"><td>total</td>`;
    sorted.forEach((l) => (table += `<td>${totals[l].toLocaleString()}</td>`));
    table += "</tr></tbody></table>";
    sections.push(`<h2>Count data</h2>${table}`);
  }

  const legend = legendItems
    .map((it) => `<span class="chip"><i style="background:${it.color}"></i>${esc(it.label)}</span>`)
    .join("");

  const rangeStr = groups.length ? `${groups[0]} &rarr; ${groups[groups.length - 1]}` : "—";
  const filterStr =
    settings.since || settings.until
      ? ` &middot; filtered ${esc(settings.since || "…")} &rarr; ${esc(settings.until || "…")}`
      : "";

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body { font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         margin: 0; padding: 32px; background: #f6f7fb; color: #1a1c22; }
  .wrap { max-width: 820px; margin: 0 auto; background: #fff; border-radius: 14px;
          padding: 28px 32px; box-shadow: 0 1px 3px rgba(0,0,0,.08), 0 8px 24px rgba(0,0,0,.05); }
  h1 { margin: 0 0 4px; font-size: 22px; }
  h2 { margin: 32px 0 12px; font-size: 16px; text-transform: uppercase; letter-spacing: .04em; color: #6b7280; }
  .meta { color: #6b7280; font-size: 13px; margin-bottom: 4px; }
  .lbl { fill: #374151; font-size: 13px; }
  .val { fill: #6b7280; font-size: 12px; }
  .axis { fill: #9ca3af; font-size: 10px; }
  .axisline { stroke: #e5e7eb; stroke-width: 1; }
  .legend { margin: 8px 0 0; display: flex; flex-wrap: wrap; gap: 12px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: #4b5563; }
  .chip i { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
  table { border-collapse: collapse; width: 100%; margin-top: 12px; font-size: 13px; }
  th, td { text-align: right; padding: 6px 10px; border-bottom: 1px solid #eceef3; }
  th:first-child, td:first-child { text-align: left; font-variant-numeric: tabular-nums; }
  td { font-variant-numeric: tabular-nums; }
  tr.total td { font-weight: 700; border-top: 2px solid #d1d5db; }
  .sub { color: #9ca3af; font-size: 11px; font-weight: 400; }
  footer { margin-top: 24px; font-size: 11px; color: #9ca3af; }
  @media (prefers-color-scheme: dark) {
    body { background: #0f1117; color: #e5e7eb; }
    .wrap { background: #171a21; box-shadow: none; }
    .lbl { fill: #d1d5db; } .val,.meta { fill: #9ca3af; color: #9ca3af; }
    th, td { border-bottom-color: #262a33; }
    tr.total td { border-top-color: #3a3f4b; }
    .chip { color: #9ca3af; }
  }
</style>
</head>
<body>
  <div class="wrap">
    <h1>${esc(title)}</h1>
    <div class="meta">${filesScanned} file(s) &middot; ${linesScanned.toLocaleString()} lines &middot; ${rangeStr}${filterStr}</div>
    <div class="legend">${legend}</div>
    ${sections.join("\n    ")}
    <footer>Generated by touchdesigner/scripts/log-report.js</footer>
  </div>
</body>
</html>`;
}

// ---------------------------------------------------------------------------
// CSV rendering
// ---------------------------------------------------------------------------

function renderCsv(settings, result) {
  const { totals, counts, groups, state } = result;
  const csvEsc = (s) => (/[",\n]/.test(s) ? `"${String(s).replace(/"/g, '""')}"` : String(s));
  const scopeGroups = settings.group === "none" ? ["__all__"] : groups;
  const rows = ["metric,label,group,value"];

  // State: total + per-group entry count and time (seconds).
  if (state && state.values.length) {
    for (const v of state.values) {
      rows.push(`count,${csvEsc(v.label)},TOTAL,${v.count}`);
      rows.push(`seconds,${csvEsc(v.label)},TOTAL,${Math.round(v.ms / 1000)}`);
      for (const g of scopeGroups) {
        if (g === "__all__") continue;
        const b = (v.byGroup && v.byGroup[g]) || { count: 0, ms: 0 };
        rows.push(`count,${csvEsc(v.label)},${csvEsc(g)},${b.count}`);
        rows.push(`seconds,${csvEsc(v.label)},${csvEsc(g)},${Math.round(b.ms / 1000)}`);
      }
    }
  }

  // Term counts.
  const sorted = Object.keys(totals).sort((a, b) => totals[b] - totals[a]);
  for (const l of sorted) {
    for (const g of scopeGroups) {
      const v = (counts[l] && counts[l][g]) || 0;
      rows.push(`count,${csvEsc(l)},${csvEsc(g === "__all__" ? "all" : g)},${v}`);
    }
    rows.push(`count,${csvEsc(l)},TOTAL,${totals[l]}`);
  }
  return rows.join("\n") + "\n";
}

// ---------------------------------------------------------------------------
// Help
// ---------------------------------------------------------------------------

function printHelp() {
  const header = fs.readFileSync(__filename, "utf8");
  // Print the top comment block as help.
  const block = header.slice(header.indexOf("/*") + 2, header.indexOf("*/"));
  console.log(block.replace(/^ \* ?/gm, "").trim());
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.help) return printHelp();

  const settings = resolveSettings(opts);

  if (!settings.terms.length && !settings.state) {
    console.error("Error: nothing to report. Provide --find <term>, --state <regex>, or --config <file>.");
    console.error("Run with --help for usage.");
    process.exitCode = 1;
    return;
  }

  let files;
  try {
    files = discoverFiles(settings.logs, settings.ext);
  } catch (err) {
    console.error(`Error reading logs at "${settings.logs}": ${err.message}`);
    process.exitCode = 1;
    return;
  }
  if (!files.length) {
    console.error(`No log files (${settings.ext.join(", ")}) found in "${settings.logs}".`);
    process.exitCode = 1;
    return;
  }

  const matchers = buildMatchers(settings.terms);
  const counts = {}; // label -> { groupKey -> count }
  const totals = {}; // label -> count
  // Ensure every term shows up even with zero hits.
  for (const t of settings.terms) {
    totals[t.label] = 0;
    counts[t.label] = {};
  }

  const stateCtx = settings.state
    ? { re: new RegExp(settings.state.match), stats: {}, maxGapSeconds: settings.state.maxGapSeconds }
    : null;

  const filter = { since: settings.since, until: settings.until };

  let linesScanned = 0;
  let filesWithData = 0;
  for (const file of files) {
    const n = await scanFile(file, matchers, settings.group, counts, totals, filter, stateCtx);
    linesScanned += n;
    if (n > 0) filesWithData++;
  }

  // Collect the sorted set of group keys actually seen (across terms + state).
  const groupSet = new Set();
  for (const l of Object.keys(counts)) {
    for (const g of Object.keys(counts[l])) if (g !== "__all__") groupSet.add(g);
  }
  if (stateCtx) {
    for (const v of Object.keys(stateCtx.stats)) {
      for (const g of Object.keys(stateCtx.stats[v].byGroup)) if (g !== "__all__") groupSet.add(g);
    }
  }
  const groups = [...groupSet].sort();

  // Shape the state result with friendly labels applied.
  let state = null;
  if (stateCtx) {
    const labels = settings.state.labels || {};
    const values = Object.keys(stateCtx.stats).map((v) => ({
      value: v,
      label: labels[v] || v,
      count: stateCtx.stats[v].count,
      ms: stateCtx.stats[v].ms,
      byGroup: stateCtx.stats[v].byGroup,
    }));
    state = { values };
  }

  const result = {
    totals,
    counts,
    groups,
    state,
    filesScanned: filesWithData,
    linesScanned,
  };

  console.log(renderConsole(settings, result));

  if (settings.html) {
    fs.writeFileSync(settings.html, renderHtml(settings, result), "utf8");
    console.log(`HTML report written to ${settings.html}`);
  }
  if (settings.csv) {
    fs.writeFileSync(settings.csv, renderCsv(settings, result), "utf8");
    console.log(`CSV written to ${settings.csv}`);
  }
}

main().catch((err) => {
  console.error(err.stack || String(err));
  process.exitCode = 1;
});
