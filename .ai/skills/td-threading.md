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

- [td-common-mistakes/SKILL.md](../td-common-mistakes/SKILL.md) — Mistake #8: Threading with TD objects
- [td-delayed-function-call/SKILL.md](../td-delayed-function-call/SKILL.md) — `run()` for frame-delayed execution
- [td-python-environment/SKILL.md](../td-python-environment/SKILL.md) — External modules and env setup
