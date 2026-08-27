param(
    [switch]$SkipInstaller,
    [switch]$OfflineBundle
)

$isCorePowerShell = $PSVersionTable.PSEdition -eq "Core"
if (-not $isCorePowerShell) {
    $pwsh = Get-Command pwsh.exe -ErrorAction SilentlyContinue
    if (-not $pwsh) {
        throw "PowerShell 7 is required to preserve UTF-8 release metadata."
    }
    $forwarded = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath)
    if ($SkipInstaller) {
        $forwarded += "-SkipInstaller"
    }
    if ($OfflineBundle) {
        $forwarded += "-OfflineBundle"
    }
    & $pwsh.Source @forwarded
    exit $LASTEXITCODE
}

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Staging = Join-Path $PSScriptRoot "staging"
$Build = Join-Path $PSScriptRoot "build"
$CanonicalDist = Join-Path $PSScriptRoot "dist"
$Dist = $CanonicalDist
$Python = Join-Path $ProjectRoot "venv\Scripts\python.exe"
$AppVersion = "0.1"
$InstallerBaseName = if ($OfflineBundle) { "Xixi-Setup-Offline" } else { "Xixi-Setup" }

function Reset-ReleaseDirectory([string]$Path) {
    $resolvedParent = (Resolve-Path (Split-Path -Parent $Path)).Path
    $target = [System.IO.Path]::GetFullPath($Path)
    if (-not $target.StartsWith($resolvedParent + [System.IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to reset path outside packaging directory: $target"
    }
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
    New-Item -ItemType Directory -Path $target | Out-Null
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing build Python: $Python"
}

Push-Location $ProjectRoot
try {
    & $Python -m compileall -q app scripts start_xixi_qq.py start_xixi_studio.py start_xixi_desktop.py
    if ($LASTEXITCODE -ne 0) { throw "Python compile check failed" }
    & $Python -m unittest discover -s tests -p "test_*.py"
    if ($LASTEXITCODE -ne 0) { throw "Public release test suite failed" }
    & $Python (Join-Path $ProjectRoot "scripts\verify_public_voice_pipeline.py")
    if ($LASTEXITCODE -ne 0) { throw "Public voice verification regression failed" }
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($node) {
        foreach ($script in @("studio\app.js", "studio\setup.js", "studio\call_overlay.js")) {
            & $node.Source --check (Join-Path $ProjectRoot $script)
            if ($LASTEXITCODE -ne 0) { throw "JavaScript syntax check failed: $script" }
        }
    }
}
finally {
    Pop-Location
}

Reset-ReleaseDirectory $Staging
Reset-ReleaseDirectory $Build
try {
    Reset-ReleaseDirectory $Dist
}
catch {
    $Dist = Join-Path $PSScriptRoot ("dist-build-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    Write-Warning "The canonical release directory is in use; building in: $Dist"
    Reset-ReleaseDirectory $Dist
}

Copy-Item -LiteralPath (Join-Path $ProjectRoot "persona.public.txt") -Destination (Join-Path $Staging "persona.txt")
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "starter_interest_profile.json") -Destination (Join-Path $Staging "interest_profile.json")
New-Item -ItemType Directory -Path (Join-Path $Staging "voice_models") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Staging "voice_wheels") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Staging "voice_engine") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Staging "voice_nltk_data") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Staging "install_tools") | Out-Null
& $Python (Join-Path $PSScriptRoot "create_installer_assets.py")
if ($LASTEXITCODE -ne 0) { throw "Installer asset generation failed" }

$UvCommand = Get-Command uv -ErrorAction SilentlyContinue
if (-not $UvCommand -or -not (Test-Path -LiteralPath $UvCommand.Source)) {
    throw "uv is required to stage the high-speed environment installer"
}
Copy-Item -LiteralPath $UvCommand.Source -Destination (Join-Path $Staging "install_tools\uv.exe")

$Workspace = Split-Path -Parent $ProjectRoot
$VoiceRoot = Join-Path $Workspace "work\GPT-SoVITS"
$VoiceEngineStage = Join-Path $Staging "voice_engine"

function Copy-VoiceEngineTree(
    [string]$Source,
    [string]$Destination,
    [string[]]$ExcludedPrefixes
) {
    foreach ($file in Get-ChildItem -LiteralPath $Source -Recurse -File) {
        $relative = [System.IO.Path]::GetRelativePath($Source, $file.FullName)
        $normalized = $relative.Replace("\", "/")
        if ($normalized -match '(^|/)__pycache__(/|$)' -or $normalized.EndsWith(".pyc")) {
            continue
        }
        $excluded = $false
        foreach ($prefix in $ExcludedPrefixes) {
            if ($normalized.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                $excluded = $true
                break
            }
        }
        if ($excluded) { continue }
        $target = Join-Path $Destination $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $target
    }
}

foreach ($name in @("api_v2.py", "requirements.txt", "requirements-windows-cu121.txt")) {
    $source = Join-Path $VoiceRoot $name
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $VoiceEngineStage $name)
    }
}
Copy-VoiceEngineTree `
    (Join-Path $VoiceRoot "GPT_SoVITS") `
    (Join-Path $VoiceEngineStage "GPT_SoVITS") `
    @("pretrained_models/", "text/G2PWModel/", "text/G2PWModel_1.1.zip")
Copy-VoiceEngineTree `
    (Join-Path $VoiceRoot "tools") `
    (Join-Path $VoiceEngineStage "tools") `
    @("asr/", "uvr5/")
$VoiceNltkDataSource = Join-Path $PSScriptRoot "voice_nltk_data"
$VoiceNltkDataStage = Join-Path $Staging "voice_nltk_data"
foreach ($relative in @(
    "corpora\cmudict.zip",
    "taggers\averaged_perceptron_tagger.zip",
    "taggers\averaged_perceptron_tagger_eng.zip"
)) {
    $source = Join-Path $VoiceNltkDataSource $relative
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Missing offline NLTK voice data: $source"
    }
    $target = Join-Path $VoiceNltkDataStage $relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $target
}
$VoiceModels = [ordered]@{
    "GPT_weights_v2Pro\xixi_voice_v2Pro-e10.ckpt" = "xixi_voice_multilingual.ckpt"
    "SoVITS_weights_v2Pro\xixi_voice_v2Pro_e4_s1572.pth" = "xixi_voice_multilingual.pth"
    "SoVITS_weights_v2Pro\xixi_voice_v2Pro_e2e4_blend30.pth" = "xixi_voice_chinese.pth"
}
if ($OfflineBundle) {
    $VoiceModels["GPT_SoVITS\pretrained_models\s1v3.ckpt"] = "s1v3.ckpt"
}

& $Python -m pip download `
    --only-binary=:all: `
    --no-deps `
    --dest (Join-Path $Staging "voice_wheels") `
    --platform win_amd64 `
    --python-version 310 `
    --implementation cp `
    --abi cp310 `
    "pyopenjtalk-plus==0.4.1.post8"
if ($LASTEXITCODE -ne 0) { throw "Failed to stage the prebuilt Japanese pronunciation wheel" }
foreach ($entry in $VoiceModels.GetEnumerator()) {
    $source = Join-Path $VoiceRoot $entry.Key
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Missing release voice model: $source"
    }
    Copy-Item -LiteralPath $source -Destination (Join-Path $Staging "voice_models\$($entry.Value)")
}

$NapCatSource = Join-Path $Workspace "napcat"
$NapCatStage = Join-Path $Staging "napcat"
if (-not (Test-Path -LiteralPath (Join-Path $NapCatSource "launcher-user.bat"))) {
    throw "Missing NapCat release source: $NapCatSource"
}
New-Item -ItemType Directory -Path $NapCatStage | Out-Null
foreach ($directory in @("native", "node_modules", "static", "worker")) {
    $source = Join-Path $NapCatSource $directory
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination $NapCatStage -Recurse
    }
}
$napcatConfigSource = Join-Path $NapCatSource "config\napcat.json"
if (Test-Path -LiteralPath $napcatConfigSource) {
    New-Item -ItemType Directory -Path (Join-Path $NapCatStage "config") -Force | Out-Null
    Copy-Item -LiteralPath $napcatConfigSource -Destination (Join-Path $NapCatStage "config\napcat.json")
}
foreach ($name in @(
    "launcher-user.bat",
    "launcher-win10-user.bat",
    "napcat.mjs",
    "NapCatWinBootHook.dll",
    "NapCatWinBootMain.exe",
    "package.json",
    "qqnt.json"
)) {
    $source = Join-Path $NapCatSource $name
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Missing NapCat release file: $source"
    }
    Copy-Item -LiteralPath $source -Destination (Join-Path $NapCatStage $name)
}
$NapCatConsoleModules = @(Get-ChildItem -LiteralPath $NapCatSource -File -Filter "conout-*.js")
if ($NapCatConsoleModules.Count -eq 0) {
    throw "Missing NapCat console runtime module: $NapCatSource\conout-*.js"
}
foreach ($module in $NapCatConsoleModules) {
    Copy-Item -LiteralPath $module.FullName -Destination (Join-Path $NapCatStage $module.Name)
}

# NapCat publishes native binaries for several operating systems in one archive.
# The public desktop build only supports Windows x64, so keeping the others wastes
# tens of megabytes without adding a usable capability.
foreach ($file in Get-ChildItem -LiteralPath $NapCatStage -File -Recurse) {
    $relative = [System.IO.Path]::GetRelativePath($NapCatStage, $file.FullName)
    if ($relative -match '(?i)(^|[\\/._-])(linux|darwin|arm64)([\\/._-]|$)') {
        Remove-Item -LiteralPath $file.FullName -Force
    }
}

$previousOfflineBundle = $env:XIXI_BUILD_OFFLINE_BUNDLE
$env:XIXI_BUILD_OFFLINE_BUNDLE = if ($OfflineBundle) { "1" } else { "0" }
try {
    & $Python -m PyInstaller --noconfirm --clean --distpath $Dist --workpath $Build (Join-Path $PSScriptRoot "xixi_public.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
}
finally {
    if ($null -eq $previousOfflineBundle) {
        Remove-Item Env:XIXI_BUILD_OFFLINE_BUNDLE -ErrorAction SilentlyContinue
    }
    else {
        $env:XIXI_BUILD_OFFLINE_BUNDLE = $previousOfflineBundle
    }
}

$ReleaseRoot = Join-Path $Dist "Xixi"
$ManifestArtifacts = @(
    "Xixi.exe",
    "studio\app.js",
    "studio\setup.html",
    "studio\setup.js",
    "studio\styles.css",
    "data\voice_assets\xixi_voice_reference_zh.mp3",
    "data\voice_assets\xixi_reference_zh.mp3",
    "runtime\voice\package\models\xixi_voice_multilingual.ckpt",
    "runtime\voice\package\models\xixi_voice_multilingual.pth",
    "runtime\voice\package\models\xixi_voice_chinese.pth",
    "runtime\voice\package\wheels\pyopenjtalk_plus-0.4.1.post8-cp310-cp310-win_amd64.whl",
    "runtime\voice\package\engine\api_v2.py",
    "runtime\voice\package\engine\GPT_SoVITS\TTS_infer_pack\TTS.py",
    "runtime\install_tools\uv.exe",
    "runtime\components\NapCat\launcher-user.bat",
    "LICENSE",
    "NOTICE",
    "docs\LICENSING.md",
    "THIRD_PARTY_NOTICES.md",
    "third_party_licenses\NapCatQQ-LICENSE.txt",
    "third_party_licenses\GPT-SoVITS-LICENSE.txt"
) + @(
    $NapCatConsoleModules | ForEach-Object { "runtime\components\NapCat\$($_.Name)" }
)
if ($OfflineBundle) {
    $ManifestArtifacts += @(
        "runtime\voice\package\models\s1v3.ckpt",
        "whisper-small-full\model.bin"
    )
}
$Artifacts = foreach ($RelativePath in $ManifestArtifacts) {
    $ArtifactPath = Join-Path $ReleaseRoot $RelativePath
    if (Test-Path -LiteralPath $ArtifactPath) {
        $Artifact = Get-Item -LiteralPath $ArtifactPath
        [ordered]@{
            path = $RelativePath.Replace("\", "/")
            size = $Artifact.Length
            sha256 = (Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash
        }
    }
}
$BuiltAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$ExeArtifact = $Artifacts | Where-Object { $_.path -eq "Xixi.exe" } | Select-Object -First 1
$ExeHash = $ExeArtifact.sha256
$BuildSuffix = if ($ExeHash) { $ExeHash.Substring(0, 12).ToLowerInvariant() } else { "unknown" }
$BuildId = "xixi-$AppVersion-$($BuiltAt.Replace('-', '').Replace(':', ''))-$BuildSuffix"
$Manifest = [ordered]@{
    schema_version = 2
    app_name = "昔夕"
    edition = "public"
    bundle_mode = if ($OfflineBundle) { "offline" } else { "online" }
    app_version = $AppVersion
    built_at_utc = $BuiltAt
    build_id = $BuildId
    deployment = [ordered]@{
        layout = "classified-install-root"
        executable = "程序文件/Xixi.exe"
        launch_shortcut = "启动昔夕.lnk"
        pointer_file = "程序文件/数据目录.txt"
        default_data_home = "用户数据"
        uninstaller = "卸载程序"
        runtime_data = "运行数据"
        webview_data = "WebView数据"
        logs = "日志"
        downloads = "下载"
        components = "本地组件"
        models = "本地模型"
        upgrade_preserves_data = $true
    }
    artifacts = @($Artifacts)
}
$Manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $ReleaseRoot "构建清单.json") -Encoding utf8

& $Python (Join-Path $ProjectRoot "scripts\audit_public_release.py") $ReleaseRoot
if ($LASTEXITCODE -ne 0) { throw "Privacy audit failed" }

& $Python (Join-Path $ProjectRoot "scripts\smoke_public_release.py") --executable (Join-Path $ReleaseRoot "Xixi.exe")
if ($LASTEXITCODE -ne 0) { throw "Packaged public release smoke test failed" }

if (-not $SkipInstaller) {
    $iscc = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $iscc) { throw "Inno Setup 6 is not installed" }
    Push-Location $PSScriptRoot
    $DistName = Split-Path -Leaf $Dist
    try { & $iscc "/DMyAppVersion=$AppVersion" "/DMyOutputBaseFilename=$InstallerBaseName" "/DMyDistDir=$DistName" (Join-Path $PSScriptRoot "xixi_public.iss") }
    finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw "Installer build failed" }
    $InstallerPath = Join-Path $Dist "installer\$InstallerBaseName.exe"
    & $Python (Join-Path $ProjectRoot "scripts\audit_public_release.py") $InstallerPath --archive-only
    if ($LASTEXITCODE -ne 0) { throw "Installer privacy audit failed" }
    $InstallerHash = (Get-FileHash -LiteralPath $InstallerPath -Algorithm SHA256).Hash
    "$InstallerHash  $InstallerBaseName.exe" | Set-Content -LiteralPath (Join-Path $Dist "installer\SHA256SUMS.txt") -Encoding ascii
    if ($Dist -ne $CanonicalDist) {
        $CanonicalInstallerDir = Join-Path $CanonicalDist "installer"
        New-Item -ItemType Directory -Path $CanonicalInstallerDir -Force | Out-Null
        Copy-Item -LiteralPath $InstallerPath -Destination (Join-Path $CanonicalInstallerDir "$InstallerBaseName.exe") -Force
        Copy-Item -LiteralPath (Join-Path $Dist "installer\SHA256SUMS.txt") -Destination (Join-Path $CanonicalInstallerDir "SHA256SUMS.txt") -Force
    }
}

Write-Host "Release ready: $Dist"
