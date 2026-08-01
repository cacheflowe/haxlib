# Agent Learnings Log

Hard-won debugging discoveries that aren't covered by official docs. Read before debugging;
write an entry after solving anything non-obvious. See [CLAUDE.md](../CLAUDE.md) for format.

## Files

- [learnings/onnx-runtime.md](learnings/onnx-runtime.md) — ONNX Runtime / TouchDesigner: CUDA EP
  silently falling back to CPU due to cuDNN version mismatches with onnxruntime-gpu's cudnn
  frontend; a measured `arena_extend_strategy` regression and the input-to-output latency
  tuning investigation behind it (see also
  [.ai/skills/td-threaded-inference-optimization.md](../.ai/skills/td-threaded-inference-optimization.md)).
