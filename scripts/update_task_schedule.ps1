# Update Tennis Morning Update task to run at 17:00 (5 PM) instead of 7:00 AM
# Run as Administrator

$taskName = "Tennis Morning Update"
Write-Host "Updating $taskName to run at 17:00..."

$task = Get-ScheduledTask -TaskName $taskName
$trigger = New-ScheduledTaskTrigger -Daily -At 17:00
Set-ScheduledTask -TaskName $taskName -Trigger $trigger

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "✓ Task updated. Next run: $($info.NextRunTime)"
