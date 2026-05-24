<#
.SYNOPSIS
    Post-restart diagnostic report -- run once after an unexpected reboot.
    Analyzes event logs to determine WHY the system restarted: BSOD,
    Windows Update, power loss, user-initiated, GPU TDR, thermal, etc.

.PARAMETER HoursBack
    How many hours before the last boot to scan for events. Default 2.

.EXAMPLE
    .\restart-diagnosis.ps1
    .\restart-diagnosis.ps1 -HoursBack 4
#>

param(
    [int]$HoursBack = 2
)

# ── Helpers ──────────────────────────────────────────────────────────────

function Write-Color {
    param([string]$Text, [string]$Color = 'White')
    Write-Host $Text -ForegroundColor $Color -NoNewline
}

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "  $Title" -ForegroundColor White
}

function Write-Finding {
    param([string]$Label, [string]$Value, [string]$Color = 'Gray')
    Write-Host "    $Label " -ForegroundColor DarkGray -NoNewline
    Write-Host $Value -ForegroundColor $Color
}

function Write-Event {
    param($Evt, [int]$MsgLen = 200)
    $msg = $Evt.Message
    if ($msg.Length -gt $MsgLen) { $msg = $msg.Substring(0, $MsgLen) + "..." }
    $msg = $msg -replace "`r`n|`n", " "
    Write-Host "    $($Evt.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss'))  " -ForegroundColor DarkGray -NoNewline
    Write-Host "[$($Evt.ProviderName) #$($Evt.Id)]" -ForegroundColor DarkCyan -NoNewline
    Write-Host "  $msg" -ForegroundColor Gray
}

# ── Boot timeline ────────────────────────────────────────────────────────

$bootTime = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
$now = Get-Date
$uptimeSpan = $now - $bootTime
$scanStart = $bootTime.AddHours(-$HoursBack)

Clear-Host
Write-Host "  RESTART DIAGNOSIS " -BackgroundColor DarkBlue -ForegroundColor White -NoNewline
Write-Host "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor DarkGray
Write-Host ""

Write-Section "BOOT TIMELINE"
Write-Finding "Last Boot:" $bootTime.ToString('yyyy-MM-dd HH:mm:ss (dddd)') 'Cyan'
Write-Finding "Current Uptime:" ("{0}h {1}m" -f [math]::Floor($uptimeSpan.TotalHours), $uptimeSpan.Minutes) 'Green'
Write-Finding "Scanning events:" "$HoursBack hours before boot ($($scanStart.ToString('HH:mm:ss')) - $($bootTime.ToString('HH:mm:ss')))" 'DarkGray'

# ── Shutdown type detection ──────────────────────────────────────────────

Write-Section "SHUTDOWN ANALYSIS"

# Event 1074: Clean shutdown/restart initiated by a process or user
# Event 6006: Event Log service stopped (clean shutdown)
# Event 6008: Unexpected shutdown (dirty)
# Event 41:   Kernel-Power -- system rebooted without clean shutdown (BSOD, power loss)
# Event 109:  Kernel-Power -- system transitioned from connected standby
# Event 1076: Shutdown reason provided after the fact

$shutdownEvents = @()

# Kernel-Power 41 = unexpected reboot (the "big one")
$kp41 = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'; Id=41; StartTime=$scanStart} -MaxEvents 5 -EA SilentlyContinue
if ($kp41) {
    foreach ($e in $kp41) {
        $bugcheck = ""
        if ($e.Properties.Count -ge 5) {
            $bugcheck = "BugcheckCode: 0x{0:X}" -f $e.Properties[0].Value
        }
        $shutdownEvents += [PSCustomObject]@{
            Time = $e.TimeCreated
            Type = "UNEXPECTED REBOOT"
            Color = "Red"
            Detail = "Kernel-Power 41 -- System rebooted without cleanly shutting down. $bugcheck"
            Event = $e
        }
    }
}

# Event 6008 = dirty/unexpected shutdown
$dirty = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='EventLog'; Id=6008; StartTime=$scanStart} -MaxEvents 5 -EA SilentlyContinue
if ($dirty) {
    foreach ($e in $dirty) {
        $shutdownEvents += [PSCustomObject]@{
            Time = $e.TimeCreated
            Type = "DIRTY SHUTDOWN"
            Color = "Red"
            Detail = "Event 6008 -- Previous shutdown was unexpected. $($e.Message -replace "`r`n|`n", ' ')"
            Event = $e
        }
    }
}

# Event 1074 = clean restart/shutdown initiated by process
$clean = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='User32'; Id=1074; StartTime=$scanStart} -MaxEvents 5 -EA SilentlyContinue
if ($clean) {
    foreach ($e in $clean) {
        $msg = $e.Message -replace "`r`n|`n", ' '
        $isUpdate = $msg -match 'Windows Update|wuauserv|svchost.*WindowsUpdate|TiWorker'
        $type = if ($isUpdate) { "WINDOWS UPDATE RESTART" } else { "CLEAN RESTART" }
        $color = if ($isUpdate) { "Yellow" } else { "Green" }
        $shutdownEvents += [PSCustomObject]@{
            Time = $e.TimeCreated
            Type = $type
            Color = $color
            Detail = $msg.Substring(0, [Math]::Min(250, $msg.Length))
            Event = $e
        }
    }
}

# Event 6006 = Event Log service stopped (clean indicator)
$logStop = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='EventLog'; Id=6006; StartTime=$scanStart} -MaxEvents 3 -EA SilentlyContinue

if ($shutdownEvents.Count -eq 0) {
    Write-Finding "Result:" "No shutdown events found in the scan window. May predate the -HoursBack range." 'Yellow'
    Write-Host "    Try: .\restart-diagnosis.ps1 -HoursBack 24" -ForegroundColor DarkGray
} else {
    $shutdownEvents = $shutdownEvents | Sort-Object Time
    foreach ($se in $shutdownEvents) {
        Write-Color "    [$($se.Time.ToString('HH:mm:ss'))] " 'DarkGray'
        Write-Color "$($se.Type)" $se.Color
        Write-Host ""
        Write-Host "      $($se.Detail)" -ForegroundColor Gray
    }
}

if ($logStop) {
    Write-Host ""
    Write-Finding "Event Log stopped:" $logStop[0].TimeCreated.ToString('HH:mm:ss') 'DarkGray'
    Write-Finding "Clean shutdown:" "Yes (log service had time to stop)" 'Green'
} else {
    Write-Host ""
    Write-Finding "Event Log stopped:" "No 6006 event -- shutdown may have been abrupt" 'Yellow'
}

# ── BSOD / Bugcheck ─────────────────────────────────────────────────────

Write-Section "BSOD / BUGCHECK"

$bugchecks = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-WER-SystemErrorReporting'; StartTime=$scanStart} -MaxEvents 5 -EA SilentlyContinue
$minidumps = Get-ChildItem "$env:SystemRoot\Minidump\*.dmp" -EA SilentlyContinue | Where-Object { $_.LastWriteTime -ge $scanStart } | Sort-Object LastWriteTime -Descending
$memDmp = Get-Item "$env:SystemRoot\MEMORY.DMP" -EA SilentlyContinue

if ($bugchecks) {
    foreach ($bc in $bugchecks) {
        Write-Event $bc 300
    }
} else {
    Write-Finding "Bugchecks:" "None in scan window" 'Green'
}

if ($minidumps) {
    Write-Host ""
    Write-Finding "Minidumps found:" "$($minidumps.Count)" 'Yellow'
    foreach ($md in $minidumps | Select-Object -First 3) {
        Write-Finding "  " "$($md.Name)  ($($md.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')),  $([math]::Round($md.Length/1KB)) KB)" 'DarkGray'
    }
}

if ($memDmp -and $memDmp.LastWriteTime -ge $scanStart) {
    Write-Finding "MEMORY.DMP:" "$($memDmp.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'))  $([math]::Round($memDmp.Length/1GB, 2)) GB" 'Red'
}

# ── Windows Update ───────────────────────────────────────────────────────

Write-Section "WINDOWS UPDATE"

$wuEvents = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-WindowsUpdateClient'; StartTime=$scanStart} -MaxEvents 10 -EA SilentlyContinue
$wuInstall = Get-WinEvent -FilterHashtable @{LogName='Setup'; StartTime=$scanStart} -MaxEvents 10 -EA SilentlyContinue

if ($wuEvents) {
    foreach ($wu in $wuEvents | Select-Object -First 5) {
        Write-Event $wu
    }
} else {
    Write-Finding "Update events:" "None in scan window" 'Green'
}

if ($wuInstall) {
    Write-Host ""
    Write-Finding "Setup log:" "$($wuInstall.Count) events around restart" 'Yellow'
    foreach ($si in $wuInstall | Select-Object -First 3) {
        Write-Event $si
    }
}

# ── GPU / Driver events ─────────────────────────────────────────────────

Write-Section "GPU / DRIVER EVENTS"

$tdr = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='nvlddmkm'; StartTime=$scanStart} -MaxEvents 10 -EA SilentlyContinue
$dxgkrnl = Get-WinEvent -FilterHashtable @{LogName='System'; Level=1,2,3; StartTime=$scanStart} -MaxEvents 200 -EA SilentlyContinue | Where-Object { $_.ProviderName -match 'dxgkrnl|display' } | Select-Object -First 5

if ($tdr) {
    Write-Finding "nvlddmkm events:" "$($tdr.Count)" 'Red'
    foreach ($t in $tdr | Select-Object -First 5) {
        Write-Event $t
    }
} else {
    Write-Finding "GPU TDR:" "None" 'Green'
}

if ($dxgkrnl) {
    Write-Host ""
    Write-Finding "dxgkrnl errors:" "$($dxgkrnl.Count)" 'Yellow'
    foreach ($d in $dxgkrnl | Select-Object -First 3) {
        Write-Event $d
    }
}

# ── Thermal / Power ─────────────────────────────────────────────────────

Write-Section "THERMAL / POWER"

$thermals = Get-WinEvent -FilterHashtable @{LogName='System'; Id=37; StartTime=$scanStart} -MaxEvents 50 -EA SilentlyContinue
$kernelPower = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'; StartTime=$scanStart} -MaxEvents 20 -EA SilentlyContinue | Where-Object { $_.Id -ne 41 }

if ($thermals) {
    $groups = $thermals | Group-Object { $_.TimeCreated.ToString('HH:mm:ss') }
    Write-Finding "Thermal throttles:" "$($thermals.Count) events in $($groups.Count) clusters" 'Yellow'
    foreach ($g in $groups | Select-Object -First 5) {
        Write-Finding "  " "$($g.Name) -- x$($g.Count)" 'DarkGray'
    }
} else {
    Write-Finding "Thermal throttles:" "None" 'Green'
}

if ($kernelPower) {
    Write-Host ""
    Write-Finding "Kernel-Power events:" "$($kernelPower.Count) (excl. ID 41)" 'DarkGray'
    foreach ($kp in $kernelPower | Select-Object -First 3) {
        Write-Event $kp 150
    }
}

# ── Application crashes ─────────────────────────────────────────────────

Write-Section "APPLICATION CRASHES (pre-restart)"

$appCrash = Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1000; StartTime=$scanStart} -MaxEvents 20 -EA SilentlyContinue
$appHang = Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1002; StartTime=$scanStart} -MaxEvents 20 -EA SilentlyContinue

$tdCrashes = $appCrash | Where-Object { $_.Message -match 'TouchDesigner|TouchPlayer' }
$tdHangs = $appHang | Where-Object { $_.Message -match 'TouchDesigner|TouchPlayer' }
$otherCrashes = $appCrash | Where-Object { $_.Message -notmatch 'TouchDesigner|TouchPlayer' }

if ($tdCrashes) {
    Write-Finding "TD Crashes:" "$($tdCrashes.Count)" 'Red'
    foreach ($tc in $tdCrashes | Select-Object -First 3) {
        Write-Event $tc 300
    }
} else {
    Write-Finding "TD Crashes:" "None" 'Green'
}

if ($tdHangs) {
    Write-Finding "TD Hangs:" "$($tdHangs.Count)" 'Yellow'
    foreach ($th in $tdHangs | Select-Object -First 3) {
        Write-Event $th 300
    }
} else {
    Write-Finding "TD Hangs:" "None" 'Green'
}

if ($otherCrashes) {
    Write-Host ""
    Write-Finding "Other app crashes:" "$($otherCrashes.Count)" 'DarkGray'
    foreach ($oc in $otherCrashes | Select-Object -First 3) {
        $name = if ($oc.Properties.Count -ge 1) { $oc.Properties[0].Value } else { "?" }
        Write-Host "    $($oc.TimeCreated.ToString('HH:mm:ss'))  $name" -ForegroundColor DarkGray
    }
}

# ── WHEA hardware errors ────────────────────────────────────────────────

Write-Section "HARDWARE ERRORS (WHEA)"

$whea = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-WHEA-Logger'; StartTime=$scanStart} -MaxEvents 20 -EA SilentlyContinue

if ($whea) {
    Write-Finding "WHEA events:" "$($whea.Count)" 'Yellow'
    foreach ($w in $whea | Select-Object -First 5) {
        Write-Event $w
    }
} else {
    Write-Finding "WHEA errors:" "None" 'Green'
}

# ── Disk errors ──────────────────────────────────────────────────────────

Write-Section "DISK ERRORS"

$diskErrors = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='disk'; Level=1,2,3; StartTime=$scanStart} -MaxEvents 20 -EA SilentlyContinue

if ($diskErrors) {
    Write-Finding "Disk events:" "$($diskErrors.Count)" 'Yellow'
    foreach ($de in $diskErrors | Select-Object -First 5) {
        Write-Event $de
    }
} else {
    Write-Finding "Disk errors:" "None" 'Green'
}

# ── Verdict ──────────────────────────────────────────────────────────────

Write-Section "VERDICT"

$verdict = "UNKNOWN"
$verdictColor = "Yellow"
$verdictDetail = "Could not determine restart cause from available events."

# Priority: BSOD > dirty shutdown > GPU TDR > thermal > Windows Update > clean restart
if ($bugchecks -or ($minidumps -and $minidumps.Count -gt 0) -or ($memDmp -and $memDmp.LastWriteTime -ge $scanStart)) {
    $verdict = "BSOD / BUGCHECK"
    $verdictColor = "Red"
    $code = if ($kp41 -and $kp41[0].Properties.Count -ge 1) { "0x{0:X}" -f $kp41[0].Properties[0].Value } else { "unknown" }
    $verdictDetail = "System crashed with a blue screen (bugcheck $code). Check minidumps with WinDbg for details."
} elseif ($kp41) {
    # Unexpected reboot but no bugcheck dump -- likely power loss
    $verdict = "POWER LOSS / HARD RESET"
    $verdictColor = "Red"
    $verdictDetail = "Kernel-Power 41 with no bugcheck dump -- likely power loss, hardware reset, or forced shutdown."
} elseif ($dirty) {
    if ($tdr) {
        $verdict = "GPU TDR CRASH"
        $verdictColor = "Red"
        $verdictDetail = "Dirty shutdown with GPU TDR events -- GPU driver caused system instability."
    } elseif ($thermals -and $thermals.Count -ge 8) {
        $verdict = "THERMAL SHUTDOWN"
        $verdictColor = "Red"
        $verdictDetail = "Dirty shutdown following $($thermals.Count) thermal throttle events -- CPU overheated."
    } else {
        $verdict = "UNEXPECTED SHUTDOWN"
        $verdictColor = "Red"
        $verdictDetail = "Dirty shutdown -- system did not shut down cleanly. Cause unclear from events."
    }
} elseif ($shutdownEvents | Where-Object { $_.Type -eq 'WINDOWS UPDATE RESTART' }) {
    $verdict = "WINDOWS UPDATE"
    $verdictColor = "Yellow"
    $verdictDetail = "System was restarted by Windows Update to apply patches."
} elseif ($shutdownEvents | Where-Object { $_.Type -eq 'CLEAN RESTART' }) {
    $se = $shutdownEvents | Where-Object { $_.Type -eq 'CLEAN RESTART' } | Select-Object -Last 1
    $verdict = "CLEAN RESTART"
    $verdictColor = "Green"
    $verdictDetail = "System was restarted normally. $($se.Detail)"
} elseif (-not $logStop) {
    $verdict = "ABRUPT SHUTDOWN"
    $verdictColor = "Red"
    $verdictDetail = "No clean shutdown events and no Event Log stop -- system was abruptly halted."
}

Write-Host ""
Write-Color "    >> " 'DarkGray'
Write-Color $verdict $verdictColor
Write-Host ""
Write-Host "    $verdictDetail" -ForegroundColor Gray
Write-Host ""

# ── Current system state ─────────────────────────────────────────────────

Write-Section "CURRENT SYSTEM STATE"

$hasNvidiaSmi = $null -ne (Get-Command nvidia-smi -EA SilentlyContinue)
if ($hasNvidiaSmi) {
    $smiOut = nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw --format=csv,noheader,nounits 2>$null
    if ($smiOut) {
        $parts = $smiOut -split ',\s*'
        Write-Finding "GPU:" "$($parts[0])C  |  Load: $($parts[1])%  |  VRAM: $($parts[2])/$($parts[3]) MiB  |  Power: $($parts[4])W" 'Gray'
    }
}

$pool = (Get-Counter '\Memory\Pool Nonpaged Bytes' -EA SilentlyContinue).CounterSamples[0].CookedValue
Write-Finding "Nonpaged Pool:" "$([math]::Round($pool/1MB)) MB" $(if ($pool/1MB -ge 2000) { 'Yellow' } else { 'Green' })

$os = Get-CimInstance Win32_OperatingSystem
$usedGB = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / 1MB, 1)
$totalGB = [math]::Round($os.TotalVisibleMemorySize / 1MB)
Write-Finding "RAM:" "${usedGB}/${totalGB} GB" 'Gray'

$td = Get-Process -Name "TouchDesigner" -EA SilentlyContinue
if ($td) {
    Write-Finding "TouchDesigner:" "Running (PID $($td.Id), $([math]::Round($td.WorkingSet64/1MB)) MB)" 'Green'
} else {
    Write-Finding "TouchDesigner:" "Not running" 'DarkGray'
}

Write-Host ""
Write-Host "  Run with -HoursBack N to scan further back if events were missed." -ForegroundColor DarkGray
Write-Host ""

