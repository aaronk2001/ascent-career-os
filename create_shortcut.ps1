# Recreates the Desktop Ascent.lnk. Run once after the .venv is created:
#   powershell -ExecutionPolicy Bypass -File .\create_shortcut.ps1
#
# Points at ascent.vbs (windowless) rather than pythonw.exe directly, so the
# venv-vs-Store-Python choice lives in one place and the shortcut keeps working
# if the .venv is ever deleted.
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Ascent.lnk'))
$lnk.TargetPath       = "$env:SystemRoot\System32\wscript.exe"
$lnk.Arguments        = "`"$dir\ascent.vbs`""
$lnk.WorkingDirectory = $dir
$lnk.WindowStyle      = 7
$lnk.IconLocation     = "$dir\ascent.ico"
$lnk.Save()
Write-Host "Shortcut saved: $([Environment]::GetFolderPath('Desktop'))\Ascent.lnk -> $dir\ascent.vbs"
