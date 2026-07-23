# TouchDesigner HTTP Bridge — Agent Quick Start

Welcome to `TdHttpApi`, the HTTP bridge that gives **AI agents autonomous read/write access** to your running TouchDesigner project. Agents can inspect, build, and debug networks directly via a REST API and open-ended Python scripting, mirroring everything that's possible with traditional manual editing in the TouchDesigner UI. This allows your coding agent (Claude/Copilot/etc) to **see the network, understand it, and modify it**, which gives you the power of agentic coding tools that are commonly used in traditional software development, but now applied to the TouchDesigner IDE.

> ⚠️ Any agentic interaction has the potential to mutate the network state immediately, with no undo. Use caution when running destructive operations, and back up your project often.

This tool is a work-in-progress, and the API is still evolving. If you have questions or suggestions, please reach out or open an issue on GitHub. The goal is to make this a robust and reliable tool for agentic TouchDesigner development.

## What You Can Do

### 🔍 **Inspect & Debug Networks**
- **See the full network structure** — all nodes, wires, and parameters as JSON
- **Find errors instantly** — list all broken operators and their error messages
- **Verify what's running** — inspect cook times, memory, and performance metrics
- **Read any DAT** — pull Python script or CSV content without opening files

### 🛠️ **Find & Fix Problems**
- **Identify parameter mistakes** — discover the exact param names instead of guessing (`radx` vs `rad0`)
- **Check operator signatures** — know if a node expects wired inputs or parameter references
- **Trace references** — see which nodes depend on which, spot broken chains
- **Understand errors in context** — read the full error message and the surrounding network

### 📖 **Explain Networks**
- **Generate network diagrams** — export as Mermaid (`/network.mmd`) for visualization
- **List all connections** — see data flow without looking at the UI
- **Describe patterns** — understand what each part of the network does

### 📚 **Learn from Official Examples**
- **Request example networks** — get curated code snippets for any operator type (via `/examples` route)
- **Ask about node types** — get explanations and use cases for any TouchDesigner operator
- **Learn techniques** — understand how to wire feedback loops, manage state, compose effects, etc.

### 🏗️ **Build Networks Programmatically**
- **Create nodes** — specify type, position, and parameters
- **Wire them up** — connect inputs/outputs with full control
- **Batch operations** — build entire sub-networks in one script
- **Use templates** — capture hand-built patterns and replay them
- **Hot-reload Python** — edit your scripts and reload without restarting TD

### 🎯 **Other Powers**
- **Set parameters** — read and write any parameter value or expression
- **Run Python** — execute one-off scripts and capture output
- **Move & organize** — reposition nodes, add comments, group with annotations
- **Compare snapshots** — diff two network states to see exactly what changed

---

## Getting Started

### Step 1: Install the TdHttpApi Component

Drop the `TdHttpApi.tox` component into your TouchDesigner project. It runs a local HTTP server on port 3031, exposing the entire network and Python API.

### Step 2: Verify the Bridge Is Live

`curl` http://127.0.0.1:3031/health or visit in a browser. You should see a JSON response.

If this fails, check:
1. Is TouchDesigner running and the project open?
2. Is the `TdHttpApi` COMP active (no red errors)?
3. Are you using `127.0.0.1` (not `localhost`)?

### Step 3: Connect Your Agent

Run a prompt to let your agent know how to use the bridge. There's a robust example prompt in the `TdHttpApi` COMP's `prompt_agent_init` DAT.

For a quick start, you can use the following simple prompt to orient your agent:

```
Use the TdHttpApi at http://127.0.0.1:3031 to inspect and modify the live TouchDesigner project.
```

---

## Optional Additions (Unlocks More 🤖 Power)

These aren't required, but they'll make your work smarter and faster, with fewer hallucinations and mistakes:

### **Skills & Documentation**
If your project has a `skills/` folder, you can copy the embedded skills in `TdHttpApi.tox` into it. These skills provide **high-level guidance** for your agent, including:
- `td-http-api.md` — friction points and best practices
- `td-network-craft.md` — idiomatic network-building technique
- `td-common-mistakes.md` — common TD Python traps to avoid

### **MCP Server: [td-docs-mcp](https://github.com/cacheflowe/td-docs-mcp)**
Query TouchDesigner's official documentation directly from your editor:
- "What parameters does a `poptoCHOP` have?"
- "Show me the Python API for CHOP operators"
- "What does the `attribscope` parameter do?"

Configured in `.mcp.json`; requires `uv` and the td-docs-mcp repo.

---

Good luck! 🚀
