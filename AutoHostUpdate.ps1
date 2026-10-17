#Requires -RunAsAdministrator
<#
    AutoHostUpdate.ps1
    Проверяет обновления именованных групп в hosts по маякам из сетевого источника.
    Обновляет только те именованные группы, которые уже есть в локальном hosts.
    Лог: %TEMP%\AutoHostUpdate.log
#>

# ---------- Параметры командной строки ----------
[CmdletBinding()]
param(
    [switch]$Quiet
)

# ---------- Конфигурация ----------
$SourceUrl      = "https://geohide.ru/eu/hosts"
$HostsPath      = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"
$LogDir         = $env:TEMP
$LogFile        = Join-Path $LogDir "AutoHostUpdate.log"
$BackupDir      = Join-Path $LogDir "AutoHostUpdate_backups"
$MarkerPrefix   = "Последнее обновление:"
$SingleRunMutex = "Global\AutoHostUpdate_RunOnce"
$SkipDialogs    = [bool]$Quiet

# ---------- Лог ----------
function Write-Log {
    param([string]$Message)
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    try { Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8 } catch { }
}

# ---------- Диалог ошибки ----------
function Show-ErrorDialog {
    param([string]$Message)
    $ErrorLog = $LogFile
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        Add-Type -AssemblyName System.Drawing -ErrorAction Stop
        $form = New-Object System.Windows.Forms.Form
        $form.Text        = "AutoHostUpdate - ошибка"
        $form.Size        = New-Object System.Drawing.Size(560, 260)
        $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
        $form.MaximizeBox  = $false
        $form.MinimizeBox  = $false
        $form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen

        $label = New-Object System.Windows.Forms.Label
        $label.Location = New-Object System.Drawing.Point(20, 20)
        $label.Size    = New-Object System.Drawing.Size(500, 100)
        $label.AutoSize = $false
        $label.Text     = $Message + "`r`n`r`nЛог: $ErrorLog"
        $form.Controls.Add($label)

        $btnLog = New-Object System.Windows.Forms.Button
        $btnLog.Text     = "Открыть лог"
        $btnLog.Location = New-Object System.Drawing.Point(20, 140)
        $btnLog.Size     = New-Object System.Drawing.Size(140, 35)
        $btnLog.Add_Click({ try { Start-Process notepad.exe $ErrorLog } catch { } })
        $form.Controls.Add($btnLog)

        $btnOk = New-Object System.Windows.Forms.Button
        $btnOk.Text     = "OK"
        $btnOk.Location = New-Object System.Drawing.Point(170, 140)
        $btnOk.Size     = New-Object System.Drawing.Size(90, 35)
        $btnOk.DialogResult = [System.Windows.Forms.DialogResult]::OK
        $form.Controls.Add($btnOk)

        $form.AcceptButton = $btnOk
        [void]$form.ShowDialog()
    } catch {
        Write-Log "Не удалось показать окно ошибки: $($_.Exception.Message)"
    }
}

# ---------- Уведомление ----------
function Show-Notification {
    param(
        [string]$Title,
        [string]$Message,
        [string]$Kind = "Info"
    )
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        Add-Type -AssemblyName System.Drawing -ErrorAction Stop
        $tip = New-Object System.Windows.Forms.NotifyIcon
        switch ($Kind) {
            "Warning" { $tip.Icon = [System.Drawing.SystemIcons]::Warning;       $iconType = [System.Windows.Forms.ToolTipIcon]::Warning }
            "Error"   { $tip.Icon = [System.Drawing.SystemIcons]::Error;         $iconType = [System.Windows.Forms.ToolTipIcon]::Error }
            default   { $tip.Icon = [System.Drawing.SystemIcons]::Information;   $iconType = [System.Windows.Forms.ToolTipIcon]::Info }
        }
        $tip.Visible = $true
        $tip.ShowBalloonTip(20000, $Title, $Message, $iconType)
        Start-Sleep -Milliseconds 4500
        $tip.Visible = $false
        $tip.Dispose()
    } catch {
        Write-Log "Не удалось показать уведомление: $($_.Exception.Message)"
    }
}

# ---------- Аварийный выход ----------
function Fail-WithError {
    param([string]$Message)
    Write-Log "ОШИБКА: $Message"
    Show-Notification "AutoHostUpdate - ошибка" $Message "Error"
    if (-not $SkipDialogs) {
        try { Write-Error $Message } catch { }
        Show-ErrorDialog $Message
    }
    exit 1
}

# ---------- Парсинг ----------
function Split-Blocks {
    param([string[]]$Lines)
    $blocks = @()
    $current = New-Object System.Collections.Generic.List[string]
    foreach ($ln in $Lines) {
        if ($null -eq $ln) { $ln = "" }
        if ($ln.Trim() -eq "") {
            if ($current.Count -gt 0) {
                $blocks += , @($current.ToArray())
                $current = New-Object System.Collections.Generic.List[string]
            }
        } else {
            $current.Add($ln.TrimEnd())
        }
    }
    if ($current.Count -gt 0) { $blocks += , @($current.ToArray()) }
    return , $blocks
}

function Get-NamedGroups {
    param([object[]]$Blocks)
    $groups = @()
    foreach ($blk in $Blocks) {
        $first = $blk[0]
        if ($first -notmatch "^#") { continue }
        $hasEntry = $false
        foreach ($ln in $blk) {
            if ($ln -notmatch "^\s*#") { $hasEntry = $true; break }
        }
        if (-not $hasEntry) { continue }
        $name = $first.TrimStart('#', ' ').Trim()
        if ($name -eq "") { continue }
        $groups += [pscustomobject]@{ Name = $name; Raw = $blk }
    }
    return , $groups
}

# ---------- Работа с источником ----------
function Get-SourceData {
    $tempFile = Join-Path $env:TEMP ("geohide_hosts_" + [guid]::NewGuid().ToString() + ".tmp")
    
    try {
        Invoke-WebRequest -Uri $SourceUrl -OutFile $tempFile -UseBasicParsing -TimeoutSec 60 -ErrorAction Stop
    } catch {
        Fail-WithError "Сайт источника недоступен ($SourceUrl).`nПроверьте подключение к интернету.`nДетали: $($_.Exception.Message)"
    }

    try {
        $content = [System.IO.File]::ReadAllText($tempFile, [System.Text.Encoding]::UTF8)
    } finally {
        if (Test-Path -LiteralPath $tempFile) { 
            Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue 
        }
    }

    $content = $content -replace "`r`n", "`n"
    $lines = $content -split "`n"
    if ($lines.Count -lt 2) { throw "Файл источника слишком короткий или пуст." }

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
function Read-HostsLines {
    if (-not (Test-Path -LiteralPath $HostsPath)) { throw "Файл hosts не найден: $HostsPath" }
    $raw = [System.IO.File]::ReadAllText($HostsPath)
    $raw = $raw -replace "`r`n", "`n"
    $lines = $raw -split "`n"
    if ($lines.Count -gt 0 -and $lines[$lines.Count - 1] -eq "") {
        $lines = $lines[0..($lines.Count - 2)]
    }
    return , $lines
}

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

function Update-GroupsLines {
    param([string[]]$LocalLines, [object[]]$SourceGroups)

    $groupsByName = @{}
    foreach ($g in $SourceGroups) { $groupsByName[$g.Name] = $g.Raw }

    $blocks = Split-Blocks $LocalLines
    $out = New-Object System.Collections.Generic.List[string]
    $changed = 0

    foreach ($blk in $blocks) {
        $first = $blk[0]
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

        if ($isNamed -and $groupsByName.ContainsKey($name)) {
            $newBlock = $groupsByName[$name]
            if ($blk -join "`n" -ne $newBlock -join "`n") {
                $changed++
                Write-Host "AutoHostUpdate: обновлена группа '$name' ($($blk.Count - 1) -> $($newBlock.Count - 1) строк)."
                Write-Log "Обновлена группа '$name' ($($blk.Count - 1) -> $($newBlock.Count - 1) строк)."
            }
            foreach ($l in $newBlock) { $out.Add($l) }
        } else {
            foreach ($l in $blk) { $out.Add($l) }
        }
        $out.Add("")
    }

    if ($out.Count -gt 0 -and $out[$out.Count - 1] -eq "") {
        $out.RemoveAt($out.Count - 1)
    }

    if ($changed -eq 0) {
        Write-Host "AutoHostUpdate: группы совпадают - содержимое не изменилось."
        Write-Log "Именованные группы совпадают - содержимое не изменилось."
    }
    return [pscustomobject]@{ Lines = $out.ToArray(); Changed = $changed }
}

function Set-MarkerDate {
    param([string[]]$Lines, [string]$DateValue)
    $marker = "# {0} {1}" -f $MarkerPrefix, $DateValue
    $out = New-Object System.Collections.Generic.List[string]
    $replaced = $false
    foreach ($ln in $Lines) {
        if ($ln -match "^#\s*Последнее обновление:\s*") {
            $out.Add($marker)
            $replaced = $true
        } else {
            $out.Add($ln)
        }
    }
    if (-not $replaced) {
        $out.Insert(0, $marker)
    }
    return , $out.ToArray()
}

# ---------- Основной поток ----------
$mutex = $null
try {
    $mutex = New-Object System.Threading.Mutex($false, $SingleRunMutex)
    if (-not $mutex.WaitOne(0)) {
        Write-Host "AutoHostUpdate: другой экземпляр уже выполняется - пропуск."
        Write-Log "Другой экземпляр уже выполняется - пропуск."
        Show-Notification "AutoHostUpdate" "Пропуск: другой экземпляр уже выполняется." "Warning"
        exit 0
    }

    if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Fail-WithError "Нужны права администратора для изменения hosts."
    }

    Write-Host "AutoHostUpdate: запуск..."
    Write-Log "=== Запуск AutoHostUpdate ==="
    if (-not (Test-Path -LiteralPath $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null }

    $source = Get-SourceData
    Write-Host "AutoHostUpdate: источник: дата='$($source.DateValue)', групп=$($source.Groups.Count)"

    $localLines = Read-HostsLines
    Write-Host "AutoHostUpdate: локальный hosts прочитан ($($localLines.Count) строк)."

    $currentDate = Get-MarkerDate $localLines
    if ($currentDate -ne "" -and $currentDate -eq $source.DateValue) {
        Write-Host "AutoHostUpdate: обновление не требуется (дата совпадает)."
        Write-Log "Обновление не требуется: дата совпадает ('$currentDate')."
        Show-Notification "AutoHostUpdate" "Обновление не требуется: hosts уже актуален ('$currentDate')."
        exit 0
    }
    Write-Host "AutoHostUpdate: найдено обновление: '$($source.DateValue)' (было '$currentDate')."
    Write-Log "Найдено обновление: '$($source.DateValue)' (было '$currentDate')."

    $backupFile = Join-Path $BackupDir ("hosts_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".bak")
    Copy-Item -LiteralPath $HostsPath -Destination $backupFile -Force
    Write-Host "AutoHostUpdate: резервная копия: $backupFile"
    Write-Log "Резервная копия: $backupFile"

    $item = Get-Item -LiteralPath $HostsPath
    if ($item.Attributes -band [System.IO.FileAttributes]::ReadOnly) {
        $item.Attributes = $item.Attributes -bxor [System.IO.FileAttributes]::ReadOnly
        Write-Host "AutoHostUpdate: атрибут ReadOnly снят с hosts."
        Write-Log "Атрибут ReadOnly снят с hosts."
    }

    $updateResult = Update-GroupsLines $localLines $source.Groups
    $newLines = $updateResult.Lines
    $newLines = Set-MarkerDate $newLines $source.DateValue

    $text = $newLines -join "`r`n"
    $utf8 = New-Object System.Text.UTF8Encoding($true)
    [System.IO.File]::WriteAllText($HostsPath, $text, $utf8)
    Write-Host "AutoHostUpdate: hosts записан ($($newLines.Count) строк)."
    Write-Log "hosts записан ($($newLines.Count) строк)."

    try {
        & ipconfig /flushdns 2>&1 | Out-Null
        Write-Host "AutoHostUpdate: DNS-кеш сброшен."
        Write-Log "DNS-кеш сброшен."
    } catch {
        Write-Log "Не удалось сбросить DNS: $($_.Exception.Message)"
    }

    if ($updateResult.Changed -gt 0) {
        Show-Notification "AutoHostUpdate" "Hosts обновлён: заменено групп - $($updateResult.Changed).`r`nРезервная копия: $backupFile"
    } else {
        Show-Notification "AutoHostUpdate" "Hosts перезаписан: группы без изменений, обновлён только маркер даты."
    }

    Write-Host "AutoHostUpdate: готово."
    Write-Log "=== Готово ==="
} catch {
    Fail-WithError $_.Exception.Message
} finally {
    if ($mutex) {
        try { $mutex.ReleaseMutex() } catch { }
        $mutex.Dispose()
    }
}