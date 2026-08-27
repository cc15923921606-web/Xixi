param(
    [string]$ProjectRoot = (Split-Path $PSScriptRoot -Parent)
)

$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$Pythonw = Join-Path $ProjectRoot "venv\Scripts\pythonw.exe"
$Launcher = Join-Path $ProjectRoot "start_xixi_desktop.py"
$Icon = Join-Path $ProjectRoot "studio\assets\xixi-v3.ico"
$AppName = ([string][char]0x6614) + [char]0x5915

if (-not (Test-Path $Pythonw)) { throw "找不到 Python 环境：$Pythonw" }
if (-not (Test-Path $Launcher)) { throw "找不到桌面启动器：$Launcher" }

function New-XixiShortcut([string]$Path) {
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($Path)
    $Shortcut.TargetPath = $Pythonw
    $Shortcut.Arguments = '"' + $Launcher + '"'
    $Shortcut.WorkingDirectory = $ProjectRoot
    $Shortcut.Description = $AppName + " local desktop application"
    $Shortcut.WindowStyle = 1
    if (Test-Path $Icon) { $Shortcut.IconLocation = $Icon + ",0" }
    $Shortcut.Save()
}

$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) ($AppName + ".lnk")
$StartMenuDirectory = Join-Path ([Environment]::GetFolderPath("Programs")) $AppName
New-Item -ItemType Directory -Path $StartMenuDirectory -Force | Out-Null
$StartMenuShortcut = Join-Path $StartMenuDirectory ($AppName + ".lnk")

New-XixiShortcut $DesktopShortcut
New-XixiShortcut $StartMenuShortcut

[pscustomobject]@{
    Desktop = $DesktopShortcut
    StartMenu = $StartMenuShortcut
}
