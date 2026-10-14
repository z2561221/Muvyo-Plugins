$ErrorActionPreference = 'Stop'
$pythonPath = git config --get muvyo.pythonPath
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($pythonPath) -or
    -not [IO.Path]::IsPathRooted($pythonPath) -or -not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    [Console]::Error.WriteLine('Set muvyo.pythonPath to a verified Python 3 executable with cryptography installed.')
    exit 1
}
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
& $pythonPath (Join-Path $PSScriptRoot '../.github/scripts/check_staged.py')
exit $LASTEXITCODE
