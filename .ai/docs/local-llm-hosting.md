# Hosting local models w/llama.cpp

### Use llama.cpp

[Install](https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md):

```bash
brew install llama.cpp
```

```powershell
winget install llama.cpp
```

### Download Gemma 4

Download:

[unsloth/gemma-4-26B-A4B-it-GGUF](https://huggingface.co/unsloth/gemma-4-26B-A4B-it-GGUF) - RTX 4090+ (24GB+ VRAM)
[unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF) - RTX 4090+ (24GB+ VRAM)
[unsloth/gemma-4-12B-it-GGUF](https://huggingface.co/unsloth/gemma-4-12B-it-qat-GGUF) - Need to try on an in-between GPU/MacBook
[unsloth/gemma-4-E4B-it-qat-GGUF](https://huggingface.co/unsloth/gemma-4-E4B-it-qat-GGUF) - MacBook M1 (32GB RAM)

### Run llama-server:

```bash
# -fa on - enable auto-fallback to CPU if GPU memory is insufficient (this will allow the model to run even if it doesn't fit entirely in GPU memory, but may be slower)
# -c 4096 - set context size to 4096 tokens (this is the default, but you can increase it if your GPU has enough memory)
# --ngl 99 - use all available GPU layers (this will automatically determine how many layers to offload based on your GPU memory)
# --jinja - enable jinja templating for better prompt formatting (this should use the model's default template if available)
# --host 0.0.0.0 - allow access from other machines on the network
# --ctx-size 131072 - increase context size to 128k tokens (default is 4096)
# --tools all - enable all tools (this will allow the model to use tools like search, calculator, etc. if supported)

# Bigger models on a 4090+ (24GB+ VRAM)
llama-server --model .\models\gemma-4-26B-A4B-it-UD-Q4_K_M.gguf -c 4096 -ngl 99 --jinja --port 8080 --host 0.0.0.0 --ctx-size 131072 --tools all
llama-server --model .\models\Qwen3.6-27B-Q4_K_M.gguf -fa on -ngl 99 --ctx-size 131072 -ctk q4_0 -ctv q4_0 --jinja --port 8080 --host 0.0.0.0 --tools all

# Smaller models on a MacBook M1 (32GB RAM)
llama-server --model ./gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf -ngl 99 -t 8 -c 32768 --jinja --tools all --parallel 1 --flash-attn on --cache-ram 4096
```

### Use pi to code:

```powershell
powershell -c "irm https://pi.dev/install.ps1 | iex"
```

```bash
curl -fsSL https://pi.dev/install.sh | sh
```

Or download from Github releases, extract, and add to path

Install `pi-llama-cpp` to connect to llama-server, and the mcp extension to connect to MCP servers:

```bash
pi install npm:pi-llama-cpp
pi install npm:pi-mcp-extension
```

#### Configure pi to point to your local llama-server:

In `~\.pi\agent\settings.json`, add:

```json
"defaultProvider": "llama-server=http://steiger-pc-1.local:8080"
```

Or configure multiple providers via the [official docs](https://pi.dev/packages/pi-lmstudio)

#### Start an mcp server in pi (example)

```bash
/mcp:start td-docs-mcp
```

#### Run a single task with pi, then exit:

```bash
pi -p "Please write a limerick about the number pi"
```

Docs are here:

```
https://pi.dev/docs/latest/usage
```

### Point Claude or Copilot at a local LM Studio server:

I didn't have great luck here, but keeping the info for reference.

```bash
ANTHROPIC_BASE_URL="http://steiger-pc-1.local:8080" export ANTHROPIC_API_KEY="local-bypass" claude
```

```
"claude": "cross-env ANTHROPIC_BASE_URL=http://steiger-pc-1.local:8080 ANTHROPIC_API_KEY=lmstudio claude --model google/gemma-4-26b-a4b-qat",
"claude-q": "cross-env ANTHROPIC_BASE_URL=http://steiger-pc-1.local:8080 ANTHROPIC_API_KEY=lmstudio claude --model qwen/qwen3.6-27b",
"copilot": "cross-env COPILOT_PROVIDER_BASE_URL=http://steiger-pc-1.local:8080/v1 COPILOT_MODEL=google/gemma-4-26b-a4b COPILOT_OFFLINE=true copilot",
"copilot-q": "cross-env COPILOT_PROVIDER_BASE_URL=http://steiger-pc-1.local:8080/v1 COPILOT_MODEL=qwen/qwen3.6-27b COPILOT_OFFLINE=true copilot",
```