#Requires -RunAsAdministrator
<#
    Uninstall-AutoHostUpdate.ps1
    Удаляет задачу 'AutoHostUpdate' из Планировщика задач.

    Использование:
      powershell.exe -ExecutionPolicy Bypass -File Uninstall-AutoHostUpdate.ps1
#>

# ---------- Параметры ----------
# Параметров нет: скрипт только удаляет задачу.

# Имя задачи в Планировщике задач.
$TaskName = "AutoHostUpdate"

# Вспомогательная функция вывода сообщений с префиксом "==>".
function Write-Info { param([string]$m) Write-Host "==> $m" }

# ---------- Проверка прав администратора ----------
# Управление задачами Планировщика требует повышенных прав.
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Нужны права администратора для удаления задачи Планировщика."
}

# ---------- Поиск задачи ----------
# Сначала проверяем, зарегистрирована ли задача, чтобы не показывать ошибку "не найдена".
Write-Info "Поиск задачи '$TaskName'..."
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "Задача '$TaskName' не существует - удалять нечего."
    exit 0
}

# ---------- Удаление задачи ----------
# Выводим параметры найденной задачи для диагностики.
Write-Info "Задача найдена. Удаляю..."
Write-Host "  Состояние: $($task.State), путь: $($task.TaskPath)"
Write-Host "  Действие: $($task.Actions.Execute) $($task.Actions.Arguments)"

try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    Write-Info "Задача '$TaskName' удалена."
} catch {
    throw "Не удалось удалить задачу '$TaskName': $($_.Exception.Message)"
}
