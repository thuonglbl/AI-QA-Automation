param(
    [string]$EnvFile = ".env",
    [string]$Version = "",
    [switch]$Push,
    [switch]$Login
)

$ErrorActionPreference = "Stop"

function Import-EnvFile {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        throw "Environment file not found: $Path"
    }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }

        $parts = $line.Split("=", 2)
        if ($parts.Count -ne 2) { return }

        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($value.StartsWith('"') -and $value.EndsWith('"')) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Get-RequiredEnv {
    param([string]$Name)

    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Missing required environment variable '$Name'. Set it in $EnvFile."
    }
    return $value
}

function Join-DockerImagePath {
    param(
        [string]$Prefix,
        [string]$ImageName,
        [string]$Tag
    )

    return "$($Prefix.TrimEnd('/'))/$ImageName`:$Tag"
}

$root = Split-Path -Parent $PSScriptRoot
Import-EnvFile (Join-Path $root $EnvFile)

$imagePrefix = Get-RequiredEnv "DOCKER_IMAGE_PREFIX"
$backendImageName = Get-RequiredEnv "DOCKER_BACKEND_IMAGE"
$frontendImageName = Get-RequiredEnv "DOCKER_FRONTEND_IMAGE"
$imageVersion = if ([string]::IsNullOrWhiteSpace($Version)) { Get-RequiredEnv "DOCKER_IMAGE_VERSION" } else { $Version }
$pythonVersion = Get-RequiredEnv "DOCKER_PYTHON_VERSION"
$nodeVersion = Get-RequiredEnv "DOCKER_NODE_VERSION"
$uvVersion = Get-RequiredEnv "DOCKER_UV_VERSION"
$nginxVersion = Get-RequiredEnv "DOCKER_NGINX_VERSION"

$backendImage = Join-DockerImagePath $imagePrefix $backendImageName $imageVersion
$frontendImage = Join-DockerImagePath $imagePrefix $frontendImageName $imageVersion

Write-Host "Building AI QA Docker images" -ForegroundColor Cyan
Write-Host "Image prefix: $imagePrefix"
Write-Host "Backend     : $backendImage"
Write-Host "Frontend    : $frontendImage"
Write-Host "Python      : $pythonVersion"
Write-Host "Node.js     : $nodeVersion"
Write-Host "uv          : $uvVersion"
Write-Host "Nginx       : $nginxVersion"

Push-Location $root
try {
    if ($Login) {
        $username = Get-RequiredEnv "ARTIFACTORY_USERNAME"
        $password = Get-RequiredEnv "ARTIFACTORY_PASSWORD"

        $password | docker login $imagePrefix --username $username --password-stdin
    }

    docker build --file Dockerfile.backend --build-arg PYTHON_VERSION=$pythonVersion --build-arg UV_VERSION=$uvVersion --tag $backendImage .
    docker build --file frontend/Dockerfile --build-arg NODE_VERSION=$nodeVersion --build-arg NGINX_VERSION=$nginxVersion --tag $frontendImage ./frontend

    if ($Push) {
        Write-Host "Pushing images to Artifactory" -ForegroundColor Cyan
        docker push $backendImage
        docker push $frontendImage
    }
    else {
        Write-Host "Build complete. Re-run with -Push to push images." -ForegroundColor Yellow
    }
}
finally {
    Pop-Location
}
