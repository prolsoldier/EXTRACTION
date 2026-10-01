# Installs JetBrains Mono for the current user (no admin needed) and sets it
# as the default font in Windows Terminal. Run: right-click > Run with PowerShell
$src  = Join-Path $PSScriptRoot 'ttf'
$dest = "$env:LOCALAPPDATA\Microsoft\Windows\Fonts"
New-Item -ItemType Directory -Force $dest | Out-Null
$reg = 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts'
Get-ChildItem $src -Filter *.ttf | ForEach-Object {
    $target = Join-Path $dest $_.Name
    Copy-Item $_.FullName $target -Force
    New-ItemProperty -Path $reg -Name ($_.BaseName + ' (TrueType)') -Value $target -PropertyType String -Force | Out-Null
}
Write-Host 'Font installed.'

# Windows Terminal default font
$paths = @(
  "$env:LOCALAPPDATA\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json",
  "$env:LOCALAPPDATA\Packages\Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe\LocalState\settings.json",
  "$env:LOCALAPPDATA\Microsoft\Windows Terminal\settings.json"
)
foreach ($p in $paths) {
  if (Test-Path $p) {
    Copy-Item $p "$p.bak" -Force
    $j = (Get-Content $p -Raw) | ConvertFrom-Json
    if (-not $j.profiles.defaults) { $j.profiles | Add-Member -NotePropertyName defaults -NotePropertyValue ([pscustomobject]@{}) }
    $j.profiles.defaults | Add-Member -NotePropertyName font -NotePropertyValue ([pscustomobject]@{ face = 'JetBrains Mono'; size = 12 }) -Force
    $j | ConvertTo-Json -Depth 20 | Set-Content $p
    Write-Host "Windows Terminal font set (backup: $p.bak)"
  }
}
Write-Host 'Done. Restart your apps. For VS Code: set editor.fontFamily to "JetBrains Mono".'
