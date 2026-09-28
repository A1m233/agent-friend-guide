$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Set-Location (Join-Path $PSScriptRoot "..\..")
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -B -m unittest discover -s tests -v @args
} else {
    & python -B -m unittest discover -s tests -v @args
}
exit $LASTEXITCODE
