#Requires -RunAsAdministrator
<#
    Установка "ParentalControl" одной командой:
      1. Копирует проект в Program Files.
      2. Ставит Python-зависимости.
      3. Регистрирует и запускает Windows-службу через service.py (pywin32).
      4. Ограничивает права на управление службой и на сам файл/папку так,
         чтобы обычная (не-админская) учётная запись ребёнка не могла её
         остановить, настроить или удалить. Служба при этом остаётся
         видимой в services.msc — никакого сокрытия, только права доступа.

    Запускать от имени администратора:
        powershell -ExecutionPolicy Bypass -File install.ps1
#>

$ErrorActionPreference = "Stop"

$InstallDir = "C:\Program Files\ParentalControl"
$SourceDir  = $PSScriptRoot

Write-Host "== 1. Копирование файлов в $InstallDir ==" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item "$SourceDir\*.py"   $InstallDir -Force
Copy-Item "$SourceDir\*.json" $InstallDir -Force
Copy-Item "$SourceDir\*.html" $InstallDir -Force

Write-Host "== 2. Установка зависимостей (psutil, pywin32) ==" -ForegroundColor Cyan
python -m pip install --quiet psutil pywin32

Write-Host "== 3. Регистрация и запуск службы ==" -ForegroundColor Cyan
Push-Location $InstallDir
python service.py --startup auto install
python service.py start
Pop-Location

Write-Host "== 4. Ограничение прав на управление службой ==" -ForegroundColor Cyan
# SYSTEM и Administrators (BA) — полный доступ.
# Interactive Users (IU) и Service logon (SU) — только чтение статуса,
# без права Start/Stop/Configure/Delete.
sc.exe sdset ParentalControlSvc "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;CCLCSWLORC;;;IU)(A;;CCLCSWLORC;;;SU)"

Write-Host "== 5. Ограничение прав на файлы установки ==" -ForegroundColor Cyan
icacls $InstallDir /inheritance:r | Out-Null
icacls $InstallDir /grant:r "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" | Out-Null

Write-Host ""
Write-Host "Готово. Служба 'ParentalControlSvc' установлена и запущена." -ForegroundColor Green
Write-Host "Проверить: services.msc -> Parental Control Service" -ForegroundColor Green
Write-Host ""
Write-Host "ВАЖНО: вся защита работает только если учётная запись ребёнка" -ForegroundColor Yellow
Write-Host "является стандартной (не администратором). Без этого шага" -ForegroundColor Yellow
Write-Host "любые права на службу/файлы можно обойти через 'Запуск от администратора'." -ForegroundColor Yellow
