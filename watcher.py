"""
Ядро родительского контроля.

Логика:
1. Читает config.json (список процессов, домен, порт).
2. Гарантирует, что домен из конфига указывает на 127.0.0.1 (правит hosts).
3. Поднимает локальный HTTP-сервер, отдающий blocked.html.
4. В цикле проверяет запущенные процессы; если находит заблокированный —
   завершает его и открывает в браузере страницу блокировки.

Этот модуль не содержит логики установки/автозапуска — это делает service.py
и install.ps1. Здесь только функциональность мониторинга.
"""

import hashlib
import json
import subprocess
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import psutil

OPEN_BROWSER_TASK_NAME = "ParentalControlOpenBrowser"


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _base_dir() -> Path:
    """Папка, где реально лежит exe/скрипт.

    В скомпилированном PyInstaller --onefile exe атрибут __file__ указывает
    на временную папку распаковки (%TEMP%\\_MEIxxxx), а не туда, где лежит
    сам .exe (C:\\Program Files\\ParentalControl) — из-за этого config.json
    и blocked.html, скопированные installer'ом рядом с exe, не находились,
    служба падала на старте с FileNotFoundError, а Windows показывала это
    как Event ID 10 без текста ошибки (нет message DLL у голого exe).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = _base_dir()
CONFIG_PATH = BASE_DIR / "config.json"
PAGE_PATH = BASE_DIR / "blocked.html"
HOSTS_PATH = Path(r"C:\Windows\System32\drivers\etc\hosts")
LOG_PATH = BASE_DIR / "service.log"


def log_exception(context: str) -> None:
    """Пишет traceback в service.log рядом с exe — Event Viewer не показывает
    текст ошибок у наших событий, поэтому реальная диагностика теперь здесь."""
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"\n--- {context} ---\n")
            f.write(traceback.format_exc())
    except Exception:
        pass  # если даже лог не пишется, не роняем службу из-за этого


def load_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def ensure_hosts_entry(host: str) -> None:
    """Добавляет запись в hosts, если её ещё нет. Требует прав администратора/SYSTEM."""
    content = HOSTS_PATH.read_text(encoding="utf-8")
    if host not in content:
        with HOSTS_PATH.open("a", encoding="utf-8") as f:
            f.write(f"\n127.0.0.1 {host}\n")


def _result_page(message: str, color: str = "#fff") -> bytes:
    return (
        "<html><body style='font-family:sans-serif;background:#1e1e2e;"
        "color:#fff;display:grid;place-items:center;height:100vh;margin:0'>"
        f"<div><h1 style='color:{color}'>{message}</h1></div></body></html>"
    ).encode("utf-8")


def make_handler(watcher: "Watcher"):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self._send_html(PAGE_PATH.read_bytes())

        def do_POST(self):
            """Форма на blocked.html шлёт сюда пароль (поле 'password')."""
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8", errors="ignore")
            password = parse_qs(raw).get("password", [""])[0]

            if hash_password(password) == watcher.unlock_password_hash:
                watcher.unlock()
                if watcher.unlock_duration_minutes > 0:
                    msg = f"✅ Разблокировано на {watcher.unlock_duration_minutes} мин."
                else:
                    msg = "✅ Защита полностью отключена. Служба удаляется..."
                self._send_html(_result_page(msg, color="#4ade80"))
            else:
                body = PAGE_PATH.read_bytes().replace(
                    b"</div>",
                    "<p style='color:#f55'>Неверный пароль</p></div>".encode("utf-8"),
                    1,
                )
                self._send_html(body)

        def _send_html(self, body: bytes) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass  # не шумим в логах службы

    return Handler


def run_server(port: int, watcher: "Watcher") -> HTTPServer:
    server = HTTPServer(("127.0.0.1", port), make_handler(watcher))
    return server


def open_browser_in_user_session() -> None:
    """Служба работает как SYSTEM в Session 0 — у неё нет доступа к рабочему
    столу пользователя, поэтому webbrowser.open() отсюда не показывает
    ничего. Вместо этого просим Task Scheduler запустить заранее
    зарегистрированную задачу (installer.py), настроенную на запуск именно
    в интерактивной сессии вошедшего пользователя."""
    try:
        subprocess.run(
            ["schtasks.exe", "/run", "/tn", OPEN_BROWSER_TASK_NAME],
            check=True,
            capture_output=True,
        )
    except Exception:
        log_exception("open_browser_in_user_session failed")


SERVICE_NAME = "ParentalControlSvc"


def self_destruct() -> None:
    """unlock_duration_minutes == 0 + верный пароль -> полное отключение:
    служба и задача удаляются из системы, папка установки стирается.

    Служба не может удалить саму себя, пока работает (Windows не даёт стереть
    файл запущенного процесса), поэтому запускаем отдельный, не зависящий от
    этого процесса cmd-скрипт: он чуть ждёт, останавливает и удаляет службу
    (после этого сам процесс службы завершится), удаляет запланированную
    задачу и затем стирает папку установки."""
    try:
        install_dir = str(BASE_DIR)
        script = (
            "timeout /t 2 /nobreak >nul & "
            f"sc stop {SERVICE_NAME} & "
            f"sc delete {SERVICE_NAME} & "
            f"schtasks /delete /tn {OPEN_BROWSER_TASK_NAME} /f & "
            "timeout /t 2 /nobreak >nul & "
            f'rmdir /s /q "{install_dir}"'
        )
        subprocess.Popen(
            ["cmd.exe", "/c", script],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    except Exception:
        log_exception("self_destruct failed")


def kill_blocked_processes(blocked_names: set[str]) -> bool:
    """Убивает все процессы из списка. Возвращает True, если хоть один был убит."""
    killed = False
    for proc in psutil.process_iter(["name"]):
        name = (proc.info["name"] or "").lower()
        if name in blocked_names:
            try:
                proc.kill()
                killed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    return killed


class Watcher:
    """Обёртка над циклом мониторинга, которую удобно дёргать по шагам из службы
    (SvcDoRun вызывает run(), который сам крутит while) или напрямую (main())."""

    def __init__(self):
        self.config = load_config()
        self.blocked_names = {n.lower() for n in self.config["blocked_processes"]}
        self.host = self.config["host"]
        self.port = self.config["port"]
        self.interval = self.config.get("check_interval_seconds", 1)
        self.cooldown = self.config.get("reopen_cooldown_seconds", 5)
        self.unlock_password_hash = self.config.get("unlock_password_hash", "")
        # 0 или отсутствует = разблокировка до перезапуска службы;
        # иначе через N минут защита включается обратно сама.
        self.unlock_duration_minutes = self.config.get("unlock_duration_minutes", 0)
        self._unlocked_until = 0.0  # 0 = защита активна
        self._last_open = 0.0
        self._server = None
        self._running = False

    def start_server(self) -> None:
        ensure_hosts_entry(self.host)
        self._server = run_server(self.port, self)
        import threading
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def unlock(self) -> None:
        """Вызывается HTTP-обработчиком при верном пароле."""
        if self.unlock_duration_minutes > 0:
            self._unlocked_until = time.time() + self.unlock_duration_minutes * 60
        else:
            # 0 = не пауза, а полное и необратимое отключение: служба,
            # задача и файлы установки удаляются из системы насовсем.
            self._unlocked_until = float("inf")
            self_destruct()

    def is_unlocked(self) -> bool:
        return time.time() < self._unlocked_until

    def step(self) -> None:
        """Один проход цикла проверки — используется службой, которая сама
        управляет остановкой через событие."""
        if self.is_unlocked():
            return  # защита временно снята верным паролем

        if kill_blocked_processes(self.blocked_names):
            now = time.time()
            if now - self._last_open > self.cooldown:
                open_browser_in_user_session()
                self._last_open = now

    def run_forever(self) -> None:
        try:
            self.start_server()
        except Exception:
            log_exception("start_server failed")
            # Даже если локальная страница не поднялась (например, порт занят),
            # мониторинг и убийство процессов всё равно должны работать.

        self._running = True
        while self._running:
            try:
                self.step()
            except Exception:
                log_exception("step failed")
            time.sleep(self.interval)

    def stop(self) -> None:
        self._running = False
        if self._server:
            self._server.shutdown()


def main() -> None:
    Watcher().run_forever()


if __name__ == "__main__":
    main()