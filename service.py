"""
Windows-служба "ParentalControlSvc".

Запускается как SYSTEM ещё до входа пользователя в систему, видна в
services.msc под обычным, не скрытым именем — защита строится не на
сокрытии, а на правах доступа (см. install.ps1: sc sdset + icacls),
которые не дают обычной (не-админской) учётной записи ребёнка её
остановить, настроить или удалить файлы.

Команды:
    python service.py install   # зарегистрировать службу
    python service.py start     # запустить
    python service.py stop      # остановить (от админа)
    python service.py remove    # удалить регистрацию службы (от админа)
"""

import sys
import threading

import servicemanager
import win32event
import win32service
import win32serviceutil

from watcher import Watcher, log_exception


class ParentalControlService(win32serviceutil.ServiceFramework):
    _svc_name_ = "ParentalControlSvc"
    _svc_display_name_ = "Parental Control Service"
    _svc_description_ = (
        "Monitors running applications and restricts access to blocked ones "
        "according to the local parental-control configuration."
    )

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        try:
            self.watcher = Watcher()
        except Exception:
            log_exception("Watcher() init failed")
            self.watcher = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.watcher:
            self.watcher.stop()
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        if self.watcher:
            threading.Thread(target=self.watcher.run_forever, daemon=True).start()
        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)


if __name__ == "__main__":
    # Когда Windows запускает скомпилированный .exe как службу напрямую
    # (binPath=ParentalControlService.exe), аргументов командной строки нет —
    # нужно сразу уйти в диспетчер служб, а не парсить install/start/remove.
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(ParentalControlService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(ParentalControlService)
