param([string]$Application='dist\SonicForge\SonicForge.exe', [string]$Models='build\native-models', [switch]$Full)
$ErrorActionPreference='Stop'
$Root=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root
$Application=[IO.Path]::GetFullPath((Join-Path $Root $Application))
$Models=[IO.Path]::GetFullPath((Join-Path $Root $Models))
$Output=Join-Path $Root 'validation\lyrics-quality'
New-Item -ItemType Directory -Path $Output -Force | Out-Null
$Ffmpeg=Join-Path $Root 'dist\SonicForge\tools\ffmpeg.exe'
$Cases=@(
    @{language='ru';code='419';phrases=@('Сегодня утром солнце освещает тихую улицу.','Мы слушаем музыку и поём вместе.','Каждое слово должно остаться на своём месте.')},
    @{language='en';code='409';phrases=@('The morning sun is shining through the window.','We listen to the music and we sing together.','Every single word should stay in the right place.')}
)
$Report=[Collections.Generic.List[object]]::new()
function Run-Worker([string[]]$Arguments,[string]$Name) {
    $Quoted=foreach($Argument in $Arguments){'"'+$Argument.Replace('"','\"')+'"'}
    $Process=Start-Process -FilePath $Application -ArgumentList $Quoted -WindowStyle Hidden -PassThru -RedirectStandardError "$Output\$Name.log"
    $Peak=0L
    while(-not $Process.WaitForExit(100)){
        $Process.Refresh()
        if(-not $Process.HasExited){$Peak=[Math]::Max($Peak,$Process.PeakWorkingSet64)}
    }
    if($Process.ExitCode -ne 0){throw "Speech check failed: $Name. See $Output\$Name.log"}
    return [Math]::Round($Peak/1MB,1)
}
function Words([string]$Text) {
    $Text=[regex]::Replace($Text.ToLowerInvariant().Replace('ё','е'),'[^\p{L}\p{N}]+',' ').Trim()
    return @($Text.Split(' ',[StringSplitOptions]::RemoveEmptyEntries))
}
function Word-Error([string]$Expected,[string]$Actual) {
    $Reference=Words $Expected; $Hypothesis=Words $Actual
    $Previous=New-Object int[] ($Hypothesis.Count+1)
    for($j=0;$j -le $Hypothesis.Count;$j++){$Previous[$j]=$j}
    for($i=1;$i -le $Reference.Count;$i++){
        $Current=New-Object int[] ($Hypothesis.Count+1); $Current[0]=$i
        for($j=1;$j -le $Hypothesis.Count;$j++){
            $Substitution=$Previous[$j-1]+[int]($Reference[$i-1] -ne $Hypothesis[$j-1])
            $Current[$j]=[Math]::Min($Substitution,[Math]::Min($Previous[$j]+1,$Current[$j-1]+1))
        }
        $Previous=$Current
    }
    return $Previous[$Hypothesis.Count]/[Math]::Max(1,$Reference.Count)
}
foreach($Case in $Cases){
    $Language=$Case.language
    $Voice=New-Object -ComObject SAPI.SpVoice
    $Selected=@($Voice.GetVoices() | Where-Object {$_.GetAttribute('Language') -match $Case.code})
    if(-not $Selected.Count){throw "Install a Windows SAPI voice for $Language to run this check"}
    $Voice.Voice=$Selected[0]
    $Onsets=@(12.,22.4,42.4)
    $Arguments=@('-hide_banner','-v','error','-y')
    $Filters=@()
    for($i=0;$i -lt 3;$i++){
        $Raw=Join-Path $Output "$Language-$i-raw.wav"
        $Clean=Join-Path $Output "$Language-$i.wav"
        $Stream=New-Object -ComObject SAPI.SpFileStream
        $Stream.Open($Raw,3,$false);$Voice.AudioOutputStream=$Stream
        [void]$Voice.Speak($Case.phrases[$i]);$Stream.Close()
        & $Ffmpeg -v error -y -i $Raw -af 'silenceremove=start_periods=1:start_duration=0.01:start_threshold=-45dB' -ac 1 -ar 16000 $Clean
        if($LASTEXITCODE -ne 0){throw 'SAPI fixture preparation failed'}
        $Arguments+=@('-i',$Clean)
        $Filters+="[$($i):a]adelay=$([int]($Onsets[$i]*1000)):all=1[a$i]"
    }
    $Wave=Join-Path $Output "$Language.wav"
    $Filters+='[a0][a1][a2]amix=inputs=3:normalize=0,apad,atrim=duration=50[out]'
    & $Ffmpeg @Arguments -filter_complex ($Filters -join ';') -map '[out]' -ac 1 -ar 16000 $Wave
    if($LASTEXITCODE -ne 0){throw 'Timed fixture preparation failed'}
    $Text=Join-Path $Output "$Language.txt"
    $Case.phrases | Set-Content -LiteralPath $Text -Encoding utf8
    $Result=Join-Path $Output "$Language-alignment.json"
    $Peak=Run-Worker @('--speech-worker','--ctc-only','--audio',$Wave,'--model',"$Models\ggml-large-v3-q5_0.bin",'--language',$Language,'--align',$Text,'--result',$Result) "$Language-alignment"
    $Lines=(Get-Content $Result -Raw|ConvertFrom-Json).lines
    if($Lines.Count -ne 3){throw 'CTC lost supplied lines'}
    $Errors=@()
    for($i=0;$i -lt 3;$i++){
        if($Lines[$i].text -ne $Case.phrases[$i]){throw 'CTC replaced supplied words'}
        $Errors+=[Math]::Abs(($Lines[$i].start+.045)-$Onsets[$i])
    }
    $Maximum=($Errors|Measure-Object -Maximum).Maximum
    $Report.Add([PSCustomObject]@{language=$Language;check='alignment';maxOnsetErrorSeconds=[Math]::Round($Maximum,3);peakWorkingMB=$Peak})
    if($Maximum -gt .35){throw "CTC onset error exceeds 350 ms: $Language"}
    if($Full){
        $Result=Join-Path $Output "$Language-recognition.json"
        $Peak=Run-Worker @('--speech-worker','--audio',$Wave,'--model',"$Models\ggml-large-v3-q5_0.bin",'--language',$Language,'--result',$Result) "$Language-recognition"
        $Lines=(Get-Content $Result -Raw|ConvertFrom-Json).lines
        $ErrorRate=Word-Error ($Case.phrases -join ' ') (($Lines|ForEach-Object text)-join ' ')
        $Report.Add([PSCustomObject]@{language=$Language;check='recognition';wordErrorRate=$ErrorRate;peakWorkingMB=$Peak})
        if($ErrorRate -gt .25){throw "Recognition word error rate exceeds 25%: $Language"}
    }
    $Report|ConvertTo-Json|Set-Content "$Output\summary.json" -Encoding utf8
}
$Report|Format-Table
