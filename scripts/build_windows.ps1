param([string]$FfmpegRoot='C:\ffmpeg', [int]$Jobs=2)
$ErrorActionPreference='Stop'
& (Join-Path $PSScriptRoot 'build_native.ps1') -Deploy -Installer -Portable -FfmpegRoot $FfmpegRoot -Jobs $Jobs
