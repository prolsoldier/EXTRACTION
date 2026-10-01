# Makes Inter the system-wide UI font (replaces Segoe UI) on Windows 10/11.
# Needs admin. Run in an elevated PowerShell: Set-ExecutionPolicy -Scope Process Bypass; .\install-system-font.ps1
# Undo anytime with restore-system-font.ps1. Sign out/in (or reboot) to apply.
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Error 'Run this as Administrator.'; exit 1 }
$src  = Join-Path $PSScriptRoot 'inter'
$dest = "$env:windir\Fonts"
$reg  = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts'
Get-ChildItem $src -Filter *.ttf | ForEach-Object {
  Copy-Item $_.FullName "$dest\$($_.Name)" -Force
  New-ItemProperty -Path $reg -Name ($_.BaseName + ' (TrueType)') -Value $_.Name -PropertyType String -Force | Out-Null
}
reg export 'HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\FontSubstitutes' "$PSScriptRoot\fontsubstitutes-backup.reg" /y | Out-Null
$sub = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\FontSubstitutes'
New-ItemProperty -Path $sub -Name 'Segoe UI' -Value 'Inter' -PropertyType String -Force | Out-Null
Write-Host 'Done. Sign out and back in to see it.'
