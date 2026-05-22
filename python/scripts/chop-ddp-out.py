"""
DDP Sender Script CHOP
======================
Reads RGBA pixel data from an upstream CHOP and streams it as DDP to LED
controllers over UDP. No GPU readback — data is already CPU-side.

Setup:
  1. Wire: TOP → TOP to CHOP → this Script CHOP
     TOP to CHOP settings:
        - Alpha: empty
        - Output as single channel set: On
        - Crop: Full Image
  2. Press 'Setup Parameters' to create custom parameters
  3. Set address/port — sender starts on first cook
  4. Enable 'Cook Every Frame' on the CHOP's Common page to send every frame.

Protocol reference: http://www.3waylabs.com/ddp/
"""

import socket
import threading
import time
import numpy as np


# ---------------------------------------------------------------------------
# DDP constants
# ---------------------------------------------------------------------------
_MAX  = 480 * 3   # max bytes per packet
_VER  = 0x40
_PUSH = 0x01
_RGB  = 0x0B


# ---------------------------------------------------------------------------
# DDP Sender
# ---------------------------------------------------------------------------

class DdpSender:
	def __init__(self, address: str, port: int, dest_id: int,
	             pixel_start: int, keepalive: float) -> None:
		self.address     = address
		self.port        = port
		self.dest_id     = dest_id
		self.pixel_start = pixel_start
		self.keepalive   = keepalive

		self._sock: socket.socket | None = None
		self._seq        = 0
		self._last_data: bytes | None = None
		self._last_send  = 0.0
		self._lock       = threading.Lock()
		self._stop       = threading.Event()
		self._thread: threading.Thread | None = None

		self.frames_sent = 0
		self.keepalive_sent = 0
		self.packets_sent = 0
		self.errors = 0

	def start(self) -> None:
		self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024)
		self._stop.clear()
		self._thread = threading.Thread(
			target=self._keepaliveLoop, daemon=True,
			name=f"ddp-{self.address}:{self.port}",
		)
		self._thread.start()

	def stop(self) -> None:
		self._stop.set()
		# No join — thread is daemon=True, exits on its own within keepalive interval
		if self._sock:
			self._sock.close()
			self._sock = None

	def sendFrame(self, rgb: bytes) -> None:
		with self._lock:
			if self._send(rgb):
				self.frames_sent += 1
				self._last_data = rgb
				self._last_send = time.monotonic()

	def _send(self, data: bytes) -> bool:
		if not self._sock:
			return False
		n     = len(data)
		count = (n + _MAX - 1) // _MAX
		base  = self.pixel_start * 3
		ok    = True
		for i in range(count):
			off    = i * _MAX
			ln     = min(_MAX, n - off)
			absoff = base + off
			self._seq = self._seq % 15 + 1
			flags  = _VER | (_PUSH if i == count - 1 else 0)
			hdr    = bytes([
				flags, self._seq, _RGB, self.dest_id,
				(absoff >> 24) & 0xFF, (absoff >> 16) & 0xFF,
				(absoff >> 8)  & 0xFF,  absoff         & 0xFF,
				(ln >> 8) & 0xFF, ln & 0xFF,
			])
			try:
				self._sock.sendto(hdr + data[off:off + ln], (self.address, self.port))
				self.packets_sent += 1
			except OSError:
				self.errors += 1
				ok = False
		return ok

	def _keepaliveLoop(self) -> None:
		while not self._stop.wait(timeout=self.keepalive):
			with self._lock:
				if self._last_data is None:
					continue
				if time.monotonic() - self._last_send < self.keepalive:
					continue
				if self._send(self._last_data):
					self.keepalive_sent += 1
					self._last_send = time.monotonic()


# ---------------------------------------------------------------------------
# Module-level sender instance.
# Thread liveness check detects module reloads (which reset this to None)
# and triggers a clean reinit on the next cook.
# ---------------------------------------------------------------------------
_sender: DdpSender | None = None


# ---------------------------------------------------------------------------
# Script CHOP callbacks
# ---------------------------------------------------------------------------

def onSetupParameters(scriptOp) -> None:
	page = scriptOp.appendCustomPage('DDP')
	page.appendToggle('Active', label='Active')[0].default = True
	page.appendStr('Address', label='Address')[0].default = '127.0.0.1'
	p = page.appendInt('Port', label='Port')[0]
	p.default = 4048
	p.min, p.max = 1, 65535
	p = page.appendInt('Destinationid', label='Destination ID')[0]
	p.default = 1
	p.min, p.max = 1, 255
	p = page.appendInt('Pixelstart', label='Pixel Start')[0]
	p.default = 0
	p.min = 0
	p = page.appendFloat('Keepalive', label='Keepalive (s)')[0]
	p.default = 0.1
	p.min, p.max = 0.01, 2.0
	page.appendPulse('Reinitialize', label='Reinitialize')
	page.appendPulse('Printstats', label='Print Stats')


def onPulse(par) -> None:
	global _sender
	if par.name == 'Reinitialize':
		if _sender:
			_sender.stop()
		_sender = _startSender(par.owner)
	elif par.name == 'Printstats':
		_printStats()


def onCook(scriptOp) -> None:
	global _sender
	try:
		if _sender is None or not _sender._thread.is_alive():
			_sender = None

		if _sender is None or _configChanged(scriptOp, _sender):
			if _sender is not None:
				_sender.stop()
			_sender = _startSender(scriptOp)

		# Write metrics to CHOP output (1 sample per channel)
		scriptOp.clear()
		scriptOp.numSamples = 1
		scriptOp.appendChan('frames_sent')[0] = float(_sender.frames_sent)
		scriptOp.appendChan('packets_sent')[0] = float(_sender.packets_sent)
		scriptOp.appendChan('errors')[0]       = float(_sender.errors)
		scriptOp.appendChan('keepalives')[0]   = float(_sender.keepalive_sent)

		if not scriptOp.par.Active.eval() or not scriptOp.inputs:
			return

		# CHOP input is already CPU-side — no GPU readback
		arr = scriptOp.inputs[0].numpyArray()
		if arr is None or arr.size == 0:
			return

		# arr shape from CHOP numpyArray() is (numChannels, numSamples)
		rgb = (arr[:3, :].T * 255.0).astype(np.uint8)
		_sender.sendFrame(rgb.tobytes())

	except Exception as e:
		print(f'[DDP] error: {e}')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _configChanged(scriptOp, sender: DdpSender) -> bool:
	return (
		sender.address     != scriptOp.par.Address.eval()
		or sender.port     != int(scriptOp.par.Port.eval())
		or sender.dest_id  != int(scriptOp.par.Destinationid.eval())
		or sender.pixel_start != int(scriptOp.par.Pixelstart.eval())
		or sender.keepalive != float(scriptOp.par.Keepalive.eval())
	)


def _startSender(scriptOp) -> DdpSender:
	address   = scriptOp.par.Address.eval()
	port      = int(scriptOp.par.Port.eval())
	dest_id   = int(scriptOp.par.Destinationid.eval())
	px_start  = int(scriptOp.par.Pixelstart.eval())
	keepalive = float(scriptOp.par.Keepalive.eval())
	s = DdpSender(address, port, dest_id, px_start, keepalive)
	s.start()
	print(f'[DDP] Started → {address}:{port}')
	return s


def _printStats() -> None:
	if _sender is None or not _sender._thread.is_alive():
		print('[DDP] no active sender')
		return
	print(f'[DDP] {_sender.address}:{_sender.port}  frames={_sender.frames_sent}  '
	      f'keepalives={_sender.keepalive_sent}  packets={_sender.packets_sent}  errors={_sender.errors}')
