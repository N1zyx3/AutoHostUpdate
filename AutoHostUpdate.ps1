#Requires -RunAsAdministrator
<#
    AutoHostUpdate.ps1
    Проверяет обновления именованных групп в hosts по маякам из сетевого источника.
    Обновляет только те именованные группы, которые уже есть в локальном hosts.
    Лог: %TEMP%\AutoHostUpdate.log
#>

# ---------- Параметры командной строки ----------
# -Quiet: подавляет модальное окно ошибок (используется при запуске по расписанию).
# Уведомления-пузыри в трее показываются всегда, независимо от -Quiet.
[CmdletBinding()]
param(
    [switch]$Quiet
)

# ---------- Конфигурация ----------
# URL источника данных (файл hosts проекта GeoHideDNS). Читается при каждом запуске, локально не хранится.
$SourceUrl      = "https://raw.githubusercontent.com/Internet-Helper/GeoHideDNS/refs/heads/main/hosts/hosts"
# Путь к системному файлу hosts.
$HostsPath      = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"
# Каталоги лога и резервных копий (оба в %TEMP%).
$LogDir         = $env:TEMP
$LogFile        = Join-Path $LogDir "AutoHostUpdate.log"
$BackupDir      = Join-Path $LogDir "AutoHostUpdate_backups"
# Префикс строки-маркера даты обновления (тот же, что в строке 2 источника).
$MarkerPrefix   = "Последнее обновление:"
# Имя глобального мутекса, запрещающего параллельные запуски скрипта.
$SingleRunMutex = "Global\AutoHostUpdate_RunOnce"
# Показывать ли диалоговые окна ошибок.
$SkipDialogs    = [bool]$Quiet

# ---------- Лог ----------
# Дописывает строку с меткой времени в лог-файл. Ошибки записи в лог не критичны.
function Write-Log {
    param([string]$Message)
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    try { Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8 } catch { }
}

# ---------- Диалог ошибки ----------
# Показывает модальное WinForms-окно с текстом ошибки и кнопкой открытия лога.
function Show-ErrorDialog {
    param([string]$Message)
    $ErrorLog = $LogFile
    try {
        # Подключаем сборки Windows Forms и GDI+ для построения окна.
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        Add-Type -AssemblyName System.Drawing -ErrorAction Stop
        $form = New-Object System.Windows.Forms.Form
        $form.Text        = "AutoHostUpdate - ошибка"
        $form.Size        = New-Object System.Drawing.Size(560, 260)
        # Фиксированный размер окна: нельзя свернуть/развернуть.
        $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
        $form.MaximizeBox  = $false
        $form.MinimizeBox  = $false
        # Позиционируем окно по центру экрана.
        $form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen

        # Текст ошибки и путь к логу для кнопки "Открыть лог".
        $label = New-Object System.Windows.Forms.Label
        $label.Location = New-Object System.Drawing.Point(20, 20)
        $label.Size    = New-Object System.Drawing.Size(500, 100)
        $label.AutoSize = $false
        $label.Text     = $Message + "`r`n`r`nЛог: $ErrorLog"
        $form.Controls.Add($label)

        # Кнопка "Открыть лог" запускает блокнот с файлом лога.
        $btnLog = New-Object System.Windows.Forms.Button
        $btnLog.Text     = "Открыть лог"
        $btnLog.Location = New-Object System.Drawing.Point(20, 140)
        $btnLog.Size     = New-Object System.Drawing.Size(140, 35)
        $btnLog.Add_Click({ try { Start-Process notepad.exe $ErrorLog } catch { } })
        $form.Controls.Add($btnLog)

        # Кнопка "OK" закрывает окно.
        $btnOk = New-Object System.Windows.Forms.Button
        $btnOk.Text     = "OK"
        $btnOk.Location = New-Object System.Drawing.Point(170, 140)
        $btnOk.Size     = New-Object System.Drawing.Size(90, 35)
        $btnOk.DialogResult = [System.Windows.Forms.DialogResult]::OK
        $form.Controls.Add($btnOk)

        # Enter = нажатие "OK"; ShowDialog делает окно модальным.
        $form.AcceptButton = $btnOk
        [void]$form.ShowDialog()
    } catch {
        # Если окно построить не удалось — хотя бы логируем это.
        Write-Log "Не удалось показать окно ошибки: $($_.Exception.Message)"
    }
}

# ---------- Уведомление ----------
# Показывает неблокирующий "пузырь" (balloon) в области уведомлений Windows.
# Вызывается при каждом завершении работы (обновлён / не требуется / ошибка).
function Show-Notification {
    param(
        [string]$Title,
        [string]$Message,
        [string]$Kind = "Info"   # Info | Warning | Error
    )
    try {
        # Подключаем сборки Windows Forms и GDI+ для построения пузыря.
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        Add-Type -AssemblyName System.Drawing -ErrorAction Stop
        $tip = New-Object System.Windows.Forms.NotifyIcon
        # Иконка пузыря зависит от типа уведомления.
        switch ($Kind) {
            "Warning" { $tip.Icon = [System.Drawing.SystemIcons]::Warning;       $iconType = [System.Windows.Forms.ToolTipIcon]::Warning }
            "Error"   { $tip.Icon = [System.Drawing.SystemIcons]::Error;         $iconType = [System.Windows.Forms.ToolTipIcon]::Error }
            default   { $tip.Icon = [System.Drawing.SystemIcons]::Information;   $iconType = [System.Windows.Forms.ToolTipIcon]::Info }
        }
        $tip.Visible = $true
        $tip.ShowBalloonTip(20000, $Title, $Message, $iconType)
        # Пузырь показывается асинхронно; держим объект живым несколько секунд, затем убираем.
        Start-Sleep -Milliseconds 4500
        $tip.Visible = $false
        $tip.Dispose()
    } catch {
        # Если уведомление показать не удалось — хотя бы логируем.
        Write-Log "Не удалось показать уведомление: $($_.Exception.Message)"
    }
}

# ---------- Аварийный выход ----------
# Логирует ошибку, всегда шлёт уведомление и завершает скрипт.
# Без -Quiet дополнительно показывает модальное окно с кнопкой "Открыть лог".
function Fail-WithError {
    param([string]$Message)
    Write-Log "ОШИБКА: $Message"
    # Уведомление об ошибке показываем всегда (пузырь не зависит от -Quiet).
    Show-Notification "AutoHostUpdate - ошибка" $Message "Error"
    if (-not $SkipDialogs) {
        try { Write-Error $Message } catch { }
        Show-ErrorDialog $Message
    }
    exit 1
}

# ---------- Парсинг ----------
# Разбивает строки на блоки: блок = группа строк, разделённая пустыми строками.
function Split-Blocks {
    param([string[]]$Lines)
    $blocks = @()
    $current = New-Object System.Collections.Generic.List[string]
    foreach ($ln in $Lines) {
        if ($null -eq $ln) { $ln = "" }
        # Пустая строка закрывает текущий блок (если он не пустой).
        if ($ln.Trim() -eq "") {
            if ($current.Count -gt 0) {
                $blocks += , @($current.ToArray())
                $current = New-Object System.Collections.Generic.List[string]
            }
        } else {
            # Убираем только хвостовые пробелы, сохраняя отступы слева.
            $current.Add($ln.TrimEnd())
        }
    }
    # Последний блок, если после него не было пустой строки.
    if ($current.Count -gt 0) { $blocks += , @($current.ToArray()) }
    return , $blocks
}

# Возвращает именованные группы: pscustomobject @{ Name; Raw }
# Группа считается именованной, если её первая строка начинается с "#" и
# внутри блока есть хотя бы одна строка-запись (не комментарий). Блоки
# только-из-комментариев (заголовок источника, # GitHub Copilot) игнорируются.
function Get-NamedGroups {
    param([object[]]$Blocks)
    $groups = @()
    foreach ($blk in $Blocks) {
        $first = $blk[0]
        # Первая строка блока должна быть заголовком (начинаться с "#").
        if ($first -notmatch "^#") { continue }
        # Проверяем, есть ли в блоке хотя бы одна не-комментарий запись.
        $hasEntry = $false
        foreach ($ln in $blk) {
            if ($ln -notmatch "^\s*#") { $hasEntry = $true; break }
        }
        # Блок сугубо из комментариев пропускаем.
        if (-not $hasEntry) { continue }
        # Имя группы = первая строка без "#" и лишних пробелов.
        $name = $first.TrimStart('#', ' ').Trim()
        if ($name -eq "") { continue }
        $groups += [pscustomobject]@{ Name = $name; Raw = $blk }
    }
    return , $groups
}

# ---------- Работа с источником ----------
# Скачивает файл-источник, извлекает дату обновления и именованные группы.
function Get-SourceData {
    $content = (Invoke-WebRequest -Uri $SourceUrl -UseBasicParsing -TimeoutSec 60 -ErrorAction Stop).Content
    # Нормализуем переводы строк: CRLF -> LF.
    $content = $content -replace "`r`n", "`n"
    $lines = $content -split "`n"
    if ($lines.Count -lt 2) { throw "Файл источника слишком короткий или пуст." }

    # Дата обновления — строка 2 источника вида "# Последнее обновление: <дата>".
    # Сравнивается как сырая строка, без парсинга в дату.
    $escapeMarker = [regex]::Escape($MarkerPrefix)
    $dateValue = ""
    if ($lines[1] -match "^#\s*$escapeMarker\s*(.*)$") {
        $dateValue = $matches[1].Trim()
    } else {
        Write-Log "Предупреждение: не найдена строка '$MarkerPrefix' во 2-й строке источника."
    }

    $blocks = Split-Blocks $lines
    $groups = Get-NamedGroups $blocks
    return [pscustomobject]@{ DateValue = $dateValue; Groups = $groups }
}

# ---------- Работа с локальным hosts ----------
# Читает локальный hosts, нормализует переводы строк, убирает последнюю пустую строку.
function Read-HostsLines {
    if (-not (Test-Path -LiteralPath $HostsPath)) { throw "Файл hosts не найден: $HostsPath" }
    # ReadAllText корректно декодирует UTF-8 (в т.ч. с BOM).
    $raw = [System.IO.File]::ReadAllText($HostsPath)
    $raw = $raw -replace "`r`n", "`n"
    $lines = $raw -split "`n"
    # Отбрасываем финальную пустую строку, которую даёт split.
    if ($lines.Count -gt 0 -and $lines[$lines.Count - 1] -eq "") {
        $lines = $lines[0..($lines.Count - 2)]
    }
    return , $lines
}

# Ищет в локальном hosts строку-маркер "# Последнее обновление: ..." и возвращает дату.
function Get-MarkerDate {
    param([string[]]$Lines)
    $escapeMarker = [regex]::Escape($MarkerPrefix)
    foreach ($ln in $Lines) {
        if ($ln -match "^#\s*$escapeMarker\s*(.*)$") {
            return $matches[1].Trim()
        }
    }
    return ""
}

# Полная замена именованных групп в локальном hosts по маякам (заголовок + записи).
# Возвращает [pscustomobject]@{ Lines = [string[]]; Changed = int }.
function Update-GroupsLines {
    param([string[]]$LocalLines, [object[]]$SourceGroups)

    # Словарь "имя группы -> блок" для быстрого поиска групп из источника.
    $groupsByName = @{}
    foreach ($g in $SourceGroups) { $groupsByName[$g.Name] = $g.Raw }

    $blocks = Split-Blocks $LocalLines
    $out = New-Object System.Collections.Generic.List[string]
    $changed = 0

    foreach ($blk in $blocks) {
        $first = $blk[0]
        # Определяем, является ли блок именованной группой (логика как в Get-NamedGroups).
        $isNamed = $false
        $name = ""
        if ($first -match "^#") {
            $hasEntry = $false
            foreach ($ln in $blk) {
                if ($ln -notmatch "^\s*#") { $hasEntry = $true; break }
            }
            if ($hasEntry) {
                $name = $first.TrimStart('#', ' ').Trim()
                if ($name -ne "") { $isNamed = $true }
            }
        }

        # Именованная группа, присутствующая и в источнике, заменяется целиком.
        if ($isNamed -and $groupsByName.ContainsKey($name)) {
            $newBlock = $groupsByName[$name]
            # Если содержимое изменилось — считаем группу обновлённой и логируем.
            if ($blk -join "`n" -ne $newBlock -join "`n") {
                $changed++
                Write-Host "AutoHostUpdate: обновлена группа '$name' ($($blk.Count - 1) -> $($newBlock.Count - 1) строк)."
                Write-Log "Обновлена группа '$name' ($($blk.Count - 1) -> $($newBlock.Count - 1) строк)."
            }
            foreach ($l in $newBlock) { $out.Add($l) }
        } else {
            # Остальные блоки (неназванные или только в источнике) оставляем без изменений.
            foreach ($l in $blk) { $out.Add($l) }
        }
        # Разделяем блоки пустой строкой.
        $out.Add("")
    }

    # Убираем завершающую пустую строку, если она осталась последней.
    if ($out.Count -gt 0 -and $out[$out.Count - 1] -eq "") {
        $out.RemoveAt($out.Count - 1)
    }

    if ($changed -eq 0) {
        Write-Host "AutoHostUpdate: группы совпадают - содержимое не изменилось."
        Write-Log "Именованные группы совпадают - содержимое не изменилось."
    }
    return [pscustomobject]@{ Lines = $out.ToArray(); Changed = $changed }
}

# Обновляет (или добавляет сверху) строку-маркер даты в локальном hosts.
function Set-MarkerDate {
    param([string[]]$Lines, [string]$DateValue)
    $marker = "# {0} {1}" -f $MarkerPrefix, $DateValue
    $out = New-Object System.Collections.Generic.List[string]
    $replaced = $false
    foreach ($ln in $Lines) {
        # Заменяем существующий маркер новым значением даты.
        if ($ln -match "^#\s*Последнее обновление:\s*") {
            $out.Add($marker)
            $replaced = $true
        } else {
            $out.Add($ln)
        }
    }
    # Если маркера в hosts не было — вставляем его первой строкой.
    if (-not $replaced) {
        $out.Insert(0, $marker)
    }
    return , $out.ToArray()
}

# ---------- Основной поток ----------
$mutex = $null
try {
    # Защита от параллельных запусков: если мутекс уже занят — выходим.
    $mutex = New-Object System.Threading.Mutex($false, $SingleRunMutex)
    if (-not $mutex.WaitOne(0)) {
        Write-Host "AutoHostUpdate: другой экземпляр уже выполняется - пропуск."
        Write-Log "Другой экземпляр уже выполняется - пропуск."
        Show-Notification "AutoHostUpdate" "Пропуск: другой экземпляр уже выполняется." "Warning"
        exit 0
    }

    # Проверка прав администратора: изменение hosts требует повышенных прав.
    if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Fail-WithError "Нужны права администратора для изменения hosts."
    }

    Write-Host "AutoHostUpdate: запуск..."
    Write-Log "=== Запуск AutoHostUpdate ==="
    # Создаём каталог для резервных копий, если его ещё нет.
    if (-not (Test-Path -LiteralPath $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null }

    # 1. Получаем данные из источника (дата обновления + именованные группы).
    $source = Get-SourceData
    Write-Host "AutoHostUpdate: источник: дата='$($source.DateValue)', групп=$($source.Groups.Count)"

    # 2. Читаем текущее содержимое локального hosts.
    $localLines = Read-HostsLines
    Write-Host "AutoHostUpdate: локальный hosts прочитан ($($localLines.Count) строк)."

    # 3. Сравниваем дату в hosts с датой источника как сырые строки.
    $currentDate = Get-MarkerDate $localLines
    if ($currentDate -ne "" -and $currentDate -eq $source.DateValue) {
        Write-Host "AutoHostUpdate: обновление не требуется (дата совпадает)."
        Write-Log "Обновление не требуется: дата совпадает ('$currentDate')."
        Show-Notification "AutoHostUpdate" "Обновление не требуется: hosts уже актуален ('$currentDate')."
        exit 0
    }
    Write-Host "AutoHostUpdate: найдено обновление: '$($source.DateValue)' (было '$currentDate')."
    Write-Log "Найдено обновление: '$($source.DateValue)' (было '$currentDate')."

    # 4. Резервная копия hosts перед внесением изменений.
    $backupFile = Join-Path $BackupDir ("hosts_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".bak")
    Copy-Item -LiteralPath $HostsPath -Destination $backupFile -Force
    Write-Host "AutoHostUpdate: резервная копия: $backupFile"
    Write-Log "Резервная копия: $backupFile"

    # 5. Снимаем атрибут ReadOnly, если он установлен (иначе запись не пройдёт).
    $item = Get-Item -LiteralPath $HostsPath
    if ($item.Attributes -band [System.IO.FileAttributes]::ReadOnly) {
        $item.Attributes = $item.Attributes -bxor [System.IO.FileAttributes]::ReadOnly
        Write-Host "AutoHostUpdate: атрибут ReadOnly снят с hosts."
        Write-Log "Атрибут ReadOnly снят с hosts."
    }

    # 6. Собираем новые строки: заменяем именованные группы и обновляем маркер даты.
    $updateResult = Update-GroupsLines $localLines $source.Groups
    $newLines = $updateResult.Lines
    $newLines = Set-MarkerDate $newLines $source.DateValue

    # 7. Записываем hosts в кодировке UTF-8 с BOM (требуется для корректной кириллицы).
    $text = $newLines -join "`r`n"
    $utf8 = New-Object System.Text.UTF8Encoding($true)
    [System.IO.File]::WriteAllText($HostsPath, $text, $utf8)
    Write-Host "AutoHostUpdate: hosts записан ($($newLines.Count) строк)."
    Write-Log "hosts записан ($($newLines.Count) строк)."

    # 8. Сбрасываем кеш DNS, чтобы изменения применились сразу.
    try {
        & ipconfig /flushdns 2>&1 | Out-Null
        Write-Host "AutoHostUpdate: DNS-кеш сброшен."
        Write-Log "DNS-кеш сброшен."
    } catch {
        Write-Log "Не удалось сбросить DNS: $($_.Exception.Message)"
    }

    # 9. Уведомление о завершении: hosts обновлён.
    if ($updateResult.Changed -gt 0) {
        Show-Notification "AutoHostUpdate" "Hosts обновлён: заменено групп - $($updateResult.Changed).`r`nРезервная копия: $backupFile"
    } else {
        Show-Notification "AutoHostUpdate" "Hosts перезаписан: группы без изменений, обновлён только маркер даты."
    }

    Write-Host "AutoHostUpdate: готово."
    Write-Log "=== Готово ==="
} catch {
    # Любая необработанная ошибка -> лог и (если не -Quiet) диалог.
    Fail-WithError $_.Exception.Message
} finally {
    # Обязательно освобождаем мутекс, чтобы не заблокировать следующий запуск.
    if ($mutex) {
        try { $mutex.ReleaseMutex() } catch { }
        $mutex.Dispose()
    }
}