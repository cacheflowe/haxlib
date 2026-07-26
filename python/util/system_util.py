import os
import sys
import socket
from datetime import datetime
import td

def project_folder():
	return td.project.folder

def get_ip_address():
	hostname = socket.gethostname()
	IPAddr = socket.gethostbyname(hostname)
	return IPAddr

def open_url(url):
	os.system("start " + url)

def print_sys_paths():
	# sys.path is where python looks for modules
	for path in sys.path:
		print('- ' + path)
		
def system_time():
	current_time = datetime.now()
	formatted_time = current_time.strftime("%H:%M:%S")
	return formatted_time

def print_python_info():
	print(f'Python version: {sys.version}')
	print(f'Python executable: {sys.executable}')
	print(f'Python sys.path:')
	for path in sys.path:
		print(f'  - {path}')

def print_numpy_info():
	try:
		import numpy as np
		print(f'numpy version: {np.__version__}')
		print(f'numpy location: {np.__file__}')
	except ImportError:
		print('numpy is not installed.')

def print_pytorch_info():
	try:
		import torch
		print(f'torch version: {torch.__version__}')
		print(f'torch location: {torch.__file__}')
	except ImportError:
		print('torch is not installed.')