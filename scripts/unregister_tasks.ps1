# Removes the Ascent notification tasks.
$ErrorActionPreference = 'SilentlyContinue'
foreach ($n in 'Ascent Morning Digest', 'Ascent Due Check') {
  Unregister-ScheduledTask -TaskName $n -Confirm:$false
  Write-Host "removed: $n"
}
