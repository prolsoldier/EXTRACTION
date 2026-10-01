# Puts Segoe UI back. Run as Administrator, then sign out/in.
Remove-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\FontSubstitutes' -Name 'Segoe UI' -ErrorAction SilentlyContinue
Write-Host 'Restored. Sign out and back in.'
