# Registers Ascent notification tasks in Windows Task Scheduler (current user).
# Idempotent: re-running replaces existing tasks. Remove with unregister_tasks.ps1.
$ErrorActionPreference = 'Stop'

$py = Join-Path $PSScriptRoot '..\.venv\Scripts\pythonw.exe'
if (-not (Test-Path $py)) { $py = (Get-Command pythonw.exe).Source }

$script = (Resolve-Path (Join-Path $PSScriptRoot '..\notifier.py')).Path
$dir = Split-Path $script

function New-AscentTask($name, $arg, $time) {
  Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
  $action = New-ScheduledTaskAction -Execute $py -Argument "`"$script`" $arg" -WorkingDirectory $dir
  $trigger = New-ScheduledTaskTrigger -Daily -At $time
  $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
  Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Description 'Ascent career tracker notification' | Out-Null
  Write-Host "registered: $name @ $time"
}

New-AscentTask 'Ascent Morning Digest' '--digest' '8:00AM'
New-AscentTask 'Ascent Due Check'      '--due'    '12:30PM'

# Day-plan block nudges: every 5 min from 07:00 for 14 h (toasts block starts + hard stop)
$name = 'Ascent Block Nudge'
Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute $py -Argument "`"$script`" --blocks" -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -Once -At '7:00AM' -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Hours 14)
$trigger.Repetition.StopAtDurationEnd = $false
$daily = New-ScheduledTaskTrigger -Daily -At '7:00AM'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $name -Action $action -Trigger @($trigger, $daily) -Settings $settings -Description 'Ascent day-plan block toasts' | Out-Null
Write-Host "registered: $name every 5 min from 7:00AM"
Write-Host 'DONE'
