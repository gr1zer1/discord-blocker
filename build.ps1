<#
    Собирает ParentalControl в два exe-файла. Запускать на Windows, где есть
    Python (обычный, не frozen) — сам результат сборки уже не требует Python
    на машине, где будет установлен родительский контроль.

    Использование:
        powershell -ExecutionPolicy Bypass -File build.ps1

    Результат появится в .\dist\:
        ParentalControlService.exe   — сама служба (ставится через installer)
        Install.exe                  — установщик одним кликом (просит UAC сам)
#>

$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot

Write-Host "== Установка зависимостей для сборки ==" -ForegroundColor Cyan
python -m pip install --quiet pyinstaller psutil pywin32

Write-Host "== Сборка ParentalControlService.exe ==" -ForegroundColor Cyan
pyinstaller --noconfirm --onefile --name ParentalControlService `
    --hidden-import win32timezone `
    "$Here\service.py"

Write-Host "== Сборка Install.exe (с запросом UAC и встроенными ресурсами) ==" -ForegroundColor Cyan
pyinstaller --noconfirm --onefile --name Install `
    --uac-admin `
    --manifest "$Here\admin_manifest.xml" `
    --add-data "$Here\dist\ParentalControlService.exe;." `
    --add-data "$Here\config.json;." `
    --add-data "$Here\blocked.html;." `
    "$Here\installer.py"

Write-Host ""
Write-Host "Готово. В .\dist\ лежит Install.exe — раздавай только его." -ForegroundColor Green
Write-Host "Двойной клик -> UAC -> служба ставится и стартует автоматически." -ForegroundColor Green
