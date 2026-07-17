---
name: td-agent-init
description: Orient an agent at the start of a live TouchDesigner session — load the td-http-api and td-network-craft skills, register the td-docs-mcp server, confirm the HTTP bridge connection, and report the open network. Use as the first message when collaborating on a running TD project.
---

# TD Session Start

We're collaborating on a **live TouchDesigner project** over the td-http-api HTTP bridge. Get oriented before doing anything else.

## 1. Load the skills

Read and follow these two skills:

- **`td-http-api`** — the HTTP bridge into the running TD project. This is your primary tool; it documents every route.
- **`td-network-craft`** — idiomatic TD network-building technique plus the OP Snippets catalog at `data/harness/op-snippets/catalog.tsv` (a greppable index of 1386 official examples).

## 2. Register the docs MCP

For any TouchDesigner operator or Python-API question, query the **`td-docs-mcp`** MCP server — it holds the near-complete official TD documentation. Use it instead of relying on training data.

After registering it, make one lightweight documentation query to verify that the server is available. Do not treat registration alone as a successful connection.

## 3. Confirm the connection

The td-http-api server is live at `http://127.0.0.1:9980`. Confirm it now:

```
curl -s "http://127.0.0.1:9980/network"
```

It returns JSON describing the network currently open in the TD UI.

## Two rules that WILL bite you if ignored

- **Use `127.0.0.1`, never `localhost`** — localhost adds ~200ms per call.
- **Every POST/PUT must send a body, even an empty one:** `curl -X POST -d "" "..."`. Without one the server stalls for ~60 seconds.

## What you can do through the API

(Full route reference is in the `td-http-api` skill.)

- **Inspect:** `/network`, `/network.mmd`, `/bounds`, `/health`, `/logs`
- **See output:** `/snapshot` (a TOP's rendered frame as a PNG you can view), `/chop` (channel data)
- **Read/write:** `/par` (params), `/dat` (DAT code/tables)
- **Debug:** `/errors` (find and read node errors), then fix and re-check
- **Build:** `/create`, `/create-from-template`, `/insert` (splice into a wire), `/wire`, `/duplicate`, `/move`, `/delete`
- **Document:** `/comment`, `/annotate`
- **Collaborate:** `/selected` (read what I clicked in the UI), `/select` (highlight nodes + home my editor to direct my attention)
- **Power tools:** `/run` (arbitrary TD Python — best for complex multi-step operations), `/diff` (structural diff of two `/network` snapshots)

Everything **mutates live project state** — it's real, with no undo guarantees. Confirm destructive steps before running them.

When writing `/run` scripts, save them to a file and POST with `curl --data-binary @file` — not shell heredocs, which mangle backslashes.

## First action

Complete the startup checks before waiting for work:

1. Confirm that **`td-http-api`** and **`td-network-craft`** were found and loaded.
2. Confirm that **`td-docs-mcp`** is available by completing the lightweight documentation query.
3. Confirm the HTTP bridge with the `/network` request.
4. Report a concise readiness status for each check. If any check fails, say exactly which one failed and include the relevant error instead of implying that the session is ready.
5. If the checks pass, tell me which network I currently have open, then wait for what I want to work on.
