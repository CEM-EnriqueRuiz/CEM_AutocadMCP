# Sets up the AutoCAD MCP server and registers it with the Claude desktop app.
# Run from the repo folder:  powershell -ExecutionPolicy Bypass -File setup_claude.ps1
$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot
# Cemengal: never install into an ACC folder: the .venv and Python's bytecode would sync to every colleague
# (docs/decisions/0003, root decision 0031).
if ($repo.Split('\') -contains 'ACCDocs') { throw "Refusing to set up in an ACC folder ($repo): clone the repo to a local disk." }

# Cemengal: the transcript goes to the self-cleaning local temp folder, never beside this script. The .venv
# (and the Python helper autocad_mcp.temp_files) may not exist yet, so the same prune lives here too.
# >>> prune
function Invoke-CemTempPrune([string]$Dir, [int]$Days = 7, [long]$MaxBytes = 50MB) {
  try {
    $limit = (Get-Date).AddDays(-$Days)
    $kept = @()
    foreach ($f in @(Get-ChildItem -LiteralPath $Dir -File -Recurse -ErrorAction SilentlyContinue | Sort-Object LastWriteTime)) {
      if ($f.LastWriteTime -lt $limit) {
        try { Remove-Item -LiteralPath $f.FullName -Force -ErrorAction Stop; continue } catch {}
      }
      $kept += $f
    }
    $total = [long](($kept | Measure-Object Length -Sum).Sum)
    foreach ($f in $kept) {
      if ($total -lt $MaxBytes) { break }
      try { Remove-Item -LiteralPath $f.FullName -Force -ErrorAction Stop; $total -= $f.Length } catch {}
    }
  } catch {}
}
# <<< prune
$logDir = Join-Path ([IO.Path]::GetTempPath()) "Cemengal\AutocadMCP"
Invoke-CemTempPrune -Dir $logDir
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("setup-" + (Get-Date -Format yyyyMMdd) + ".log")
Start-Transcript -Path $log -Append | Out-Null
Write-Host "== AutoCAD MCP setup in $repo (log: $log)" -ForegroundColor Cyan

# 1. Find a Python >= 3.10
$candidates = @(
  @("py", "-3"), @("python"),
  @("$env:USERPROFILE\miniforge3\python.exe"),
  @("$env:USERPROFILE\anaconda3\python.exe"),
  @("$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"),
  @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"),
  @("$env:LOCALAPPDATA\Programs\Python\Python311\python.exe")
)
$py = $null
foreach ($c in $candidates) {
  try {
    $exe = $c[0]; $extra = @($c | Select-Object -Skip 1)
    $v = & $exe @extra -c "import sys;print('%d.%d'%sys.version_info[:2]) if sys.version_info>=(3,10) else exit(1)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $v) { $py = $c; Write-Host "Using Python $v -> $($c -join ' ')"; break }
  } catch {}
}
if (-not $py) { throw "No Python 3.10+ found. Install it from python.org and re-run." }

# 2. Virtual env + dependencies
$venvPy = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
  & $py[0] @(@($py | Select-Object -Skip 1) + @("-m", "venv", (Join-Path $repo ".venv")))
}
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -e $repo --quiet | Out-Host
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
Write-Host "Dependencies installed (mcp<2, pywin32)" -ForegroundColor Green

# 3. COM check against the running AutoCAD / Civil 3D
& $venvPy -c @"
import win32com.client as w
from autocad_mcp.server import AutoCADCOMServer
for pid in AutoCADCOMServer.candidate_progids():
    try:
        a = w.GetActiveObject(pid)
        print('AutoCAD COM OK via', pid, ':', a.Name, a.Version, '| drawing:', a.ActiveDocument.Name)
        break
    except Exception:
        pass
else:
    print('AutoCAD not reachable yet (open AutoCAD or Civil 3D with a drawing)')
"@ | Out-Host

# 4. Register in Claude desktop config (Store and classic installs), with backup
# Cemengal: since 2026-10-20 the Store (MSIX) app keeps its data in %LOCALAPPDATA%\Claude-Data\claude_<id>\;
# Packages\Claude_<id>\LocalCache\Roaming\Claude then holds only a .user-data-left marker.
# >>> configs
function Get-ClaudeConfigs([string]$LocalAppData, [string]$AppData) {
  $configs = @(Get-ChildItem (Join-Path $LocalAppData "Claude-Data") -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Join-Path $_.FullName "claude_desktop_config.json" })
  $configs += @(Get-ChildItem (Join-Path $LocalAppData "Packages") -Directory -Filter "Claude*" -ErrorAction SilentlyContinue |
    ForEach-Object { Join-Path $_.FullName "LocalCache\Roaming\Claude\claude_desktop_config.json" })
  $classic = Join-Path $AppData "Claude\claude_desktop_config.json"
  $existing = @(@($configs) + $classic | Where-Object { Test-Path $_ })
  if ($existing.Count -eq 0) { $existing = @($classic) }
  $existing
}
# <<< configs
$existing = @(Get-ClaudeConfigs -LocalAppData $env:LOCALAPPDATA -AppData $env:APPDATA)
foreach ($cfg in $existing) {
  New-Item -ItemType Directory -Force (Split-Path $cfg) | Out-Null
  if (Test-Path $cfg) { Copy-Item $cfg "$cfg.bak-autocad" -Force }
  & $venvPy -c @"
import json, os, sys
p = sys.argv[1]
d = json.load(open(p, encoding='utf-8-sig')) if os.path.exists(p) and os.path.getsize(p) else {}
d.setdefault('mcpServers', {})['autocad-mcp'] = {
    'command': sys.argv[2],
    'args': ['-m', 'autocad_mcp.server'],
}
json.dump(d, open(p, 'w', encoding='utf-8'), indent=2)
print('Registered autocad-mcp in', p)
print('Servers now in config:', list(d['mcpServers']))
"@ $cfg $venvPy | Out-Host
}
Write-Host ""
Write-Host "Done. Fully quit Claude (tray icon -> Quit) and reopen it." -ForegroundColor Green
Stop-Transcript | Out-Null
