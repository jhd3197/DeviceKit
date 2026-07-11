# DeviceKit - dev helper
#
# Usage:
#   .\dev.ps1              Start backend + frontend in separate windows
#   .\dev.ps1 backend      Start only the backend (in this window)
#   .\dev.ps1 frontend     Start only the frontend (in this window)
#   .\dev.ps1 test         Run backend tests (extra args go to pytest)
#   .\dev.ps1 test -k ai   e.g. only tests matching "ai"

param(
    [Parameter(Position = 0)]
    [ValidateSet('dev', 'backend', 'frontend', 'test')]
    [string]$Command = 'dev',

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$root = $PSScriptRoot

# Add ADB to PATH if not already available
if (-not (Get-Command adb -ErrorAction SilentlyContinue)) {
    $adbDirs = @(
        'C:\Program Files (x86)\Android\android-sdk\platform-tools',
        "$env:LOCALAPPDATA\Android\Sdk\platform-tools"
    )
    foreach ($dir in $adbDirs) {
        if (Test-Path "$dir\adb.exe") {
            $env:PATH = "$env:PATH;$dir"
            break
        }
    }
}

switch ($Command) {
    'test' {
        Push-Location "$root\backend"
        try {
            python -m pytest tests/ @Rest
            exit $LASTEXITCODE
        }
        finally {
            Pop-Location
        }
    }
    'backend' {
        Set-Location "$root\backend"
        python app.py
    }
    'frontend' {
        Set-Location "$root\frontend"
        npm run dev
    }
    'dev' {
        Write-Host 'Starting DeviceKit dev servers...'
        Write-Host ''
        Write-Host '  Backend  : http://localhost:7317'
        Write-Host '  Frontend : http://localhost:7318'
        Write-Host ''

        Start-Process pwsh -WorkingDirectory "$root\backend" `
            -ArgumentList '-NoExit', '-Command', 'python app.py'

        # Wait for the backend to answer /health before opening the frontend,
        # so the first page load doesn't race the boot.
        Write-Host 'Waiting for backend...' -NoNewline
        for ($i = 0; $i -lt 30; $i++) {
            try {
                $null = Invoke-WebRequest -Uri 'http://127.0.0.1:7317/health' -TimeoutSec 2 -UseBasicParsing
                Write-Host ' ready.'
                break
            }
            catch {
                Write-Host '.' -NoNewline
                Start-Sleep -Seconds 1
            }
        }

        Start-Process pwsh -WorkingDirectory "$root\frontend" `
            -ArgumentList '-NoExit', '-Command', 'npm run dev'

        Write-Host 'Both servers started in separate windows.'
        Write-Host 'Close those windows to stop the servers.'
    }
}
