# Uses the existing local executor; credentials stay in process memory.
# A simple script keeps native flags such as pytest -p out of PowerShell's
# common-parameter binding (where -p would mean PipelineVariable).
$ComposeArgs = $args

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$previous = @{}
$exitCode = 1
Push-Location -LiteralPath $root
try {
    $previous['PYTHONDONTWRITEBYTECODE'] = $env:PYTHONDONTWRITEBYTECODE
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $runtimeCode = @'
import json, os
from django.conf import settings
if settings.SETTINGS_MODULE != 'config.settings.development':
    raise SystemExit('Use somente a configuracao de desenvolvimento local.')
keys = ('POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_PORT')
values = {key: os.environ[key] for key in keys}
values['DJANGO_SECRET_KEY'] = settings.SECRET_KEY
values['DJANGO_DEBUG'] = str(settings.DEBUG).lower()
values['DJANGO_ALLOWED_HOSTS'] = ','.join(settings.ALLOWED_HOSTS)
values['CSRF_TRUSTED_ORIGINS'] = ','.join(settings.CSRF_TRUSTED_ORIGINS)
print(json.dumps(values))
'@
    $runtimeJson = & .\.venv\Scripts\python.exe .\.local\dev_local.py backend\manage.py shell --no-imports --verbosity 0 --command $runtimeCode
    $runtimeExit = $LASTEXITCODE
    if ($runtimeExit -ne 0) {
        $exitCode = $runtimeExit
        throw 'Nao foi possivel carregar a configuracao pelo executor local.'
    }
    $runtime = $runtimeJson | ConvertFrom-Json
    foreach ($property in $runtime.PSObject.Properties) {
        $previous[$property.Name] = [Environment]::GetEnvironmentVariable($property.Name, 'Process')
        [Environment]::SetEnvironmentVariable($property.Name, [string]$property.Value, 'Process')
    }
    $endpoint = & docker context inspect --format '{{.Endpoints.docker.Host}}'
    $contextExit = $LASTEXITCODE
    if ($contextExit -ne 0 -or $endpoint -ne 'npipe:////./pipe/dockerDesktopLinuxEngine' -or $env:DOCKER_HOST -or $env:DOCKER_CONTEXT) {
        throw 'Use o contexto local desktop-linux, sem overrides DOCKER_HOST/DOCKER_CONTEXT.'
    }
    if (-not $ComposeArgs) { $ComposeArgs = @('ps') }
    & docker --context desktop-linux compose --project-name obra-control --project-directory $root -f docker-compose.yml -f docker-compose.dev.yml @ComposeArgs
    $exitCode = $LASTEXITCODE
}
catch {
    Write-Host 'Compose de desenvolvimento interrompido. Confira Docker Desktop e o executor local; valores privados nao foram exibidos.'
}
finally {
    foreach ($key in $previous.Keys) {
        [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process')
    }
    $runtimeJson = $runtime = $null
    Pop-Location
}
exit $exitCode
