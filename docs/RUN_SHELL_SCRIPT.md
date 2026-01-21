## Run a shell script on a thread

```python
# https://docs.python.org/3/library/subprocess.html#subprocess.Popen

import threading
import subprocess
from subprocess import Popen, PIPE, STDOUT
import system_util

def run_script():
    # Start the subprocess and specify stdout and stderr to be piped
    p = Popen(['serve-all.cmd'], cwd='www\\scripts', stdout=PIPE, stderr=STDOUT, shell=True, text=True, bufsize=1)

    # Use a loop to read the output line by line as it becomes available
    for line in p.stdout:
      print(line, end='')  # Print each line of the output

    p.stdout.close()  # Close the stdout stream
    p.wait()  # Wait for the subprocess to exit

# Create and start a thread to run the run_script function
thread = threading.Thread(target=run_script)
thread.start()

# open a browser window at current ip address
# get ip address
ipAddr = system_util.get_ip_address()
system_util.open_url("http://" + ipAddr + ":5173/app-store-distributed/index.html")
```