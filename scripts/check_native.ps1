param([string]$Application='dist\SonicForge\SonicForge.exe', [switch]$Neural)
$ErrorActionPreference='Stop'
$Root=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
Set-Location -LiteralPath $Root
$Application=[IO.Path]::GetFullPath((Join-Path $Root $Application))
$AppDirectory=Split-Path -Parent $Application
$Output=Join-Path $Root 'validation\packaged-native'
New-Item -ItemType Directory -Path $Output -Force | Out-Null
$MemoryReport=[Collections.Generic.List[object]]::new()
function Run-Native([string[]]$Arguments,[string]$Name) {
    $Quoted = foreach ($Argument in $Arguments) { '"'+$Argument.Replace('"','\"')+'"' }
    $Process=Start-Process -FilePath $Application -ArgumentList $Quoted -WindowStyle Hidden -PassThru -RedirectStandardOutput "$Output\$Name.stdout.log" -RedirectStandardError "$Output\$Name.stderr.log"
    $PeakWorking=0L; $PeakPrivate=0L
    $Deadline=[Diagnostics.Stopwatch]::StartNew()
    while (-not $Process.WaitForExit(100)) {
        if ($Deadline.Elapsed.TotalSeconds -gt $(if ($Neural) { 1800 } else { 120 })) { Stop-Process -Id $Process.Id; throw "Native check timed out: $Name" }
        $Process.Refresh()
        if (-not $Process.HasExited) {
            $PeakWorking=[Math]::Max($PeakWorking,$Process.PeakWorkingSet64)
            $PeakPrivate=[Math]::Max($PeakPrivate,$Process.PrivateMemorySize64)
        }
    }
    $MemoryReport.Add([PSCustomObject]@{check=$Name;peakWorkingMB=[Math]::Round($PeakWorking/1MB,1);peakPrivateMB=[Math]::Round($PeakPrivate/1MB,1)})
    $MemoryReport | ConvertTo-Json | Set-Content "$Output\memory.json" -Encoding utf8
    if ($Process.ExitCode -ne 0) { throw "Failed native check: $Name ($($Process.ExitCode))" }
}
$SavedPath=$env:PATH
$SavedPlatform=$env:QT_QPA_PLATFORM
$SavedPlugins=$env:QT_PLUGIN_PATH
try {
    $env:PATH="$env:WINDIR\System32;$env:WINDIR"
    $env:QT_QPA_PLATFORM='offscreen'
    $env:QT_PLUGIN_PATH=$null
    $Wave=Join-Path $Output 'tone.wav'
    & "$AppDirectory\tools\ffmpeg.exe" -hide_banner -loglevel error -y -f lavfi -i 'sine=frequency=220:duration=6:sample_rate=44100' -ac 2 $Wave
    if ($LASTEXITCODE -ne 0) { throw 'Bundled FFmpeg failed' }
    Run-Native @('--smoke-test',"$Output\ui") 'ui'
    Run-Native @('--reliability-smoke','--result',"$Output\reliability.json") 'reliability'
    Run-Native @('--playback-smoke',$Wave,'--result',"$Output\playback.json") 'playback'
    Run-Native @('--lyrics-save-smoke',$Wave,'--result',"$Output\lyrics-save.json") 'lyrics-save'
    Run-Native @('--cover-export-smoke',$Wave,'--result',"$Output\cover-export.json") 'cover-export'
    $RhythmWave=Join-Path $Output 'rhythm-history.wav'
    & "$AppDirectory\tools\ffmpeg.exe" -hide_banner -loglevel error -y -f lavfi -i 'aevalsrc=sin(2*PI*130*t)*exp(-45*mod(t\,if(lt(t\,8)\,1\,1/3)))*lt(mod(t\,if(lt(t\,8)\,1\,1/3))\,0.12):s=11025:d=16' $RhythmWave
    if ($LASTEXITCODE -ne 0) { throw 'Rhythm fixture generation failed' }
    Run-Native @('--diagnose-cover-rhythm',$RhythmWave,'--result',"$Output\rhythm-history.json",'--cover-image',"$Output\rhythm-history.png") 'rhythm-history'
    $Rhythm=Get-Content "$Output\rhythm-history.json" -Raw | ConvertFrom-Json
    $Slow=$Rhythm.timeline | Sort-Object { [Math]::Abs($_.seconds-4) } | Select-Object -First 1
    $Fast=$Rhythm.timeline | Sort-Object { [Math]::Abs($_.seconds-12) } | Select-Object -First 1
    if ($Slow.pace -ge .45 -or $Fast.pace -le .72) { throw 'Cover colors did not follow the slow-to-fast transition' }
    Run-Native @('--sound-smoke',$Wave,'--result',"$Output\sound.json") 'sound'
    Run-Native @('--close-smoke','--result',"$Output\close.json") 'close'
    $Close=Get-Content "$Output\close.json" -Raw | ConvertFrom-Json
    if (-not $Close.complete -or -not $Close.task_finished -or $Close.milliseconds -ge 3000) { throw 'Closing left background work running' }
    Run-Native @('--diagnose-audio',$Wave,'--result',"$Output\analysis.json") 'analysis'
    $Analysis=Get-Content "$Output\analysis.json" -Raw | ConvertFrom-Json
    if (-not $Analysis.ffmpeg.StartsWith($AppDirectory.Replace('\','/'),[StringComparison]::OrdinalIgnoreCase)) { throw 'FFmpeg resolved outside the bundle' }
    $BundlePrefix = $AppDirectory.Replace('\','/').TrimEnd('/')
    if ($Analysis.plugins | Where-Object { $_.TrimEnd('/') -ine $BundlePrefix -and -not $_.StartsWith($BundlePrefix+'/', [StringComparison]::OrdinalIgnoreCase) }) { throw 'Qt plugin search path points outside the bundle' }
    $Forbidden=Get-ChildItem -LiteralPath $AppDirectory -Recurse -File | Where-Object { $_.Extension -in '.py','.pyc','.pyd' -or $_.Name -match '^python.*\.dll$' }
    if ($Forbidden) { throw 'Python runtime present in native app' }
    if ($Neural) {
        $Speech=Join-Path $Output 'speech.wav'
        $Voice=New-Object -ComObject SAPI.SpVoice
        foreach ($Candidate in $Voice.GetVoices()) { if ($Candidate.GetAttribute('Language') -match '409') { $Voice.Voice=$Candidate; break } }
        $Stream=New-Object -ComObject SAPI.SpFileStream
        $Stream.Open($Speech,3,$false)
        $Voice.AudioOutputStream=$Stream
        [void]$Voice.Speak('The morning sun is shining through the window. We hear the music and we sing together.')
        $Stream.Close()
        $Text=Join-Path $Output 'supplied.txt'
        Set-Content -LiteralPath $Text -Encoding UTF8 -Value "The morning sun`nis shining through the window.`nWe hear the music`nand we sing together."
        Run-Native @('--speech-worker','--ctc-direct','--audio',$Speech,'--model',"$AppDirectory\models\ggml-large-v3-q5_0.bin",'--language','en','--align',$Text,'--result',"$Output\alignment.json") 'alignment'
        $Alignment=Get-Content "$Output\alignment.json" -Raw | ConvertFrom-Json
        $Expected=@('The morning sun','is shining through the window.','We hear the music','and we sing together.')
        if ($Alignment.lines.Count -ne 4) { throw 'Line alignment did not preserve four supplied lines' }
        for ($i=0;$i -lt 4;$i++) {
            if ($Alignment.lines[$i].text -ne $Expected[$i]) { throw 'Alignment replaced supplied words' }
            if ($i -gt 0 -and $Alignment.lines[$i].start -le $Alignment.lines[$i-1].start) { throw 'Word alignment collapsed timestamps' }
        }
        New-Item -ItemType Directory -Path "$Output\stems" -Force | Out-Null
        Run-Native @('--stems-worker','--audio',$Speech,'--model',"$AppDirectory\models\ggml-model-htdemucs-4s-f16.bin",'--segment-seconds','3','--out',"$Output\stems") 'stems'
        foreach ($Stem in @('vocals','drums','bass','other')) {
            if ((Get-Item "$Output\stems\$Stem.wav").Length -lt 1000) { throw "Invalid stem: $Stem" }
        }
    }
    Write-Host 'Native bundle passed with a system-only PATH and no Python runtime.'
} finally {
    $env:PATH=$SavedPath
    $env:QT_QPA_PLATFORM=$SavedPlatform
    $env:QT_PLUGIN_PATH=$SavedPlugins
}
