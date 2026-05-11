param(
    [switch]$SkipInstall,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$DjangoArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[dj] $Message"
}

$backendRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$venvDir = Join-Path $backendRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\\python.exe"
$requirements = Join-Path $backendRoot "requirements.txt"
$managePy = Join-Path $backendRoot "manage.py"

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Step "No existe .venv, creando entorno virtual..."
    Push-Location $backendRoot
    try {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            try {
                & py -3.11 -m venv .venv
            }
            catch {
                Write-Step "No fue posible crear .venv con Python 3.11; probando con el launcher por defecto..."
                & py -3 -m venv .venv
            }
        }
        elseif (Get-Command python -ErrorAction SilentlyContinue) {
            & python -m venv .venv
        }
        else {
            throw "No se encontro 'python' ni 'py' en PATH."
        }
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "No se pudo crear/encontrar $venvPython"
}

Write-Step "Verificando Django en .venv..."
$djangoOk = $true
try {
    & $venvPython -c "import django; print(django.get_version())" | Out-Null
}
catch {
    $djangoOk = $false
}

if (-not $djangoOk) {
    if ($SkipInstall) {
        throw "Django no esta instalado en .venv y se uso -SkipInstall."
    }
    if (-not (Test-Path -LiteralPath $requirements)) {
        throw "No existe requirements.txt en $requirements"
    }
    Write-Step "Instalando dependencias desde requirements.txt..."
    & $venvPython -m pip install -r $requirements
}

if (-not (Test-Path -LiteralPath $managePy)) {
    throw "No existe manage.py en $managePy"
}

if (-not $DjangoArgs -or $DjangoArgs.Count -eq 0) {
    $DjangoArgs = @("check")
}

Write-Step ("Ejecutando: python manage.py " + ($DjangoArgs -join " "))
Push-Location $backendRoot
try {
    & $venvPython manage.py @DjangoArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
