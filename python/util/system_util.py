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