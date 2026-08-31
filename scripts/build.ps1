$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock] $Command
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

$bundledPython = "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$pythonCandidates = @(
    $env:PYTHON,
    $bundledPython,
    "python",
    "py"
) | Where-Object { $_ }

$python = $null
foreach ($candidate in $pythonCandidates) {
    try {
        & $candidate --version | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $python = $candidate
            break
        }
    } catch {
    }
}

if (-not $python) {
    throw "Python was not found. Install Python 3.11+ or set the PYTHON environment variable."
}

function Stop-RunningDistExe {
    $distDir = Join-Path $projectRoot "dist"
    if (-not (Test-Path -LiteralPath $distDir)) {
        return
    }
    $distFull = [System.IO.Path]::GetFullPath($distDir)
    $pids = @()
    foreach ($proc in Get-Process -ErrorAction SilentlyContinue) {
        $path = $null
        try {
            $path = $proc.Path
        } catch {
            continue
        }
        if (-not $path) {
            continue
        }
        $full = [System.IO.Path]::GetFullPath($path)
        if ($full.StartsWith($distFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            Write-Host "Closing running $($proc.ProcessName) (PID $($proc.Id))"
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            $pids += $proc.Id
        }
    }
    foreach ($id in $pids) {
        Wait-Process -Id $id -Timeout 15 -ErrorAction SilentlyContinue
    }
}

Stop-RunningDistExe

if (-not (Test-Path ".venv")) {
    Invoke-Checked { & $python -m venv .venv }
}

$pipIndexUrl = if ($env:PIP_INDEX_URL) { $env:PIP_INDEX_URL } else { "https://pypi.tuna.tsinghua.edu.cn/simple" }

Invoke-Checked {
    & ".\.venv\Scripts\python.exe" -m pip install `
        --timeout 180 `
        --index-url $pipIndexUrl `
        -r requirements.txt
}

Invoke-Checked {
    & ".\.venv\Scripts\pyinstaller.exe" `
        --noconfirm `
        --clean `
        ".\DDTool.spec"
}

Invoke-Checked {
    & ".\.venv\Scripts\python.exe" -c @"
from pathlib import Path
dist = Path('dist')
src = dist / 'DDTool.exe'
dst = dist / '\u8c46\u835a\u5de5\u5177.exe'
if src.exists():
    dst.write_bytes(src.read_bytes())
    src.unlink()
for path in dist.glob('*.exe'):
    if path.name != dst.name:
        path.unlink()
print(dst)
"@
}
