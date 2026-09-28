# Run the rolling quarterly India research workflow (archive + orchestrate).
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
$EnvFile = Join-Path $ScriptDir "india-research-quarterly.env"

if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') {
            return
        }
        $name, $value = $_ -split '=', 2
        if ($name) {
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}

Set-Location $ProjectRoot
python -m src.investing.cli schedule run-quarterly @args
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
