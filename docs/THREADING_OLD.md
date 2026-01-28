## Threading examples

Threading in action:
- JoystickToMouse.tox
- PythonWebServer.tox
- AppStore start webserver cmd 
- onnx_inference_manager.py
- Powermate.py

Threadng concepts:
- Threaded results need to end up on the main thread to interact with TouchDesigner nodes
  - This can be w/an Execute DAT calling a method every frame to check for results from a thread
  - Or w/callbacks that use `run()` to schedule code on the main thread?
- Possible routes for advanced threading
  - Python thread objects 
    - locks/queues/events
  - TD py thread manager
  - Aysncio.tox


Threading:
```python
import queue
import threading
import os

class PythonWebServer:
	def __init__(self, ownerComp):
		self.status_queue = queue.Queue() 

	def StartServer(self):
		self.thread = threading.Thread(target=self.StartServerThread)
		self.thread.daemon = True  # Set as daemon thread
		self.thread.start()

	def CheckServerActive(self):
		"""Callback function is executed on the main thread, called by DAT execute every frame."""
		try:
				result = self.status_queue.get(block=False) # non-blocking get
				# print("Result received: {}".format(result))
				self.is_active = result[0]
		except queue.Empty:
				pass # queue is empty nothing to do.
		return
	
	def SetActiveStatus(self, active):
		self.status_queue.put(active)

	def StopServer(self):
		if self.httpd is None:
			print('[PythonWebServer] No server to stop!')
			self.SetActiveStatus([False, 'Stopped'])
			return

		self.stopThread = threading.Thread(target=self.StopServerThread)
		self.stopThread.start()
		# run("parent().SetActive(0)", fromOP=me, delayFrames=1)

	def StopServerThread(self):
		# clean up
		self.thread.join()
		self.shutdown_event.set()
		# self.stopThread.join()
```
