import shutil
import subprocess
import threading

_has_nvidia = shutil.which('nvidia-smi') is not None


def print_gpu_temp():
	"""Print GPU temperature. Runs nvidia-smi in a background thread so it never blocks TD."""
	if not _has_nvidia:
		return
	def _query():
		try:
			result = subprocess.run(
				['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader,nounits'],
				capture_output=True, text=True, timeout=2
			)
			temp = float(result.stdout.strip())
			if temp < 80:
				label = 'OK'
			elif temp < 90:
				label = 'WARM'
			elif temp < 95:
				label = 'HOT!'
			else:
				label = 'CRITICAL!'
			print(f'GPU: {temp:.0f}C ({label})')
		except Exception:
			print('GPU: read failed')
	threading.Thread(target=_query, daemon=True).start()
