# Windows Task Scheduler'a mail_filter'i kaydeder (varsayilan: her 15 dakikada bir).
# Calistir:  PowerShell -ExecutionPolicy Bypass -File .\setup_scheduler.ps1

param(
    [int]$IntervalMinutes = 15,
    [string]$TaskName = "MailFilter"
)

$ErrorActionPreference = "Stop"
$dir = $PSScriptRoot

# Python yolunu bul
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) {
    Write-Error "Python bulunamadi. Once Python kur: https://www.python.org/downloads/"
    exit 1
}
Write-Host "Python: $python"

$script = Join-Path $dir "mail_filter.py"

# Pencere acilmadan calissin diye pythonw varsa onu kullan
$pythonw = $python -replace "python\.exe$", "pythonw.exe"
if (Test-Path $pythonw) { $python = $pythonw }

$action = New-ScheduledTaskAction -Execute $python -Argument "`"$script`"" -WorkingDirectory $dir

# Gunluk tetikleyici + gun boyu tekrar. ('-Once' tetikleyici tekrar suresi
# tanimsiz oldugunda gorev calistiktan sonra otomatik SILINIYOR; gunluk olan silinmez.)
$trigger = New-ScheduledTaskTrigger -Daily -At 7am
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At 7am `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 1)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

# Var olan gorevi temizle
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Gelen mailleri ozetler, onemliyse Telegram bildirimi gonderir." | Out-Null

Write-Host ""
Write-Host "[OK] '$TaskName' gorevi kuruldu - her $IntervalMinutes dakikada bir calisacak." -ForegroundColor Green
Write-Host ""
Write-Host "Yararli komutlar:"
Write-Host "  Hemen calistir : Start-ScheduledTask -TaskName $TaskName"
Write-Host "  Durdur/sil     : Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
Write-Host "  Durumu gor     : Get-ScheduledTask -TaskName $TaskName"
