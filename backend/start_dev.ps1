$ErrorActionPreference = "Stop"
Get-Content (Join-Path $PSScriptRoot ".env") | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $idx = $_.IndexOf('=')
    $key = $_.Substring(0, $idx).Trim()
    $value = $_.Substring($idx + 1).Trim()
    [System.Environment]::SetEnvironmentVariable($key, $value)
}
& (Join-Path $PSScriptRoot ".venv/Scripts/uvicorn.exe") main:app --reload --port 8000
