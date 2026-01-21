"""
pip install scapy
pip install prettytable
pip install getmac
"""

import threading
import socket
import ipaddress
import time
from getmac import get_mac_address
from prettytable import PrettyTable
import concurrent.futures

class NetworkScanner:
    def __init__(self, network_range, max_threads=50):
        self.network_range = network_range
        self.devices = []
        self.scan_complete = False
        self.progress = 0
        self.total_ips = 0
        self.max_threads = max_threads
        self.lock = threading.Lock()  # For thread-safe updates to shared resources

    def scan_ip(self, ip):
        """Scan a single IP address for activity"""
        ip_str = str(ip)
        
        try:
            # Try to establish a connection to port 80 (common HTTP port)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((ip_str, 80))
            sock.close()
            
            # Alternative check: try to resolve hostname (another sign of an active host)
            is_active = False
            open_ports = []
            
            if result == 0:  # Port 80 is open
                is_active = True
                open_ports.append(80)
            
            # Try additional ports to determine device type
            common_ports = {
                443: "HTTPS",
                554: "RTSP",  # Common for IP cameras
                8000: "IP Camera",  # Hikvision
                8080: "HTTP Alt",  # Common for IP cameras and web servers
                8554: "RTSP Alt",  # Alternative RTSP port
                9000: "IP Camera",  # Some IP camera brands
                1818: "IP Camera",  # Some IP camera brands
                88: "IP Camera",  # FOSCAM IP Camera
                9100: "Printer",
                22: "SSH",
                23: "Telnet",
                25: "SMTP",
                21: "FTP",
                20: "FTP Data",
                445: "SMB",
                139: "NetBIOS",
                3389: "RDP",  # Windows Remote Desktop
                5900: "VNC",  # VNC Remote Access
                6000: "X11",  # X Window System
                1883: "MQTT",  # IoT Devices
                8883: "MQTT SSL",  # Secure MQTT for IoT
                2323: "IoT Telnet",  # Alternative Telnet for IoT
                7547: "CWMP",  # TR-069 - ISP router management
                49152: "UPnP",  # Common UPnP port
                5353: "mDNS",  # Apple/Bonjour services
                631: "IPP",  # Internet Printing Protocol
                515: "LPD",  # Line Printer Daemon
                53: "DNS",  # DNS Server
                67: "DHCP",  # DHCP Server
                68: "DHCP",  # DHCP Client
                161: "SNMP",  # Network Management
                123: "NTP",  # Time Synchronization
                1723: "PPTP",  # VPN
                1701: "L2TP",  # VPN
                500: "IKE",  # VPN
                4500: "IKE NAT",  # VPN
                5060: "SIP",  # VoIP
                5061: "SIP TLS",  # Secure VoIP
                1935: "RTMP",  # Streaming
                8443: "HTTPS Alt",  # Alternative HTTPS
                8081: "HTTP Alt",  # Alternative HTTP
                8181: "HTTP Alt",  # Alternative HTTP
                2000: "Cisco SCCP", # Cisco phones
                5000: "UPnP",  # Universal Plug and Play
                1900: "SSDP",  # Simple Service Discovery Protocol
                32400: "Plex",  # Plex Media Server
                8123: "Home Assistant", # Smart home
                1880: "Node-RED",  # IoT programming platform
                502: "Modbus",  # Industrial control systems
                4433: "IP Camera", # Many IP camera systems
                10000: "Webmin",  # Server administration
                5005: "Sonos",  # Sonos systems
                8009: "Chromecast/Nest", # Google Cast devices
            }
        
            # Check additional ports if we haven't found activity yet or to determine device type
            for port, service in common_ports.items():
                if port != 80:  # Already checked port 80
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(0.1)  # Short timeout for more efficient scanning
                    result = sock.connect_ex((ip_str, port))
                    sock.close()
                    if result == 0:
                        is_active = True
                        open_ports.append(port)
            
            if not is_active:
                # Try ping via socket hostname resolution
                try:
                    socket.gethostbyaddr(ip_str)
                    is_active = True
                except socket.herror:
                    pass
            
            if is_active:
                # If host is active, try to get the MAC address
                mac = get_mac_address(ip=ip_str) or "Unknown"
                
                # Determine device type based on open ports
                device_types = self.determine_device_type(open_ports)
                
                device_info = {
                    'ip': ip_str,
                    'mac': mac,
                    'os': device_types[0],  # Primary type for backward compatibility
                    'device_types': device_types,  # All possible types
                    'vendor': self.guess_vendor(mac),
                    'ports': open_ports,
                }
                
                # Thread-safe update of shared resources
                with self.lock:
                    self.devices.append(device_info)
                    print(f"Found device: {ip_str} - {device_types[0]} - MAC: {mac}")
            
        except Exception as e:
            # Just skip failed attempts without printing errors
            pass
        
        # Update progress counter (thread-safe)
        with self.lock:
            self.progress += 1
    
    def determine_device_type(self, open_ports):
        """Identify all possible device types based on open ports"""
        if not open_ports:
            return ["Unknown"]
            
        # Expanded port signatures
        camera_ports = {554, 8000, 9000, 8554, 4433, 8080, 8081, 8123, 9001, 9002, 10000, 8889, 3702, 88, 1818}
        router_ports = {80, 443, 22, 23, 53, 67, 68, 8080, 8443, 7547, 161, 123, 500, 4500, 1900}
        pc_ports = {139, 445, 3389, 5900, 135, 137, 138, 6000, 6001, 548, 88}
        printer_ports = {9100, 631, 515, 9101, 9102, 9103, 9104, 9105, 9106, 9107}
        media_server_ports = {32400, 1900, 5000, 5353, 8200, 8080, 8096, 8097, 8200, 1935}
        nvr_ports = {8000, 8200, 9000, 37777, 37778, 34567, 554}
        iot_ports = {1883, 8883, 8123, 80, 443, 8080, 8443, 2323, 5000, 1880, 502}
        voip_ports = {5060, 5061, 2000, 10000}
        google_ports = {8009}
        
        # List to collect all possible device types
        device_types = []
        
        # Check for VoIP devices
        if any(port in voip_ports for port in open_ports):
            device_types.append("VoIP Device")
            
        # Check for Google devices
        if any(port in google_ports for port in open_ports):
            device_types.append("Google Device")
            
        # Check for cameras
        if any(port in camera_ports for port in open_ports):
            # Further differentiate between NVR and IP Camera
            if len(set(open_ports).intersection(nvr_ports)) >= 2:
                device_types.append("NVR/DVR")
            device_types.append("IP Camera")
            
        # Check for media servers/streaming devices
        if any(port in media_server_ports for port in open_ports):
            device_types.append("Media Server/Streaming Device")
            
        # Check for routers/network devices
        router_match_count = len(set(open_ports).intersection(router_ports))
        if router_match_count >= 1:
            confidence = "Possible "
            if router_match_count >= 3:
                confidence = ""
            device_types.append(f"{confidence}Router/Network Device")
        
        # Smart Home/IoT devices
        if any(port in iot_ports for port in open_ports):
            if 8123 in open_ports:
                device_types.append("Home Assistant Server")
            if 1880 in open_ports:
                device_types.append("Node-RED Server")
            if 1883 in open_ports or 8883 in open_ports:
                device_types.append("MQTT Device/Broker")
            device_types.append("IoT Device")
            
        # Check for printers
        if any(port in printer_ports for port in open_ports):
            device_types.append("Printer")
            
        # Check for PC/servers with increased specificity
        if any(port in pc_ports for port in open_ports):
            if 3389 in open_ports:
                device_types.append("Windows PC/Server")
            if 5900 in open_ports:
                device_types.append("VNC Server")
            if 548 in open_ports or 88 in open_ports:
                device_types.append("Apple Computer")
            device_types.append("PC/Server")
        
        # Check for NAS devices
        if 445 in open_ports and (80 in open_ports or 443 in open_ports):
            device_types.append("NAS Device")
            
        # Mobile devices often have few open ports but might respond to web ports
        if len(open_ports) <= 2 and (80 in open_ports or 443 in open_ports):
            device_types.append("Mobile/Embedded Device")
            
        # Web servers
        if 80 in open_ports or 443 in open_ports:
            device_types.append("Web-enabled Device")
            
        # If we find SSH/Telnet without many other identifiers, it's likely a managed device
        if (22 in open_ports or 23 in open_ports) and len(device_types) == 0:
            device_types.append("Network Managed Device")
        
        # If no types identified, return Unknown
        if not device_types:
            device_types.append("Unknown Device")
        
        return device_types
    
    def guess_vendor(self, mac):
        """Attempt to identify vendor from MAC address"""
        if mac == "Unknown" or not mac:
            return "Unknown"
            
        # Convert MAC to uppercase for comparison
        mac = mac.upper()
        
        # Very simple MAC address prefix to vendor mapping
        # This could be expanded or replaced with a proper OUI database
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

    def scan_network(self):
        """Scans the network for devices using standard socket connections with thread pool."""
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

        socket.setdefaulttimeout(0.2)  # Set a short timeout for quick scanning
        
        # Use ThreadPoolExecutor for parallel scanning
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
        table.field_names = ["IP", "MAC", "Device Types", "Vendor", "Open Ports"]
        table.max_width["Device Types"] = 40  # Ensure column doesn't get too wide

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
                # Format the ports list for better display
                ports_str = ", ".join(map(str, device['ports'])) if device['ports'] else "None"
                
                # Format the device types list
                if 'device_types' in device:
                    types_str = ", ".join(device['device_types'])
                else:
                    # For backwards compatibility
                    types_str = device['os']
                
                # Truncate long device type lists
                if len(types_str) > 40:
                    types_str = types_str[:37] + "..."
                
                table.add_row([device['ip'], device['mac'], types_str, device['vendor'], ports_str])
            
            print(table)
    
    def ip_to_int(self, ip_str):
        """Convert IP string to integer for sorting"""
        try:
            return int(ipaddress.IPv4Address(ip_str))
        except:
            return 0

if __name__ == "__main__":
    network_range = '192.168.1.0/24'  # Replace with your network range
    scanner = NetworkScanner(network_range)
    scanner.run_scan_in_thread()
    scanner.print_results_table()
