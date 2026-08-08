#Requires -RunAsAdministrator
<#
    Install-AutoHostUpdate.ps1
    Создаёт задачу в Планировщике задач для автозапуска AutoHostUpdate.ps1
    при входе в систему с правами администратора.

    Параметры:
      -ScriptPath  путь к AutoHostUpdate.ps1 (по умолчанию - рядом с этим файлом)
      -Uninstall  удалить задачу вместо установки
#>

# ---------- Параметры ----------
# -ScriptPath: явный путь к основному скрипту; -Uninstall: режим удаления задачи.
[CmdletBinding()]
param(
    [string]$ScriptPath = "",
    [switch]$Uninstall
)

# Имя задачи в Планировщике задач.
$TaskName = "AutoHostUpdate"

# Вспомогательная функция вывода сообщений с префиксом "==>".
function Write-Info { param([string]$m) Write-Host "==> $m" }

# ---------- Определяем путь к основному скрипту ----------
# Если путь не передан, берём AutoHostUpdate.ps1 из папки рядом с этим файлом.
if (-not $ScriptPath) {
    $ScriptPath = Join-Path $PSScriptRoot "AutoHostUpdate.ps1"
}
$ScriptPath = [System.IO.Path]::GetFullPath($ScriptPath)
Write-Info "Путь к основному скрипту: $ScriptPath"

# ---------- Режим удаления ----------
# Удаляем задачу из Планировщика, если она есть; отсутствие задачи не считается ошибкой.
if ($Uninstall) {
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Info "Задача '$TaskName' удалена."
    } catch {
        if ($_.Exception.Message -match "not found|не найден") {
            Write-Host "Задача '$TaskName' не существует - удалять нечего."
        } else {
            throw
        }
    }
    exit 0
}

# ---------- Проверка основного скрипта ----------
# Прежде чем создавать задачу, убеждаемся, что целевой скрипт существует.
if (-not (Test-Path -LiteralPath $ScriptPath)) {
    throw "Не найден скрипт: $ScriptPath. Укажите -ScriptPath."
}
Write-Info "Скрипт найден: $ScriptPath"

# ---------- Аргумент действия ----------
# Запуск powershell.exe со скрытым окном и обходом политики выполнения.
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $ScriptPath)
Write-Host "  действие: powershell.exe $($action.Arguments)"

# ---------- Триггер при входе ----------
# Задача срабатывает при входе пользователя в систему.
$trigger = New-ScheduledTaskTrigger -AtLogOn
Write-Host "  триггер: при входе (AtLogOn)"

# ---------- Настройки ----------
# Выполнение от батареи, запуск после пропуска расписания, без ограничения времени.
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
Write-Host "  настройки: от батареи, StartWhenAvailable, без лимита времени"

# ---------- Права (администратор) ----------
# Задача выполняется от имени текущего пользователя с максимальными правами.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest
Write-Host "  права: $env:USERDOMAIN\$env:USERNAME (Interactive, Highest)"

# ---------- Создание задачи ----------
# -Force: перезаписывает задачу с тем же именем, если она уже существует.
Write-Info "Регистрирую задачу '$TaskName'..."
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force

Write-Info "Задача '$TaskName' создана."
Write-Info "Скрипт: $ScriptPath"
Write-Info "Запуск: при входе пользователя $env:USERNAME с правами администратора."