"""
A simple network scanner with no external dependencies
Uses standard ping commands to detect devices on the network
"""

import threading
import subprocess
import ipaddress
import time
import concurrent.futures
import socket
import platform
import sys
import os

class SimpleNetworkScanner:
    def __init__(self, network_range, max_threads=50):
        self.network_range = network_range
        self.devices = []
        self.scan_complete = False
        self.progress = 0
        self.total_ips = 0
        self.max_threads = max_threads
        self.lock = threading.Lock()
        # Determine the ping command based on operating system
        self.ping_cmd = "ping -n 1 -w 300" if platform.system().lower() == "windows" else "ping -c 1 -W 1"

    def ping_ip(self, ip):
        """Ping a single IP address and check if it responds"""
        ip_str = str(ip)
        
        try:
            # Build the ping command
            cmd = f"{self.ping_cmd} {ip_str}"

            # Run the ping command and capture output
            # Using subprocess with DEVNULL to hide output
            result = subprocess.run(
                cmd, 
                shell=True, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                timeout=1  # Timeout after 1 second
            )
            
            # Check if ping was successful (return code 0)
            if result.returncode == 0:
                # Try to get hostname
                hostname = "Unknown"
                try:
                    hostname = socket.gethostbyaddr(ip_str)[0]
                except (socket.herror, socket.gaierror):
                    pass
                
                # Add to the list of active devices
                device_info = {
                    'ip': ip_str,
                    'hostname': hostname
                }
                
                # Thread-safe update of shared resources
                with self.lock:
                    self.devices.append(device_info)
                    print(f"Found device: {ip_str} - {hostname}")
            
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            # Ping timed out or other error, consider the host as down
            pass
        except Exception as e:
            # General error handling
            with self.lock:
                print(f"Error checking {ip_str}: {str(e)}")
        
        # Update progress counter (thread-safe)
        with self.lock:
            self.progress += 1

    def scan_network(self):
        """Scans the network for devices using ping"""
        try:
            network = ipaddress.ip_network(self.network_range)
            
            # Skip network address and broadcast address
            ip_list = [ip for ip in network 
                if ip != network.network_address and ip != network.broadcast_address]
            
            self.total_ips = len(ip_list)
            
        except ValueError:
            print("Invalid network range. Please use CIDR notation (e.g., 192.168.1.0/24)")
            self.scan_complete = True
            return

        # Use ThreadPoolExecutor for parallel scanning
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            # Submit all IP scanning tasks
            futures = [executor.submit(self.ping_ip, ip) for ip in ip_list]
            
            # Wait for all tasks to complete
            concurrent.futures.wait(futures)
        
        self.scan_complete = True

    def run_scan_in_thread(self):
        """Runs the network scan in a separate thread."""
        thread = threading.Thread(target=self.scan_network)
        thread.daemon = True
        thread.start()
        return thread

    def print_results(self):
        """Prints the scan results in a simple text format"""
        # Wait for scan to complete with feedback
        while not self.scan_complete:
            if self.total_ips > 0:
                percent = int((self.progress / self.total_ips) * 100)
                print(f"Scanning network... {percent}% complete ({self.progress}/{self.total_ips})", end='\r')
            else:
                print("Scanning network... Please wait.", end='\r')
            time.sleep(0.5)
        
        print("\nScan complete.                                           ")

        if not self.devices:
            print("No devices found on the network.")
        else:
            # Sort devices by IP for better presentation
            sorted_devices = sorted(self.devices, key=lambda d: self.ip_to_int(d['ip']))
            
            # Print header
            print("\n{:<15} {:<40}".format("IP Address", "Hostname"))
            print("-" * 55)
            
            # Print each device
            for device in sorted_devices:
                print("{:<15} {:<40}".format(
                    device['ip'],
                    device.get('hostname', 'Unknown')
                ))
            
            print(f"\nTotal devices found: {len(self.devices)}")
    
    def ip_to_int(self, ip_str):
        """Convert IP string to integer for sorting"""
        try:
            return int(ipaddress.IPv4Address(ip_str))
        except:
            return 0

def main():
    # Get network range from command line argument or use default
    network_range = '192.168.1.0/24'
    if len(sys.argv) > 1:
        network_range = sys.argv[1]
    
    print(f"Starting network scan on {network_range}")
    
    scanner = SimpleNetworkScanner(network_range)
    scanner.run_scan_in_thread()
    scanner.print_results()

if __name__ == "__main__":
    main()
