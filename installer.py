"""
Установщик ParentalControl.

Компилируется в Install.exe (см. build.ps1). Благодаря вшитому манифесту
admin_manifest.xml, Windows при запуске .exe сразу показывает окно UAC —
отдельно запускать от администратора не нужно, достаточно подтвердить запрос.

Делает то же самое, что раньше делал install.ps1:
  1. Копирует файлы в Program Files.
  2. Регистрирует ParentalControlService.exe как Windows-службу напрямую
     (без Python на целевой машине — служба тоже скомпилирована в exe).
  3. Ограничивает права на управление службой (sc sdset) и на файлы (icacls),
     чтобы обычная учётная запись не могла её остановить/удалить.
"""

import ctypes
import json
import shutil
import subprocess
import sys
from pathlib import Path

INSTALL_DIR = Path(r"C:\Program Files\ParentalControl")
SERVICE_NAME = "ParentalControlSvc"
SERVICE_DISPLAY_NAME = "Parental Control Service"
OPEN_BROWSER_TASK_NAME = "ParentalControlOpenBrowser"


def resource_dir() -> Path:
    """Папка с ресурсами: рядом с exe, или _MEIPASS при PyInstaller --onefile."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # noqa: SLF001
    return Path(__file__).resolve().parent


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    """Подстраховка на случай запуска без манифеста (например, из python installer.py)."""
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )
    sys.exit(0)


def run(cmd: list[str]) -> None:
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    if not is_admin():
        relaunch_as_admin()
        return

    src = resource_dir()

    print("== 1. Копирование файлов ==")
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("ParentalControlService.exe", "config.json", "blocked.html"):
        shutil.copy2(src / name, INSTALL_DIR / name)

    service_exe = str(INSTALL_DIR / "ParentalControlService.exe")

    print("== 2. Регистрация службы ==")
    # Служба — самостоятельный exe (скомпилирован из service.py), Python на
    # целевой машине не нужен.
    run([
        "sc.exe", "create", SERVICE_NAME,
        f"binPath={service_exe}",
        "start=auto",
        f"DisplayName={SERVICE_DISPLAY_NAME}",
    ])
    run(["sc.exe", "description", SERVICE_NAME,
         "Monitors running applications and restricts access to blocked ones."])
    run(["sc.exe", "start", SERVICE_NAME])

    print("== 3. Регистрация задачи показа страницы блокировки ==")
    with (INSTALL_DIR / "config.json").open(encoding="utf-8") as f:
        cfg = json.load(f)
    host, port = cfg["host"], cfg["port"]
    url = f"http://{host}/" if port == 80 else f"http://{host}:{port}/"

    # /ru INTERACTIVE + /it ("run only if logged on") — ключевая часть:
    # задача выполняется в интерактивной сессии вошедшего пользователя,
    # а не в Session 0, где сидит служба. Поэтому её и может запускать
    # обычная служба SYSTEM через "schtasks /run", а страница реально
    # откроется на экране у пользователя.
    subprocess.run(["schtasks.exe", "/delete", "/tn", OPEN_BROWSER_TASK_NAME, "/f"],
                   capture_output=True)  # игнорируем ошибку, если задачи ещё нет
    run([
        "schtasks.exe", "/create", "/tn", OPEN_BROWSER_TASK_NAME,
        "/tr", f'cmd /c start "" "{url}"',
        "/sc", "onlogon",
        "/ru", "INTERACTIVE",
        "/it",
        "/f",
    ])

    print("== 4. Ограничение прав на управление службой ==")
    sddl = (
        "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)"
        "(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)"
        "(A;;CCLCSWLORC;;;IU)"
        "(A;;CCLCSWLORC;;;SU)"
    )
    run(["sc.exe", "sdset", SERVICE_NAME, sddl])

    print("== 5. Ограничение прав на файлы ==")
    run(["icacls.exe", str(INSTALL_DIR), "/inheritance:r"])
    run(["icacls.exe", str(INSTALL_DIR), "/grant:r",
         "SYSTEM:(OI)(CI)F", "Administrators:(OI)(CI)F"])

    print()
    print("Готово. Служба 'ParentalControlSvc' установлена и запущена.")
    print("ВАЖНО: учётная запись ребёнка должна быть стандартной (не админ),")
    print("иначе все ограничения можно обойти через 'Запуск от администратора'.")
    input("\nНажми Enter для выхода...")


if __name__ == "__main__":
    main()
