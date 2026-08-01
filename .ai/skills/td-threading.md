---
name: td-threading
description: Threading and background work patterns for TouchDesigner. Use this when offloading long-running work while keeping TD interactions on the main thread.
---

# Threading in TouchDesigner

Patterns for running background work without blocking TD's main thread. Critical rule: **never access TD operators from a background thread**.

## Core Concept

TouchDesigner is single-threaded for operator access. Background threads can do computation, I/O, and network calls, but must pass results back to the main thread via a queue or similar mechanism. The main thread polls the queue (typically via an Execute DAT callback every frame).

## Queue-Based Pattern

The standard pattern: thread puts results in a `queue.Queue`, main thread polls it each frame.

```python
import queue
import threading

class BackgroundWorker:
	def __init__(self, ownerComp: baseCOMP):
		self.ownerComp: baseCOMP = ownerComp
		self.result_queue = queue.Queue()
		self.thread = None

	def StartWork(self):
		"""Launch background thread."""
		self.thread = threading.Thread(target=self.workerThread)
		self.thread.daemon = True  # Dies when TD exits
		self.thread.start()

	def workerThread(self):
		"""Runs on background thread — NO TD operator access here."""
		result = do_expensive_computation()
		self.result_queue.put(result)

	def CheckResults(self):
		"""Called every frame from an Execute DAT on the main thread."""
		try:
			result = self.result_queue.get(block=False)
			# Safe to access TD operators here (main thread)
			self.ownerComp.op('table1')[0, 0].val = str(result)
		except queue.Empty:
			pass
```

Wire an Execute DAT to call `CheckResults()` every frame via its `onFrameStart` callback.

## Subprocess Pattern

Run external scripts/commands without blocking TD:

```python
import threading
import subprocess
from subprocess import Popen, PIPE, STDOUT

def run_script():
	p = Popen(
		['serve-all.cmd'],
		cwd='www\\scripts',
		stdout=PIPE, stderr=STDOUT,
		shell=True, text=True, bufsize=1
	)
	for line in p.stdout:
		print(line, end='')
	p.stdout.close()
	p.wait()

thread = threading.Thread(target=run_script)
thread.daemon = True
thread.start()
```

## Shell Script with Main-Thread Continuation

Starting a thread doesn't block — code after `thread.start()` runs immediately on the main thread while the subprocess runs in the background. This is useful when you need to kick off a long-running script and do other work at the same time:

```python
# https://docs.python.org/3/library/subprocess.html#subprocess.Popen

import threading
from subprocess import Popen, PIPE, STDOUT
import system_util  # project-specific module

def run_script():
	p = Popen(
		['serve-all.cmd'],
		cwd='www\\scripts',
		stdout=PIPE, stderr=STDOUT,
		shell=True, text=True, bufsize=1
	)
	for line in p.stdout:
		print(line, end='')  # stream output to textport as it arrives
	p.stdout.close()
	p.wait()

thread = threading.Thread(target=run_script)
thread.daemon = True  # thread dies when TD exits
thread.start()

# These run immediately on the main thread — no waiting for the script to finish
ip_addr = system_util.get_ip_address()
system_util.open_url(f'http://{ip_addr}:5173/app-store-distributed/index.html')
```

**How it works:**

1. `run_script` is passed as the thread's target — it runs on the background thread
2. `thread.start()` launches the thread and **returns immediately**
3. The `Popen` loop inside `run_script` streams subprocess output line-by-line to TD's textport as it arrives, without buffering
4. Meanwhile, `get_ip_address()` and `open_url()` run on the main thread concurrently — no delay waiting for the script
5. `p.wait()` (on the background thread) blocks until the subprocess exits, then the thread ends cleanly

**Fix applied:** the original code was missing `thread.daemon = True`. Without it, TD can hang on exit waiting for the background thread to finish.

## Web Server Example

A more complete example showing a threaded HTTP server with start/stop lifecycle:

```python
import queue
import threading

class PythonWebServer:
	def __init__(self, ownerComp: baseCOMP):
		self.ownerComp: baseCOMP = ownerComp
		self.status_queue = queue.Queue()
		self.httpd = None
		self.thread = None

	def StartServer(self):
		self.thread = threading.Thread(target=self.startServerThread)
		self.thread.daemon = True
		self.thread.start()

	def startServerThread(self):
		"""Background thread — start HTTP server."""
		# ... server setup ...
		self.SetActiveStatus([True, 'Running'])

	def CheckServerActive(self):
		"""Main thread — called by Execute DAT every frame."""
		try:
			result = self.status_queue.get(block=False)
			self.is_active = result[0]
		except queue.Empty:
			pass

	def SetActiveStatus(self, active):
		"""Thread-safe status update via queue."""
		self.status_queue.put(active)

	def StopServer(self):
		if self.httpd is None:
			print('[PythonWebServer] No server to stop!')
			self.SetActiveStatus([False, 'Stopped'])
			return
		stop_thread = threading.Thread(target=self.stopServerThread)
		stop_thread.start()

	def stopServerThread(self):
		"""Background thread — stop server and clean up."""
		self.thread.join()
		self.shutdown_event.set()
```

## Rules

1. **Never access `op()`, `me`, `parent()`, or any TD object from a thread** — crash or undefined behavior
2. **Set `thread.daemon = True`** so threads die when TD exits
3. **Use `queue.Queue`** for thread-safe communication to the main thread
4. **Poll the queue from an Execute DAT** callback (e.g., `onFrameStart`)
5. **Alternative**: Use `run()` with `delayFrames=0` from within a thread to schedule code on the main thread (use sparingly)

## Advanced Options

- **Python `threading.Event`** — signal between threads
- **Python `threading.Lock`** — protect shared data structures
- **TD Thread Manager** — experimental built-in threading support
- **AsyncIO** — available via community `.tox` components
- **[tdPyEnvManager](https://docs.derivative.ca/Experimental:Palette:tdPyEnvManager)** — includes thread manager for third-party libraries

## See Also

- [.ai/skills/td-common-mistakes.md](.ai/skills/td-common-mistakes.md) — Mistake #8: Threading with TD objects
- [.ai/skills/td-delayed-calls.md](.ai/skills/td-delayed-calls.md) — `run()` for frame-delayed execution
- [.ai/skills/td-python-environment.md](.ai/skills/td-python-environment.md) — External modules and env setup
- [.ai/skills/td-threaded-inference-optimization.md](.ai/skills/td-threaded-inference-optimization.md)'s "Round 3" — a real crash from this exact rule: a helper method (`_par_or_default()`) that was always safe from its usual main-thread call sites became a TD-object-access-from-a-thread violation the moment a new `run_inference()` override called it from the ONNX inference manager's worker thread. The lesson generalizes beyond ONNX: a helper's thread-safety depends on where it's called from, not on what it does — audit every transitive call a background-thread method makes, don't assume a helper is safe just because it's safe elsewhere.
