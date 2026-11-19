# Copyright 2026 The Helium Authors
# You can use, redistribute, and/or modify this source code under
# the terms of the GPL-3.0 license that can be found in the LICENSE file.

# Sets up this PowerShell session for Helium development:
#   PS> . .\dev.ps1
#   PS> he

if ($MyInvocation.InvocationName -ne '.') {
    Write-Error "usage: . .\dev.ps1, then run 'he'"
    return
}

$global:HeliumRoot = $PSScriptRoot

$heliumEnv = & python "$HeliumRoot\dev.py" env
if ($LASTEXITCODE -ne 0) {
    return
}
foreach ($line in $heliumEnv) {
    $name, $value = $line -split '=', 2
    Set-Item "env:$name" $value
}

function global:he {
    & python "$global:HeliumRoot\dev.py" @args
}

foreach ($name in 'q.exe', 'quilt.exe') {
    $program = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue
    if ($program) {
        $global:HeliumQuilt = ($program | Select-Object -First 1).Source
        break
    }
}

function global:q {
    & $global:HeliumQuilt --quiltrc - @args
}
Set-Alias -Scope Global quilt q

if (-not $global:HeliumPromptLoaded) {
    $global:HeliumPromptLoaded = $true
    $global:HeliumOriginalPrompt = $function:prompt
    function global:prompt {
        [char]::ConvertFromUtf32(0x1F388) + ' ' + (& $global:HeliumOriginalPrompt)
    }
}
