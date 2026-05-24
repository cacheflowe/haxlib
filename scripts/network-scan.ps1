<#
.SYNOPSIS
    Scans the local network for active devices and prints detailed info.
.DESCRIPTION
    Discovers the local subnet, pings all IPs concurrently, then gathers
    hostname, MAC address, open ports, NetBIOS name, manufacturer (OUI),
    and response time for each responding device.
.EXAMPLE
    .\network-scan.ps1
    .\network-scan.ps1 -Subnet "192.168.1.0/24" -MaxThreads 100
#>

param(
    [string]$Subnet,
    [int]$MaxThreads = 80,
    [int]$PingTimeoutMs = 400,
    [int[]]$PortsToScan = @(22,53,80,443,445,554,3389,5900,8000,8080,8443,8554,9000,9100)
)

# ── Resolve local subnet if not provided ──────────────────────────────
function Get-LocalSubnet {
    $adapter = Get-NetIPConfiguration |
        Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
        Select-Object -First 1

    if (-not $adapter) {
        Write-Error "No active network adapter with a default gateway found."
        exit 1
    }

    $ip     = $adapter.IPv4Address.IPAddress
    $prefix = $adapter.IPv4Address.PrefixLength
    Write-Host "Detected interface : $($adapter.InterfaceAlias)" -ForegroundColor Cyan
    Write-Host "Local IP           : $ip / $prefix" -ForegroundColor Cyan
    Write-Host "Gateway            : $($adapter.IPv4DefaultGateway.NextHop)" -ForegroundColor Cyan

    # Calculate network address
    $ipBytes   = ([System.Net.IPAddress]::Parse($ip)).GetAddressBytes()
    $maskInt   = ([uint32]::MaxValue) -shl (32 - $prefix) -band [uint32]::MaxValue
    $maskBytes = [BitConverter]::GetBytes($maskInt)
    [Array]::Reverse($maskBytes)

    $netBytes = @(0,0,0,0)
    for ($i = 0; $i -lt 4; $i++) { $netBytes[$i] = $ipBytes[$i] -band $maskBytes[$i] }
    $network = ($netBytes -join '.')
    return "$network/$prefix"
}

if (-not $Subnet) { $Subnet = Get-LocalSubnet }
Write-Host "`nScanning subnet    : $Subnet" -ForegroundColor Yellow
Write-Host "Ping timeout       : ${PingTimeoutMs}ms   Threads: $MaxThreads" -ForegroundColor Yellow
Write-Host ("-" * 70)

# ── Build IP list ─────────────────────────────────────────────────────
function Get-IPRange([string]$cidr) {
    $parts   = $cidr -split '/'
    $baseIP  = [System.Net.IPAddress]::Parse($parts[0])
    $prefix  = [int]$parts[1]
    $ipInt   = [BitConverter]::ToUInt32($baseIP.GetAddressBytes()[3..0], 0)
    $maskInt = ([uint32]::MaxValue) -shl (32 - $prefix) -band [uint32]::MaxValue
    $netInt  = $ipInt -band $maskInt
    $bcastInt= $netInt -bor (-bnot $maskInt -band [uint32]::MaxValue)

    $ips = [System.Collections.Generic.List[string]]::new()
    for ($i = $netInt + 1; $i -lt $bcastInt; $i++) {
        $bytes = [BitConverter]::GetBytes([uint32]$i)
        [Array]::Reverse($bytes)
        $ips.Add(([System.Net.IPAddress]::new($bytes)).ToString())
    }
    return $ips
}

$allIPs = Get-IPRange $Subnet
Write-Host "IPs to scan        : $($allIPs.Count)" -ForegroundColor Yellow
Write-Host ""

# ── Phase 1: Parallel ping ───────────────────────────────────────────
Write-Host "Phase 1/3 — Pinging all hosts..." -ForegroundColor Green

$pingResults = $allIPs | ForEach-Object -Parallel {
    $ip = $_
    $timeout = $using:PingTimeoutMs
    try {
        $ping = New-Object System.Net.NetworkInformation.Ping
        $reply = $ping.Send($ip, $timeout)
        if ($reply.Status -eq 'Success') {
            [PSCustomObject]@{
                IP          = $ip
                RoundtripMs = $reply.RoundtripTime
            }
        }
    } catch { }
} -ThrottleLimit $MaxThreads

$aliveIPs = @($pingResults | Where-Object { $_ })
$pingedSet = [System.Collections.Generic.HashSet[string]]::new()
foreach ($r in $aliveIPs) { [void]$pingedSet.Add($r.IP) }
Write-Host "  Found $($aliveIPs.Count) responding host(s).`n" -ForegroundColor Green

# ── Grab ARP table once ──────────────────────────────────────────────
$arpTable = @{}
$arpRaw = & arp -a 2>$null
foreach ($line in $arpRaw) {
    if ($line -match '^\s+([\d\.]+)\s+([\w-]+)\s+(\w+)') {
        $arpIP  = $Matches[1]
        $arpMAC = $Matches[2].ToUpper()
        # Skip multicast (224-239), broadcast, and link-local (169.254)
        $firstOctet = [int]($arpIP -split '\.')[0]
        if ($firstOctet -ge 224 -or $arpIP -eq '255.255.255.255' -or $arpIP.StartsWith('169.254')) { continue }
        if ($arpMAC -eq 'FF-FF-FF-FF-FF-FF') { continue }
        $arpTable[$arpIP] = $arpMAC
    }
}

# ── Merge ARP-only devices (present on network but didn't respond to ping)
$arpOnlyIPs = @()
foreach ($arpIP in $arpTable.Keys) {
    if (-not $pingedSet.Contains($arpIP)) {
        $arpOnlyIPs += [PSCustomObject]@{
            IP          = $arpIP
            RoundtripMs = -1   # sentinel: ARP-only
        }
    }
}
if ($arpOnlyIPs.Count -gt 0) {
    Write-Host "  + $($arpOnlyIPs.Count) additional device(s) found via ARP (no ping response).`n" -ForegroundColor DarkYellow
}
$allAlive = @($aliveIPs) + @($arpOnlyIPs)

# ── OUI lookup (first 3 octets of MAC → manufacturer) ────────────────
# Embedded common OUI prefixes for quick offline lookup
$ouiMap = @{
    "00:50:56"="VMware"; "00:0C:29"="VMware"; "00:15:5D"="Microsoft Hyper-V"
    "B8:27:EB"="Raspberry Pi"; "DC:A6:32"="Raspberry Pi"; "E4:5F:01"="Raspberry Pi"
    "AC:DE:48"="Private"; "00:1A:79"="Epson"
    "00:1B:44"="SanDisk"; "00:25:90"="Super Micro"
    "3C:22:FB"="Apple"; "A4:83:E7"="Apple"; "F0:18:98"="Apple"
    "00:1E:C9"="Dell"; "F8:BC:12"="Dell"; "00:14:22"="Dell"
    "B4:2E:99"="Glenyre"; "00:17:88"="Philips Hue"
    "00:04:4B"="Nvidia"; "48:B0:2D"="Nvidia"
    "D8:3A:DD"="Raspberry Pi"; "28:CD:C1"="Raspberry Pi"
    "2C:CF:67"="Apple"; "64:A2:F9"="Apple"
    "00:0D:B9"="PC Engines"; "00:1C:42"="Parallels"
    "FC:EC:DA"="Ubiquiti"; "78:8A:20"="Ubiquiti"; "24:5A:4C"="Ubiquiti"
    "B0:BE:76"="TP-Link"; "50:C7:BF"="TP-Link"
    "00:18:0A"="Cisco"; "00:1B:2B"="Cisco"
    "00:50:C2"="IEEE Reg Authority"; "44:D9:E7"="Ubiquiti"
    "00:E0:4C"="Realtek"; "52:54:00"="QEMU/KVM"
    "08:00:27"="VirtualBox"; "0A:00:27"="VirtualBox"
    "00:1A:A0"="Dell"; "D4:BE:D9"="Dell"
    "00:23:24"="Asustek"; "74:D0:2B"="Asustek"
    "30:B4:9E"="TP-Link"; "A0:F3:C1"="TP-Link"
    "E8:9F:80"="Belkin"; "94:10:3E"="Belkin"
    "C8:3A:35"="Tenda"; "00:26:18"="Asus"
    "9C:5C:8E"="Intel"; "A4:BB:6D"="Intel"; "3C:A9:F4"="Intel"
    "00:1C:C0"="Intel"; "68:05:CA"="Intel"
    "18:31:BF"="Samsung"; "00:07:AB"="Samsung"
    "D8:9E:F3"="Amazon"; "44:65:0D"="Amazon"
    "30:FD:38"="Google"; "54:60:09"="Google"
    "D0:03:4B"="Apple"; "A8:51:5B"="Apple"
    "00:24:E4"="Cisco"; "00:1D:A2"="Cisco"
}

function Get-Manufacturer([string]$mac) {
    if (-not $mac -or $mac -eq '(none)') { return '' }
    $normalized = ($mac -replace '-',':').ToUpper()
    $prefix = $normalized.Substring(0, 8)
    if ($ouiMap.ContainsKey($prefix)) { return $ouiMap[$prefix] }
    return ''
}

if ($allAlive.Count -eq 0) {
    Write-Host "No devices found. Try increasing -PingTimeoutMs or check firewall settings." -ForegroundColor Red
    exit 0
}

# ── Phase 2: Gather details ──────────────────────────────────────────
Write-Host "Phase 2/3 — Resolving hostnames & MAC addresses..." -ForegroundColor Green

$devices = foreach ($entry in $allAlive) {
    $ip = $entry.IP
    $roundtrip = $entry.RoundtripMs

    # Hostname
    $hostname = ''
    try {
        $dns = [System.Net.Dns]::GetHostEntry($ip)
        $hostname = $dns.HostName
    } catch { }

    # NetBIOS name
    $netbios = ''
    try {
        $nbtResult = & nbtstat -A $ip 2>$null | Select-String '<00>\s+UNIQUE' | Select-Object -First 1
        if ($nbtResult) {
            $netbios = ($nbtResult -replace '^\s+' -split '\s+')[0]
        }
    } catch { }
    
    # MAC from ARP
    $mac = if ($arpTable.ContainsKey($ip)) { $arpTable[$ip] } else { '(none)' }
    $manufacturer = Get-Manufacturer $mac

    [PSCustomObject]@{
        IP           = $ip
        Hostname     = if ($hostname) { $hostname } else { '—' }
        NetBIOS      = if ($netbios) { $netbios } else { '—' }
        MAC          = $mac
        Manufacturer = if ($manufacturer) { $manufacturer } else { '—' }
        RoundtripMs  = $roundtrip
        Source       = if ($roundtrip -ge 0) { 'Ping' } else { 'ARP only' }
        OpenPorts    = ''
    }
}

$devices = @($devices | Sort-Object { [version]$_.IP })
Write-Host "  Done.`n" -ForegroundColor Green

# ── Phase 3: Port scan ───────────────────────────────────────────────
Write-Host "Phase 3/3 — Scanning common ports on live hosts..." -ForegroundColor Green

$portScanJobs = foreach ($dev in $devices) {
    $ip = $dev.IP
    $ports = $PortsToScan
    [PSCustomObject]@{
        IP   = $ip
        Task = [System.Threading.Tasks.Task]::Run([System.Func[object]]{
            $open = [System.Collections.Generic.List[int]]::new()
            foreach ($p in $ports) {
                try {
                    $tcp = New-Object System.Net.Sockets.TcpClient
                    $ar  = $tcp.BeginConnect($ip, $p, $null, $null)
                    $ok  = $ar.AsyncWaitHandle.WaitOne(300, $false)
                    if ($ok -and $tcp.Connected) { $open.Add($p) }
                    $tcp.Close()
                } catch { }
            }
            return ($open -join ', ')
        }.GetNewClosure())
    }
}

foreach ($job in $portScanJobs) {
    $job.Task.Wait()
    $dev = $devices | Where-Object { $_.IP -eq $job.IP }
    if ($dev) { $dev.OpenPorts = $job.Task.Result }
}

Write-Host "  Done.`n" -ForegroundColor Green

# ── Pretty-print results ─────────────────────────────────────────────
Write-Host ("=" * 120) -ForegroundColor Cyan
Write-Host " NETWORK SCAN RESULTS — $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')   Subnet: $Subnet" -ForegroundColor Cyan
Write-Host ("=" * 120) -ForegroundColor Cyan

$portLabels = @{
    22='SSH'; 53='DNS'; 80='HTTP'; 443='HTTPS'; 445='SMB'
    554='RTSP'; 3389='RDP'; 5900='VNC'; 8000='Cam'; 8080='HTTP-Alt'
    8443='HTTPS-Alt'; 8554='RTSP-Alt'; 9000='Cam'; 9100='Print'
}

foreach ($dev in $devices) {
    $color = if ($dev.OpenPorts) { 'White' } else { 'Gray' }
    Write-Host ""
    Write-Host "  $($dev.IP)" -ForegroundColor Yellow -NoNewline
    if ($dev.Source -eq 'ARP only') {
        Write-Host "  [ARP only — no ping response]" -ForegroundColor DarkYellow
    } else {
        Write-Host "  ($($dev.RoundtripMs)ms)" -ForegroundColor DarkGray
    }

    Write-Host "    Hostname     : $($dev.Hostname)" -ForegroundColor $color
    Write-Host "    NetBIOS      : $($dev.NetBIOS)" -ForegroundColor $color
    Write-Host "    MAC          : $($dev.MAC)" -ForegroundColor $color
    Write-Host "    Manufacturer : $($dev.Manufacturer)" -ForegroundColor $color

    if ($dev.OpenPorts) {
        $labeled = ($dev.OpenPorts -split ',\s*') | ForEach-Object {
            $p = [int]$_
            if ($portLabels.ContainsKey($p)) { "$p($($portLabels[$p]))" } else { "$p" }
        }
        Write-Host "    Open Ports   : $($labeled -join '  ')" -ForegroundColor Green
    } else {
        Write-Host "    Open Ports   : (none detected)" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host ("=" * 120) -ForegroundColor Cyan
Write-Host " Total devices found: $($devices.Count)" -ForegroundColor Cyan
Write-Host ("=" * 120) -ForegroundColor Cyan
Write-Host ""
