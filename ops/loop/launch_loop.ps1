param(
  [ValidateSet("dry", "live")][string]$Mode = "dry",
  [int]$Regressions = 0,
  [switch]$Hang,
  [string]$Cfg = ""
)
$ErrorActionPreference = "Stop"
$py = "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe"
$root = "C:\LegionWallpaper"
$ctl = "$root\ops\loop\control"
$ahk = "C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe"
$bridge = "$root\ops\loop\claude_gui_bridge.ahk"
$ctrl = "$root\ops\loop\loop_controller.py"
$stub = "$root\ops\loop\claude_stub.py"
$env:GEMINI_API_KEY = [Environment]::GetEnvironmentVariable("GEMINI_API_KEY", "User")
if (-not $Cfg) { $Cfg = if ($Mode -eq "live") { "$root\ops\loop\config.json" } else { "$root\ops\loop\config.dry.json" } }

New-Item -ItemType Directory -Force $ctl | Out-Null
# pre-clean stale sentinels so a prior run's STOP cannot early-kill this one
"STOP", "gemini.ready", "typed.flag", "claude.done", "cycle.txt" | ForEach-Object {
  Remove-Item "$ctl\$_" -Force -ErrorAction SilentlyContinue
}
# Kill ONLY THIS repo's bridge instances (cmdline-scoped). A bare AutoHotkey64
# kill would murder the sibling Riot Commander loop's bridge mid-run; RC holds
# the mirror-image guard (RC commit 81636382). taskkill per repo rule.
Get-CimInstance Win32_Process -Filter "Name='AutoHotkey64.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like "*LegionWallpaper\ops\loop*" } |
  ForEach-Object { & taskkill /F /PID $_.ProcessId | Out-Null }
Start-Sleep -Milliseconds 300

if ($Mode -eq "dry") {
  $sa = @("`"$stub`"")
  if ($Regressions) { $sa += "--regressions"; $sa += "1" }
  if ($Hang) { $sa += "--hang" }
  Start-Process $py -ArgumentList $sa -WorkingDirectory $root
  Write-Host "dry: claude_stub launched (regress=$Regressions hang=$($Hang.IsPresent))"
}
else {
  if (-not (Test-Path $bridge)) {
    Write-Error "live mode unavailable: $bridge missing"
    exit 1
  }
  # STRICT pid-bind: exactly ONE claude window whose title EQUALS the config
  # claude_window_title ("Image"). Zero or ambiguous = refuse to arm; the
  # bridge itself aborts on a missing pid (no title fallback, RC 81636382).
  $title = (Get-Content $Cfg -Raw | ConvertFrom-Json).claude_window_title
  $wins = @(Get-Process claude -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -eq $title })
  if ($wins.Count -ne 1) {
    $seen = (Get-Process claude -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | ForEach-Object { $_.MainWindowTitle }) -join " | "
    Write-Error "need exactly ONE claude window titled '$title' (found $($wins.Count)); titles seen: [$seen]"
    exit 1
  }
  Set-Content "$ctl\target_pid.txt" -Value $wins[0].Id -Encoding ascii
  Set-Content "$ctl\ahk_mode.txt" -Value "live" -Encoding ascii
  Start-Process $ahk -ArgumentList "`"$bridge`""
  Write-Host "live: AHK bridge -> claude pid $($wins[0].Id) title '$title'"
}
Start-Process $py -ArgumentList "`"$ctrl`"", "`"$Cfg`"" -WorkingDirectory $root -WindowStyle Hidden
Write-Host "controller launched cfg=$(Split-Path $Cfg -Leaf)"
Write-Host "control dir: $ctl"
Write-Host "abort: create $ctl\STOP   |   live log: $ctl\controller.log"
