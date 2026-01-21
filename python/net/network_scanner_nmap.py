"""
pip install prettytable
pip install python-nmap
pip install getmac
"""

import threading
import nmap
import ipaddress
import time
import os
import sys
from getmac import get_mac_address
from prettytable import PrettyTable
import concurrent.futures
import socket

# Add Nmap to PATH temporarily
NMAP_PATH = r"C:\Program Files (x86)\Nmap"
if os.path.exists(NMAP_PATH):
    os.environ["PATH"] = NMAP_PATH + os.pathsep + os.environ["PATH"]
    print(f"Added Nmap directory to PATH: {NMAP_PATH}")
else:
    print(f"Warning: Nmap directory not found at {NMAP_PATH}")
    print("Please make sure Nmap is installed or modify the NMAP_PATH variable.")

class NetworkScanner:
    def __init__(self, network_range, max_threads=10):
        self.network_range = network_range
        self.devices = []
        self.scan_complete = False
        self.progress = 0
        self.total_ips = 0
        self.max_threads = max_threads
        self.lock = threading.Lock()  # For thread-safe updates to shared resources
        
        # Check if nmap is available
        try:
            self.nm = nmap.PortScanner()  # Create Nmap scanner instance
        except nmap.PortScannerError as e:
            print(f"Error initializing Nmap: {e}")
            print("Please ensure Nmap is installed and in your PATH.")
            print("You can download Nmap from https://nmap.org/download.html")
            sys.exit(1)

    def scan_ip(self, ip):
        """Scan a single IP address using nmap"""
        ip_str = str(ip)
        
        try:
            # First do a quick ping scan to check if host is up
            ping_scan = self.nm.scan(hosts=ip_str, arguments='-sn')
            host_status = ip_str in ping_scan['scan'] and ping_scan['scan'][ip_str]['status']['state'] == 'up'
            
            if not host_status:
                # Try a TCP connect scan on common ports as fallback
                scan_result = self.nm.scan(hosts=ip_str, arguments='-F -T4')
                host_status = ip_str in scan_result['scan'] and scan_result['scan'][ip_str]['status']['state'] == 'up'
            
            if host_status:
                # Do a more thorough scan with OS detection and service version detection
                self.nm.scan(hosts=ip_str, arguments='-sV -O -T4 --version-intensity 2 --max-os-tries 1')
                
                if ip_str in self.nm.all_hosts():
                    # Get MAC address
                    mac = "Unknown"
                    if 'mac' in self.nm[ip_str]['addresses']:
                        mac = self.nm[ip_str]['addresses']['mac']
                    else:
                        # Fallback to getmac library
                        mac = get_mac_address(ip=ip_str) or "Unknown"
                    
                    # Get OS information
                    os_info = "Unknown"
                    if 'osmatch' in self.nm[ip_str] and len(self.nm[ip_str]['osmatch']) > 0:
                        os_info = self.nm[ip_str]['osmatch'][0]['name']
                    
                    # Get vendor information
                    vendor = "Unknown"
                    if 'vendor' in self.nm[ip_str] and mac in self.nm[ip_str]['vendor']:
                        vendor = self.nm[ip_str]['vendor'][mac]
                    else:
                        # Fallback to our own vendor detection
                        vendor = self.guess_vendor(mac)
                    
                    # Get open ports and services
                    open_ports = []
                    services = {}
                    
                    if 'tcp' in self.nm[ip_str]:
                        for port in self.nm[ip_str]['tcp']:
                            if self.nm[ip_str]['tcp'][port]['state'] == 'open':
                                open_ports.append(port)
                                service_name = self.nm[ip_str]['tcp'][port]['name']
                                product = self.nm[ip_str]['tcp'][port].get('product', '')
                                version = self.nm[ip_str]['tcp'][port].get('version', '')
                                
                                if product or version:
                                    service_info = f"{service_name}"
                                    if product:
                                        service_info += f" ({product}"
                                        if version:
                                            service_info += f" {version}"
                                        service_info += ")"
                                    services[port] = service_info
                                else:
                                    services[port] = service_name
                    
                    # Determine device type
                    device_type = self.determine_device_type(open_ports, os_info, services)
                    
                    device_info = {
                        'ip': ip_str,
                        'mac': mac,
                        'os': os_info,
                        'device_type': device_type,
                        'vendor': vendor,
                        'ports': open_ports,
                        'services': services
                    }
                    
                    # Get hostname if available
                    try:
                        hostname = socket.gethostbyaddr(ip_str)[0]
                        device_info['hostname'] = hostname
                    except:
                        device_info['hostname'] = "Unknown"
                    
                    # Thread-safe update of shared resources
                    with self.lock:
                        self.devices.append(device_info)
                        print(f"Found device: {ip_str} - {device_type} - {os_info}")
            
        except Exception as e:
            # Print error for debugging but continue
            with self.lock:
                print(f"Error scanning {ip_str}: {str(e)}")
        
        # Update progress counter (thread-safe)
        with self.lock:
            self.progress += 1
    
    def determine_device_type(self, open_ports, os_info, services):
        """Determine the device type based on ports, OS, and services"""
        if not open_ports:
            return "Unknown"
        
        # Look for specific service keywords in the service descriptions
        service_str = ' '.join(services.values()).lower()
        
        # Check for camera-related keywords
        camera_keywords = ['camera', 'hikvision', 'dahua', 'axis', 'rtsp', 'onvif', 'ipcam', 'webcam']
        if any(keyword in service_str for keyword in camera_keywords):
            if 'nvr' in service_str or 'dvr' in service_str:
                return "NVR/DVR"
            return "IP Camera"
        
        # Check OS detection results for types of devices
        os_lower = os_info.lower()
        
        # Check for router/switches in OS fingerprint
        if any(keyword in os_lower for keyword in ['router', 'switch', 'firewall', 'mikrotik', 'fortinet', 'pfsense', 'cisco ios']):
            return "Router/Network Device"
            
        # Check for NAS devices
        if any(keyword in os_lower for keyword in ['nas', 'synology', 'qnap', 'freenas', 'truenas']):
            return "NAS Device"
            
        # Check for printers
        if any(keyword in service_str for keyword in ['printer', 'ipp', 'jetdirect', 'cups']):
            return "Printer"
            
        # Check for IoT devices
        if any(keyword in service_str for keyword in ['mqtt', 'iot', 'smart', 'home assistant', 'hass', 'zwave']):
            return "IoT Device"
            
        # Check for media devices
        if any(keyword in service_str for keyword in ['plex', 'dlna', 'roku', 'chromecast', 'apple tv', 'kodi']):
            return "Media Device"
            
        # Check for operating systems
        if 'windows' in os_lower:
            return "Windows PC/Server"
        elif 'mac' in os_lower or 'apple' in os_lower or 'ios' in os_lower:
            return "Apple Device"
        elif 'linux' in os_lower or 'unix' in os_lower:
            return "Linux Device"
        elif 'android' in os_lower:
            return "Android Device"
            
        # Fall back to port-based detection if OS detection failed
        camera_ports = {554, 8000, 9000, 8554, 4433, 8080, 8081, 1818}
        router_ports = {80, 443, 22, 23, 53, 67, 68, 8080, 8443, 7547, 161, 123}
        pc_ports = {139, 445, 3389, 5900, 135, 137, 138}
        printer_ports = {9100, 631, 515}
        
        # Check common port patterns
        if any(port in camera_ports for port in open_ports):
            return "IP Camera"
            
        if len(set(open_ports).intersection(router_ports)) >= 3:
            return "Router/Network Device"
            
        if any(port in printer_ports for port in open_ports):
            return "Printer"
            
        if any(port in pc_ports for port in open_ports):
            return "PC/Server"
            
        # Default for web-enabled devices
        if 80 in open_ports or 443 in open_ports:
            return "Web-enabled Device"
            
        return "Unknown Device"
    
    def scan_network(self):
        """Scans the network for devices using nmap"""
        try:
            network = ipaddress.ip_network(self.network_range)
            
            # Skip network address and broadcast address for larger networks
            if network.num_addresses > 2:
                ip_list = [ip for ip in network 
                    if ip != network.network_address and ip != network.broadcast_address]
            else:
                ip_list = list(network.hosts())
            
            self.total_ips = len(ip_list)
            
        except ValueError:
            print("Invalid network range. Please use CIDR notation (e.g., 192.168.1.0/24)")
            self.scan_complete = True
            return

        # Use ThreadPoolExecutor for parallel scanning
        # Note: Using fewer threads with nmap to prevent system overload
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            # Submit all IP scanning tasks
            futures = [executor.submit(self.scan_ip, ip) for ip in ip_list]
            
            # Wait for all tasks to complete
            concurrent.futures.wait(futures)
        
        self.scan_complete = True

    def run_scan_in_thread(self):
        """Runs the network scan in a separate thread."""
        thread = threading.Thread(target=self.scan_network)
        thread.daemon = True  # Make thread a daemon so it exits when main program exits
        thread.start()
        return thread

    def print_results_table(self):
        """Prints the scan results in a table format."""
        table = PrettyTable()
        table.field_names = ["IP", "Hostname", "MAC", "Device Type", "OS", "Vendor", "Open Ports/Services"]

        # Wait for scan to complete with feedback
        while not self.scan_complete:
            if self.total_ips > 0:
                percent = int((self.progress / self.total_ips) * 100)
                print(f"Scanning network... {percent}% complete ({self.progress}/{self.total_ips})", end='\r')
            else:
                print("Scanning network... Please wait.", end='\r')
            time.sleep(0.5)
        
        print("Scan complete.                                           ")  # Clear the progress line

        if not self.devices:
            print("No devices found on the network.")
        else:
            # Sort devices by IP for better presentation
            sorted_devices = sorted(self.devices, key=lambda d: self.ip_to_int(d['ip']))
            
            for device in sorted_devices:
                # Format the services list
                services_str = ""
                for port in device['ports']:
                    if port in device.get('services', {}):
                        services_str += f"{port}/{device['services'][port]}, "
                    else:
                        services_str += f"{port}, "
                
                services_str = services_str.rstrip(", ") if services_str else "None"
                
                table.add_row([
                    device['ip'], 
                    device.get('hostname', 'Unknown'),
                    device['mac'], 
                    device.get('device_type', 'Unknown'), 
                    device['os'], 
                    device['vendor'], 
                    services_str
                ])
            
            print(table)
    
    def ip_to_int(self, ip_str):
        """Convert IP string to integer for sorting"""
        try:
            return int(ipaddress.IPv4Address(ip_str))
        except:
            return 0
            
    def guess_vendor(self, mac):
        """Attempt to identify vendor from MAC address"""
        if mac == "Unknown" or not mac:
            return "Unknown"
            
        # Convert MAC to uppercase for comparison
        mac = mac.upper()
        
        # Very simple MAC address prefix to vendor mapping
        vendor_prefixes = {
            "00:1A:79": "Cisco",
            "00:1B:63": "Apple",
            "00:16:B6": "Cisco-Linksys",
            "00:50:56": "VMware",
            "00:21:85": "Hikvision",
            "FC:D8:48": "Hikvision",
            "28:57:BE": "Hikvision",
            "C0:56:E3": "Hikvision",
            "44:19:B6": "Dahua",
            "8C:E7:48": "Dahua",
            "BC:32:5F": "Dahua",
            "90:02:A9": "Dahua",
            "00:18:AE": "Axis",
            "AC:CC:8E": "Axis",
        }
        
        # Check if the MAC address starts with any known prefixes
        for prefix, vendor in vendor_prefixes.items():
            if mac.startswith(prefix.replace(":", "")):
                return vendor
                
        return "Unknown"

if __name__ == "__main__":
    network_range = '192.168.1.0/24'  # Replace with your network range
    scanner = NetworkScanner(network_range)
    scanner.run_scan_in_thread()
    scanner.print_results_table()
