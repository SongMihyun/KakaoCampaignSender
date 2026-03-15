# FILE: src/backend/integrations/windows/task_scheduler_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class TaskRegistrationResult:
    task_name: str
    task_path: str


class TaskSchedulerService:
    FOLDER_NAME = "KakaoCampaignSender"

    def build_task_name(self, schedule_id: int) -> str:
        return f"ScheduledSend_{int(schedule_id)}"

    def register_one_time_task(
        self,
        *,
        schedule_id: int,
        run_at: datetime,
        executable_path: str,
        arguments: list[str],
        working_dir: str,
        description: str = "",
    ) -> TaskRegistrationResult:
        try:
            import pythoncom
            import win32com.client
        except Exception as e:
            raise RuntimeError(
                "Windows 작업 스케줄러 연동을 사용할 수 없습니다. pywin32 환경을 확인해주세요."
            ) from e

        pythoncom.CoInitialize()
        try:
            service = win32com.client.Dispatch("Schedule.Service")
            service.Connect()

            root = service.GetFolder("\\")
            folder = self._ensure_folder(root, self.FOLDER_NAME)

            task_def = service.NewTask(0)
            task_def.RegistrationInfo.Description = description or f"Scheduled send #{schedule_id}"

            settings = task_def.Settings
            settings.Enabled = True
            settings.StartWhenAvailable = True
            settings.WakeToRun = True
            settings.AllowDemandStart = True
            settings.DisallowStartIfOnBatteries = False
            settings.StopIfGoingOnBatteries = False
            try:
                settings.MultipleInstances = 0
            except Exception:
                pass

            principal = task_def.Principal
            principal.LogonType = 3  # TASK_LOGON_INTERACTIVE_TOKEN

            trigger = task_def.Triggers.Create(1)  # TIME_TRIGGER
            trigger.StartBoundary = run_at.strftime("%Y-%m-%dT%H:%M:%S")

            action = task_def.Actions.Create(0)  # EXEC_ACTION
            action.Path = str(Path(executable_path))
            action.Arguments = " ".join(self._quote_arg(x) for x in arguments)
            action.WorkingDirectory = str(Path(working_dir))

            task_name = self.build_task_name(schedule_id)
            folder.RegisterTaskDefinition(task_name, task_def, 6, "", "", 3)

            return TaskRegistrationResult(
                task_name=task_name,
                task_path=f"\\{self.FOLDER_NAME}\\{task_name}",
            )
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    def delete_task(self, task_name: str) -> None:
        try:
            import pythoncom
            import win32com.client
        except Exception as e:
            raise RuntimeError(
                "Windows 작업 스케줄러 연동을 사용할 수 없습니다. pywin32 환경을 확인해주세요."
            ) from e

        pythoncom.CoInitialize()
        try:
            service = win32com.client.Dispatch("Schedule.Service")
            service.Connect()
            folder = service.GetFolder(f"\\{self.FOLDER_NAME}")
            folder.DeleteTask(str(task_name), 0)
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    def _ensure_folder(self, root, folder_name: str):
        try:
            return root.GetFolder(f"\\{folder_name}")
        except Exception:
            return root.CreateFolder(folder_name)

    def _quote_arg(self, value: str) -> str:
        v = str(value or "")
        if not v:
            return '""'
        if " " in v or '"' in v:
            return '"' + v.replace('"', '\\"') + '"'
        return v
