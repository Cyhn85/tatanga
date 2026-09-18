$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\TATANGA Hub.lnk")
$Shortcut.TargetPath = "$env:USERPROFILE\Desktop\tatanga\T11_HUB\start_hub.bat"
$Shortcut.WorkingDirectory = "$env:USERPROFILE\Desktop\tatanga\T11_HUB"
$Shortcut.Description = "TATANGA Hub - CSS Berlin Komuta Merkezi"
$Shortcut.Save()
Write-Host "Masaustu kisayolu olusturuldu: TATANGA Hub.lnk"
