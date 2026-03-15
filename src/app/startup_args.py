# FILE: src/app/startup_args.py
from __future__ import annotations

from dataclasses import dataclass
import argparse


@dataclass(slots=True)
class StartupArgs:
    scheduled_send_id: int | None = None
    scheduler_launch: bool = False
    recover_scheduled_sends: bool = False
    minimized: bool = False

    @property
    def is_scheduled_launch(self) -> bool:
        return bool(self.scheduler_launch and self.scheduled_send_id is not None)


def parse_startup_args(argv: list[str] | None = None) -> StartupArgs:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--scheduled-send-id", type=int, default=None)
    parser.add_argument("--scheduler-launch", action="store_true")
    parser.add_argument("--recover-scheduled-sends", action="store_true")
    parser.add_argument("--minimized", action="store_true")

    ns, _unknown = parser.parse_known_args(argv)
    return StartupArgs(
        scheduled_send_id=ns.scheduled_send_id,
        scheduler_launch=bool(ns.scheduler_launch),
        recover_scheduled_sends=bool(ns.recover_scheduled_sends),
        minimized=bool(ns.minimized),
    )
