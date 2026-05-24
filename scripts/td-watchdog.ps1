<#
.SYNOPSIS
    TouchDesigner system health watchdog — live CLI dashboard.
    Monitors GPU temp, NVDisplay handle leak, nonpaged pool, CPU thermal
    throttling, TD process health, and GPU driver events.
    Built from months of crash forensics on an ASUS ROG Zephyrus M16
    (i9-13900H + RTX 4090 Laptop GPU + Intel Iris Xe, Optimus).

.PARAMETER IntervalSeconds
    Seconds between checks. Default 30.

.PARAMETER MaxNVDisplayHandles
    NVDisplay.Container handle threshold — kills the user-session process
    when exceeded. The parent service respawns it. Default 10000.

.PARAMETER GpuWarnTemp
    GPU temperature (C) to show a warning. Default 75.

.PARAMETER GpuCriticalTemp
    GPU temperature (C) to show critical alert. Default 85.

.EXAMPLE
    .\td-watchdog.ps1
    .\td-watchdog.ps1 -IntervalSeconds 15 -GpuWarnTemp 70
    .\td-watchdog.ps1 -IntervalSeconds 15 -GpuWarnTemp 70 -MaxNVDisplayHandles 5000
#>

param(
    [int]$IntervalSeconds = 30,
    [int]$MaxNVDisplayHandles = 10000,
    [int]$GpuWarnTemp = 75,
    [int]$GpuCriticalTemp = 85
)

# ── Helpers ──────────────────────────────────────────────────────────────

$logFile = Join-Path $PSScriptRoot "td-watchdog.log"
$hasNvidiaSmi = $null -ne (Get-Command nvidia-smi -ErrorAction SilentlyContinue)

function Write-Log {
    param([string]$Message)
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Add-Content -Path $logFile -Value $line
}

function Write-Color {
    param([string]$Text, [string]$Color = 'White')
    Write-Host $Text -ForegroundColor $Color -NoNewline
}

function Get-Bar {
    param([int]$Value, [int]$Max, [int]$Width = 20)
    $filled = [math]::Min($Width, [math]::Max(0, [math]::Round($Value / [math]::Max(1, $Max) * $Width)))
    $empty = $Width - $filled
    "[" + ("#" * $filled) + ("-" * $empty) + "]"
}

function Get-TempColor {
    param([int]$Temp)
    if ($Temp -ge $GpuCriticalTemp) { 'Red' }
    elseif ($Temp -ge $GpuWarnTemp) { 'Yellow' }
    else { 'Green' }
}

function Get-PoolColor {
    param([int]$PoolMB)
    if ($PoolMB -ge 3000) { 'Red' }
    elseif ($PoolMB -ge 2000) { 'Yellow' }
    else { 'Green' }
}

# ── Startup banner ──────────────────────────────────────────────────────

$startTime = Get-Date
Write-Log "Watchdog started. Interval=${IntervalSeconds}s NVDisplayMax=$MaxNVDisplayHandles GpuWarn=$GpuWarnTemp GpuCrit=$GpuCriticalTemp"

# Count baseline thermal throttle events
$baselineThrottles = (Get-WinEvent -FilterHashtable @{LogName='System'; Id=37; StartTime=(Get-Date).AddDays(-1)} -MaxEvents 500 -ErrorAction SilentlyContinue | Measure-Object).Count
$baselineTDR = (Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='nvlddmkm'; StartTime=(Get-Date).AddDays(-1)} -MaxEvents 100 -ErrorAction SilentlyContinue | Measure-Object).Count
$baselineTDCrash = (Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1000; StartTime=(Get-Date).AddDays(-1)} -MaxEvents 500 -ErrorAction SilentlyContinue | Where-Object { $_.Message -match 'TouchDesigner' } | Measure-Object).Count
$baselineTDHang = (Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1002; StartTime=(Get-Date).AddDays(-1)} -MaxEvents 500 -ErrorAction SilentlyContinue | Where-Object { $_.Message -match 'TouchDesigner' } | Measure-Object).Count
$baselineWHEA = (Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-WHEA-Logger'; StartTime=(Get-Date).AddDays(-1)} -MaxEvents 100 -ErrorAction SilentlyContinue | Measure-Object).Count

# Track previous values for delta detection
$prevThrottles = $baselineThrottles
$prevTDR = $baselineTDR
$prevTDCrash = $baselineTDCrash
$prevTDHang = $baselineTDHang
$prevWHEA = $baselineWHEA
$alerts = @()

# Rolling timeline history (last N readings)
$historyMax = 20
$history = [System.Collections.ArrayList]@()

# ── Main loop ───────────────────────────────────────────────────────────

while ($true) {
    $now = Get-Date
    $ts = $now.ToString('HH:mm:ss')
    $uptime = (New-TimeSpan -Start (Get-CimInstance Win32_OperatingSystem).LastBootUpTime -End $now)
    $uptimeStr = "{0}h {1}m" -f [math]::Floor($uptime.TotalHours), $uptime.Minutes
    $watchdogRuntime = (New-TimeSpan -Start $startTime -End $now)
    $runtimeStr = "{0}h {1}m" -f [math]::Floor($watchdogRuntime.TotalHours), $watchdogRuntime.Minutes

    # ── Gather data ─────────────────────────────────────────────────────

    # GPU
    $gpuTemp = 0; $gpuUtil = 0; $gpuMemUtil = 0; $gpuPower = 0; $gpuDisplayActive = "?"
    if ($hasNvidiaSmi) {
        $smiOut = nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,utilization.memory,power.draw,display_active --format=csv,noheader,nounits 2>$null
        if ($smiOut) {
            $parts = $smiOut -split ',\s*'
            $gpuTemp = [int]$parts[0]
            $gpuUtil = [int]$parts[1]
            $gpuMemUtil = [int]$parts[2]
            $gpuPower = [math]::Round([double]$parts[3], 1)
            $gpuDisplayActive = $parts[4].Trim()
        }
    }

    # NVDisplay handles
    $nvProcs = Get-CimInstance Win32_Process -Filter "Name='NVDisplay.Container.exe'" -ErrorAction SilentlyContinue
    $nvService = $nvProcs | Where-Object { $_.SessionId -eq 0 } | Select-Object -First 1
    $nvUser = $nvProcs | Where-Object { $_.SessionId -ne 0 } | Select-Object -First 1
    $nvServiceHandles = if ($nvService) { $nvService.HandleCount } else { 0 }
    $nvUserHandles = if ($nvUser) { $nvUser.HandleCount } else { 0 }
    $nvUserHours = if ($nvUser -and $nvUser.CreationDate) { [math]::Round(($now - $nvUser.CreationDate).TotalHours, 1) } else { 0 }
    $nvHandleRate = if ($nvUserHours -gt 0) { [math]::Round($nvUserHandles / $nvUserHours) } else { 0 }

    # Nonpaged pool
    $poolBytes = (Get-Counter '\Memory\Pool Nonpaged Bytes' -ErrorAction SilentlyContinue).CounterSamples[0].CookedValue
    $poolMB = [math]::Round($poolBytes / 1MB)

    # RAM
    $osInfo = Get-CimInstance Win32_OperatingSystem
    $freeRAM = [math]::Round($osInfo.FreePhysicalMemory / 1MB, 1)
    $totalRAM = [math]::Round($osInfo.TotalVisibleMemorySize / 1MB)
    $usedRAM = [math]::Round($totalRAM - $freeRAM, 1)

    # TD process
    $tdProc = Get-Process -Name "TouchDesigner" -ErrorAction SilentlyContinue | Select-Object -First 1
    $tdStatus = "NOT RUNNING"
    $tdStatusColor = "DarkGray"
    $tdHandles = 0; $tdThreads = 0; $tdWS = 0; $tdSuspended = 0
    if ($tdProc) {
        $tdHandles = $tdProc.HandleCount
        $tdThreads = $tdProc.Threads.Count
        $tdWS = [math]::Round($tdProc.WorkingSet64 / 1MB)
        $tdSuspended = ($tdProc.Threads | Where-Object { $_.WaitReason -eq 'Suspended' } | Measure-Object).Count
        if (-not $tdProc.Responding) {
            $tdStatus = "FROZEN"
            $tdStatusColor = "Red"
        } elseif ($tdSuspended -gt ($tdThreads - 2)) {
            $tdStatus = "HUNG?"
            $tdStatusColor = "Yellow"
        } else {
            $tdStatus = "OK"
            $tdStatusColor = "Green"
        }
    }

    # Event counts (last 24h)
    $throttleEvents = Get-WinEvent -FilterHashtable @{LogName='System'; Id=37; StartTime=$now.AddDays(-1)} -MaxEvents 500 -ErrorAction SilentlyContinue
    $curThrottles = ($throttleEvents | Measure-Object).Count
    $lastThrottleTime = if ($throttleEvents) { $throttleEvents[0].TimeCreated.ToString('HH:mm:ss') } else { $null }
    $curTDR = (Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='nvlddmkm'; StartTime=$now.AddDays(-1)} -MaxEvents 100 -ErrorAction SilentlyContinue | Measure-Object).Count
    $curTDCrash = (Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1000; StartTime=$now.AddDays(-1)} -MaxEvents 500 -ErrorAction SilentlyContinue | Where-Object { $_.Message -match 'TouchDesigner' } | Measure-Object).Count
    $curTDHang = (Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1002; StartTime=$now.AddDays(-1)} -MaxEvents 500 -ErrorAction SilentlyContinue | Where-Object { $_.Message -match 'TouchDesigner' } | Measure-Object).Count
    $curWHEA = (Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-WHEA-Logger'; StartTime=$now.AddDays(-1)} -MaxEvents 100 -ErrorAction SilentlyContinue | Measure-Object).Count

    # ── Detect new events ───────────────────────────────────────────────

    $alerts = @()

    if ($curThrottles -gt $prevThrottles) {
        $delta = $curThrottles - $prevThrottles
        $msg = "CPU THERMAL THROTTLE x$delta"
        $alerts += $msg
        Write-Log "ALERT: $msg"
    }
    if ($curTDR -gt $prevTDR) {
        $msg = "GPU TDR (nvlddmkm) DETECTED"
        $alerts += $msg
        Write-Log "ALERT: $msg"
    }
    if ($curTDCrash -gt $prevTDCrash) {
        $msg = "TD CRASH (APPCRASH) DETECTED"
        $alerts += $msg
        Write-Log "ALERT: $msg"
    }
    if ($curTDHang -gt $prevTDHang) {
        $msg = "TD HANG (AppHangB1) DETECTED"
        $alerts += $msg
        Write-Log "ALERT: $msg"
    }
    if ($curWHEA -gt $prevWHEA) {
        $msg = "WHEA HARDWARE ERROR DETECTED"
        $alerts += $msg
        Write-Log "ALERT: $msg"
    }
    if ($gpuTemp -ge $GpuCriticalTemp) {
        $msg = "GPU CRITICAL: ${gpuTemp}C"
        $alerts += $msg
        Write-Log "ALERT: $msg"
    }
    if ($tdProc -and -not $tdProc.Responding) {
        $msg = "TD IS FROZEN (PID $($tdProc.Id))"
        $alerts += $msg
        Write-Log "ALERT: $msg (Threads: $tdThreads, Suspended: $tdSuspended, Handles: $tdHandles)"
    }

    $prevThrottles = $curThrottles
    $prevTDR = $curTDR
    $prevTDCrash = $curTDCrash
    $prevTDHang = $curTDHang
    $prevWHEA = $curWHEA

    # ── Record history ───────────────────────────────────────────────

    $entry = [PSCustomObject]@{
        Time = $ts
        GPU = $gpuTemp
        Pool = $poolMB
        NVH = $nvUserHandles
        TD = $tdStatus
        Thr = $curThrottles
        Alerts = if ($alerts.Count -gt 0) { $alerts -join '; ' } else { '' }
    }
    [void]$history.Add($entry)
    if ($history.Count -gt $historyMax) { $history.RemoveAt(0) }

    # ── NVDisplay handle kill ───────────────────────────────────────────

    $nvKilled = $false
    if ($nvUser -and $nvUserHandles -gt $MaxNVDisplayHandles) {
        try {
            Stop-Process -Id $nvUser.ProcessId -Force -ErrorAction Stop
            $nvKilled = $true
            Write-Log "KILL NVDisplay PID $($nvUser.ProcessId) handles=$nvUserHandles (threshold=$MaxNVDisplayHandles)"
        } catch {
            Write-Log "KILL FAILED NVDisplay PID $($nvUser.ProcessId): $_"
        }
    }

    # ── Render dashboard ────────────────────────────────────────────────

    Clear-Host

    # Header
    Write-Host "  TD WATCHDOG " -BackgroundColor DarkBlue -ForegroundColor White -NoNewline
    Write-Host "  $ts  |  Uptime: $uptimeStr  |  Monitoring: $runtimeStr  |  Log: td-watchdog.log" -ForegroundColor DarkGray
    Write-Host ""

    # Alerts banner
    if ($alerts.Count -gt 0) {
        Write-Host " !! ALERTS !! " -BackgroundColor Red -ForegroundColor White
        foreach ($a in $alerts) {
            Write-Host "  >> $a" -ForegroundColor Red
        }
        Write-Host ""
    }

    # TouchDesigner
    Write-Host "  TOUCHDESIGNER" -ForegroundColor White
    Write-Color "    Status: "; Write-Color $tdStatus $tdStatusColor; Write-Host ""
    if ($tdProc) {
        Write-Host "    PID: $($tdProc.Id)  |  Threads: $tdThreads ($tdSuspended suspended)  |  Handles: $tdHandles  |  RAM: ${tdWS} MB" -ForegroundColor Gray
    }
    Write-Host ""

    # GPU
    Write-Host "  GPU" -ForegroundColor White
    $tempColor = Get-TempColor $gpuTemp
    $tempBar = Get-Bar $gpuTemp 100 15
    Write-Color "    Temp:  "; Write-Color "${gpuTemp}C " $tempColor; Write-Color $tempBar $tempColor; Write-Host ""
    $utilBar = Get-Bar $gpuUtil 100 15
    Write-Host "    Load:  ${gpuUtil}% $utilBar  |  VRAM: ${gpuMemUtil}%  |  Power: ${gpuPower}W" -ForegroundColor Gray
    $dispColor = if ($gpuDisplayActive -eq 'Enabled') { 'Green' } else { 'Yellow' }
    Write-Color "    Display: "; Write-Color $gpuDisplayActive $dispColor; Write-Host ""
    Write-Host ""

    # NVDisplay
    Write-Host "  NVDISPLAY HANDLES" -ForegroundColor White
    $nvPct = if ($MaxNVDisplayHandles -gt 0) { [math]::Round($nvUserHandles / $MaxNVDisplayHandles * 100) } else { 0 }
    $nvColor = if ($nvPct -gt 70) { 'Yellow' } elseif ($nvPct -gt 100) { 'Red' } else { 'Green' }
    $nvBar = Get-Bar $nvUserHandles $MaxNVDisplayHandles 15
    Write-Color "    User:  "; Write-Color "$nvUserHandles " $nvColor; Write-Color $nvBar $nvColor
    Write-Host "  ($nvPct% of $MaxNVDisplayHandles)  |  Rate: ~${nvHandleRate}/hr  |  Age: ${nvUserHours}h" -ForegroundColor Gray
    Write-Host "    Service: $nvServiceHandles" -ForegroundColor Gray
    if ($nvKilled) {
        Write-Host "    >> KILLED user-session process (service will respawn)" -ForegroundColor Red
    }
    Write-Host ""

    # Memory
    Write-Host "  MEMORY" -ForegroundColor White
    $poolColor = Get-PoolColor $poolMB
    $poolBar = Get-Bar $poolMB 4000 15
    Write-Color "    Nonpaged Pool: "; Write-Color "${poolMB} MB " $poolColor; Write-Color $poolBar $poolColor; Write-Host ""
    $ramBar = Get-Bar $usedRAM $totalRAM 15
    Write-Host "    RAM: ${usedRAM}/${totalRAM} GB $ramBar" -ForegroundColor Gray
    Write-Host ""

    # Event counters (24h)
    Write-Host "  EVENTS (24h)" -ForegroundColor White
    $tColor = if ($curThrottles -gt 0) { 'Yellow' } else { 'Green' }
    $tdrColor = if ($curTDR -gt 0) { 'Red' } else { 'Green' }
    $crashColor = if ($curTDCrash -gt 0) { 'Red' } else { 'Green' }
    $hangColor = if ($curTDHang -gt 0) { 'Yellow' } else { 'Green' }
    $wheaColor = if ($curWHEA -gt 0) { 'Yellow' } else { 'Green' }
    Write-Color "    Thermal Throttles: "; Write-Color "$curThrottles" $tColor
    if ($lastThrottleTime) { Write-Color "  (last: $lastThrottleTime)" 'Yellow' }
    Write-Host ""
    Write-Color "    GPU TDR (nvlddmkm): "; Write-Color "$curTDR" $tdrColor; Write-Host ""
    Write-Color "    TD Crashes: "; Write-Color "$curTDCrash" $crashColor; Write-Host ""
    Write-Color "    TD Hangs: "; Write-Color "$curTDHang" $hangColor; Write-Host ""
    Write-Color "    WHEA Errors: "; Write-Color "$curWHEA" $wheaColor; Write-Host ""
    Write-Host ""

    # Timeline
    Write-Host "  TIMELINE (last $($history.Count) readings)" -ForegroundColor White
    Write-Host "    Time     GPU   Pool    NVDisp  Thr  TD         Alert" -ForegroundColor DarkGray
    foreach ($h in $history) {
        $line = "    {0}  {1,3}C  {2,5}MB  {3,6}  {4,3}  {5,-9}" -f $h.Time, $h.GPU, $h.Pool, $h.NVH, $h.Thr, $h.TD
        $lineColor = 'Gray'
        if ($h.Alerts) {
            $line += "  $($h.Alerts)"
            $lineColor = 'Yellow'
        }
        if ($h.TD -eq 'FROZEN') { $lineColor = 'Red' }
        if ($h.GPU -ge $GpuCriticalTemp) { $lineColor = 'Red' }
        elseif ($h.GPU -ge $GpuWarnTemp -and $lineColor -ne 'Red') { $lineColor = 'Yellow' }
        Write-Host $line -ForegroundColor $lineColor
    }
    Write-Host ""

    # Footer
    Write-Host "  Next check in ${IntervalSeconds}s  |  Ctrl+C to stop" -ForegroundColor DarkGray

    Start-Sleep -Seconds $IntervalSeconds
}
