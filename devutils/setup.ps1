# Copyright 2026 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.

<#
.SYNOPSIS
Sets up a Windows machine for Helium development.

.DESCRIPTION
Installs Git, clones helium-windows onto a Dev Drive (creating one if there
isn't one yet), installs the build requirements from the checkout's
.config\configuration.winget, sets the Git and PowerShell options that the
development tools need, and installs q. Every step is skipped when it is
already done, so it is safe to run again.

Run it from an elevated PowerShell, without cloning anything first:
  irm https://raw.githubusercontent.com/imputnet/helium-windows/main/devutils/setup.ps1 | iex

To pass options, run it like this instead:
  iex "& {$(irm https://raw.githubusercontent.com/imputnet/helium-windows/main/devutils/setup.ps1)} -SkipDevDrive"

It can also be run from an existing checkout:
  powershell -ExecutionPolicy Bypass -File devutils\setup.ps1
Builds are much faster on a Dev Drive, so that checkout is only set up in place
when it is on one, or with -SkipDevDrive. Otherwise the script clones another
checkout onto the Dev Drive, as it does without one.

.PARAMETER Path
Where to clone helium-windows, or the existing checkout to set up. Defaults to
\src\helium-windows on the Dev Drive.

.PARAMETER Branch
The branch or tag to clone.

.PARAMETER DevDrivePath
Where to create a Dev Drive VHDX, if this machine doesn't have a Dev Drive yet.

.PARAMETER DevDriveSize
The maximum size of a new Dev Drive. The VHDX only takes up what is used.

.PARAMETER SkipDevDrive
Don't use or create a Dev Drive. The checkout goes in ~\src\helium-windows,
unless -Path says otherwise.
#>
param(
    [string]$Path,
    [string]$Branch = 'main',
    [string]$DevDrivePath = "$env:SystemDrive\devdrive.vhdx",
    [uint64]$DevDriveSize = 250GB,
    [switch]$SkipDevDrive
)

$Repository = 'https://github.com/imputnet/helium-windows.git'

function Write-Step($message) {
    Write-Host "==> $message" -ForegroundColor Cyan
}

function Invoke-Native {
    # Judge native commands by their exit code: when output is redirected,
    # Windows PowerShell turns their stderr into errors, which Stop would make fatal.
    $ErrorActionPreference = 'Continue'
    & $args[0] @($args | Select-Object -Skip 1)
    if ($LASTEXITCODE -ne 0) {
        throw "$($args -join ' ') failed with exit code $LASTEXITCODE"
    }
}

function Update-SessionPath {
    # Pick up what installers added since this session started.
    $machine = [Environment]::GetEnvironmentVariable('PATH', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('PATH', 'User')
    $env:PATH = "$machine;$user"
}

function Install-Git {
    if (Get-Command git.exe -ErrorAction SilentlyContinue) {
        return
    }

    Write-Step 'Installing Git'
    Invoke-Native winget install -e --id Git.Git --source winget `
        --accept-package-agreements --accept-source-agreements --disable-interactivity
    Update-SessionPath
}

function Test-DevDrive($driveLetter) {
    (fsutil devdrv query "${driveLetter}:" | Out-String) -match 'trusted developer volume'
}

function Get-DevDrive {
    Get-Volume | Where-Object { $_.DriveLetter -and $_.FileSystemType -eq 'ReFS' } |
        Where-Object { Test-DevDrive $_.DriveLetter } | Select-Object -First 1
}

function New-DevDrive {
    if (Test-Path $DevDrivePath) {
        throw "$DevDrivePath already exists but isn't an attached Dev Drive; attach it, " +
            'or pass -DevDrivePath with a new location'
    }

    Write-Step "Creating a $($DevDriveSize / 1GB) GB Dev Drive at $DevDrivePath"
    $script = "create vdisk file=`"$DevDrivePath`" maximum=$($DevDriveSize / 1MB) type=expandable`n" +
        "attach vdisk`n"
    $script | diskpart | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "diskpart couldn't create $DevDrivePath"
    }

    $disk = Get-DiskImage -ImagePath $DevDrivePath | Get-Disk
    Initialize-Disk -Number $disk.Number -PartitionStyle GPT
    $partition = New-Partition -DiskNumber $disk.Number -UseMaximumSize -AssignDriveLetter
    $volume = Format-Volume -Partition $partition -DevDrive -FileSystem ReFS `
        -NewFileSystemLabel 'Dev Drive' -Confirm:$false

    # A VHDX isn't attached again after a restart by itself.
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument (
        "-NoProfile -Command `"Mount-DiskImage -ImagePath '$DevDrivePath'`"")
    Register-ScheduledTask -TaskName 'Attach Helium Dev Drive' -Action $action `
        -Trigger (New-ScheduledTaskTrigger -AtStartup) -User 'SYSTEM' -RunLevel Highest -Force |
        Out-Null

    $volume
}

function Get-CheckoutPath {
    if ($Path) {
        return $Path
    }

    # When run from a checkout rather than through iex, set that one up, as
    # long as it is on a Dev Drive: building anywhere else is much slower.
    if ($PSScriptRoot -and (Test-Path "$PSScriptRoot\..\.git")) {
        $local = Split-Path -Parent $PSScriptRoot
        if ($SkipDevDrive -or (Test-DevDrive (Split-Path -Qualifier $local).TrimEnd(':'))) {
            return $local
        }
    }

    if ($SkipDevDrive) {
        return "$HOME\src\helium-windows"
    }

    $devDrive = Get-DevDrive
    if ($devDrive) {
        Write-Step "Using the Dev Drive at $($devDrive.DriveLetter):"
    } else {
        $devDrive = New-DevDrive
    }

    "$($devDrive.DriveLetter):\src\helium-windows"
}

function Initialize-Checkout($checkout) {
    if (-not (Test-Path "$checkout\.git")) {
        Write-Step "Cloning helium-windows to $checkout"
        Invoke-Native git clone --recurse-submodules --branch $Branch $Repository $checkout
        return
    }

    Write-Step "Using the checkout at $checkout"
    Invoke-Native git -C $checkout config core.autocrlf false

    # Leave an existing helium-chromium checkout alone, since it may have work in it.
    if (-not (Test-Path "$checkout\helium-chromium\.git")) {
        Invoke-Native git -C $checkout submodule update --init --recursive
    }

    $converted = git -C $checkout ls-files --eol | Select-String 'i/lf\s+w/crlf' |
        Select-Object -First 1
    if ($converted) {
        Write-Warning ("$checkout was checked out with converted line endings, which breaks " +
            'patches. Clone it again now that core.autocrlf is false.')
    }
}

function Install-Requirements($checkout) {
    $configuration = "$checkout\.config\configuration.winget"
    if (-not (Test-Path $configuration)) {
        throw "$configuration doesn't exist; update the checkout to a newer helium-windows"
    }

    Write-Step 'Installing build requirements with winget'
    Invoke-Native winget configure --enable
    Invoke-Native winget configure -f $configuration `
        --accept-configuration-agreements --disable-interactivity
    Update-SessionPath
}

function Install-Debuggers {
    # gn gen copies dbghelp.dll from the SDK's Debugging Tools for Windows,
    # which Visual Studio's SDK component doesn't install.
    $dbghelp = "${env:ProgramFiles(x86)}\Windows Kits\10\Debuggers\x64\dbghelp.dll"
    if (Test-Path $dbghelp) {
        return
    }

    if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
        Write-Warning ("The SDK doesn't install Debuggers\x64 on ARM64, but Chromium needs " +
            "it; copy it from an x64 machine to $(Split-Path $dbghelp)")
        return
    }

    Write-Step 'Installing the Windows SDK debugging tools'
    # The same Windows SDK installer as in CI, limited to the debugging tools.
    $installer = "$env:TEMP\winsdksetup.exe"
    Invoke-WebRequest -UseBasicParsing -OutFile $installer 'https://go.microsoft.com/fwlink/?linkid=2370315'
    $process = Start-Process $installer -Wait -PassThru -ArgumentList (
        '/features', 'OptionId.WindowsDesktopDebuggers', '/quiet', '/norestart')
    Remove-Item $installer
    if ($process.ExitCode -notin 0, 3010) {
        throw "The Windows SDK installer failed with exit code $($process.ExitCode)"
    }
    if (-not (Test-Path $dbghelp)) {
        throw "$dbghelp is still missing after installing the debugging tools"
    }
}

function Set-UserOptions {
    Write-Step 'Setting PowerShell and Python options'

    # dev.ps1 is a local script, which the default policy doesn't allow. When
    # this script runs with -ExecutionPolicy Bypass, PowerShell reports the new
    # policy as overridden, even though it was saved.
    try {
        Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force
    } catch [Security.SecurityException] {
    }
    if ((Get-ExecutionPolicy -Scope CurrentUser) -ne 'RemoteSigned') {
        Write-Warning "couldn't allow local scripts; dev.ps1 won't load until you do"
    }

    Invoke-Native python -m pip install --quiet --disable-pip-version-check requests Pillow
}

function Install-Q {
    if (Get-Command q.exe -ErrorAction SilentlyContinue) {
        Write-Step "q is already installed at $((Get-Command q.exe).Source)"
        return
    }

    Write-Step 'Installing q'
    $directory = "$env:LOCALAPPDATA\Programs\q"
    New-Item -ItemType Directory -Force $directory | Out-Null
    Invoke-WebRequest -UseBasicParsing -OutFile "$directory\q.exe" `
        'https://github.com/imputnet/q/releases/latest/download/q-x86_64-windows.exe'

    $userPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
    if (($userPath -split ';') -notcontains $directory) {
        [Environment]::SetEnvironmentVariable('PATH', "$userPath;$directory", 'User')
    }
    Update-SessionPath
}

function Invoke-Setup {
    # Scoped to this function, so that it doesn't leak into the session under iex.
    $ErrorActionPreference = 'Stop'
    # Windows PowerShell may otherwise not offer TLS 1.2 for the downloads.
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    $principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this from an elevated PowerShell: it installs software and creates a Dev Drive.'
    }

    Install-Git
    # Converted line endings break patches, so this has to be set before cloning.
    Invoke-Native git config --global core.autocrlf false

    $checkout = Get-CheckoutPath
    Initialize-Checkout $checkout
    Install-Requirements $checkout
    Install-Debuggers
    Set-UserOptions
    Install-Q

    Write-Step 'Done. To set up the Chromium source tree, run:'
    Write-Host "  cd $checkout"
    Write-Host '  . .\dev.ps1'
    Write-Host '  he setup'
}

Invoke-Setup
