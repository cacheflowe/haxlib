# log-report.js

A zero-dependency, cross-platform (Windows / macOS / Linux) Node.js tool for
turning event logs into a usage report. It can:

- **Count** how often each search term appears across one file or a whole
  directory of logs (grouped by day or by file).
- **Measure time-in-state** — for a state field like `app_state=...`, report
  both the entry count *and* the total time spent in each state (dwell time =
  the gap until the next entry, computed within each file so overnight gaps
  between daily logs are never counted).
- **Filter by date range** so you can exclude testing days.

Output includes both an overall total and, when grouped by day, a per-day
breakdown (time, share of that day, and entry count for each state). CSV emits
per-day `count` and `seconds` rows for both metrics.

It prints an ASCII-bar summary to the console and can emit a standalone **HTML
report** with inline SVG charts to hand to a client — no `npm install`, no
external assets.

Because it only uses Node core modules, you can copy `log-report.js` into any
project and point it at a different log folder with a different set of terms.

## Usage

Run these from the `touchdesigner/` directory (`cd touchdesigner` first):

```sh
# Use the project config (recommended — repeatable).
# log-report.config.json is set up for the app_state field and scoped to the
# live show dates (2026-01-06 → 2026-01-09).
node scripts/log-report.js --config scripts/log-report.config.json

# Also write a shareable HTML report + CSV
node scripts/log-report.js --config scripts/log-report.config.json \
  --html report.html --csv report.csv

# Ad-hoc: count one or more terms in a folder of logs
node scripts/log-report.js --logs logs \
  --find "app_state=chill" --label "Chill" \
  --find "app_state=nightclub" --label "Nightclub"

# Ad-hoc time-in-state (regex needs one capture group for the state value)
node scripts/log-report.js --logs logs --state "app_state=(\w+)"

# Override the config's date range (e.g. see all testing days too)
node scripts/log-report.js --config scripts/log-report.config.json --since 2025-12-18
```

The config's `logs` path is resolved relative to the config file, so the
config-based commands work from any directory — e.g. from the repo root:
`node touchdesigner/scripts/log-report.js --config touchdesigner/scripts/log-report.config.json`.

## Options

| Flag | Description |
|------|-------------|
| `--logs <path>` | Log file **or** directory (scanned non-recursively). Default: cwd. |
| `--find <term>` | Search term (repeatable). Plain substring unless `--regex`. |
| `--label <text>` | Friendly label for the preceding `--find`. |
| `--regex` | Treat every `--find` term as a JS regular expression. |
| `--state <regex>` | Time-in-state analysis. Regex needs one capture group, e.g. `"app_state=(\w+)"`. Reports count + total time per state. |
| `--since <date>` | Only include lines on/after this day (`YYYY-MM-DD`). |
| `--until <date>` | Only include lines on/before this day (`YYYY-MM-DD`). |
| `--group <mode>` | `day` (default), `file`, or `none`. |
| `--config <path>` | JSON config; CLI flags override it. A relative `logs` in the config resolves relative to the config file. |
| `--html <path>` | Also write a standalone HTML report. |
| `--csv <path>` | Also write a CSV (`metric,label,group,value`). |
| `--ext <list>` | Extensions to scan in a directory. Default: `txt,log`. |
| `-h`, `--help` | Show help. |

## Config file

A config makes a report repeatable and is the easy thing to change per project.
A config can define `terms` (counts), a `state` block (count + time), or both.
Each term may set `"regex": true` individually.

**Time-in-state config** (what this project uses — see
[`log-report.config.json`](log-report.config.json)):

```json
{
  "title": "My Project — Usage",
  "logs": "../logs",
  "group": "day",
  "since": "2026-01-06",
  "until": "2026-01-09",
  "state": {
    "match": "app_state=(\\w+)",
    "labels": { "attract": "Attract (idle)", "chill": "Chill" },
    "maxGapSeconds": null
  }
}
```

- `match` — regex with **one capture group** holding the state value.
- `labels` — optional friendly names, keyed by captured value.
- `maxGapSeconds` — optional cap: gaps longer than this between entries are
  treated as "unknown" and not added to a state's time (useful if the app was
  shut down mid-day). `null`/omitted = count every gap within a file.

**Term-count config:**

```json
{
  "title": "My Project — Usage",
  "logs": "path/to/logs",
  "group": "day",
  "terms": [
    { "label": "Sessions started", "match": "session_start" },
    { "label": "Errors", "match": "\\| error \\|", "regex": true }
  ]
}
```

## Log format assumptions

- One event per line.
- Day grouping looks for the first `YYYY-MM-DD` on each line; lines without one
  fall back to being grouped by filename. This project's logs
  (`timestamp | level | source | message`) work out of the box.

## Reusing across projects

Copy `log-report.js` into the new project's scripts folder and add a
`log-report.config.json` next to it with that project's terms (or `state`
block). Point the config's `logs` at that project's log folder. Nothing else is
required.
