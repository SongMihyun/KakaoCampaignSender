

# ✅ FILE: src/app/sender/speed_profiles.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HookTimings:
    search_open_delay: float = 0.04
    select_home_delay: float = 0.006
    select_end_delay: float = 0.010
    delete_delay: float = 0.012
    extra_delete_delay: float = 0.010
    paste_name_delay: float = 0.03
    enter1_delay: float = 0.05
    enter2_delay: float = 0.08


@dataclass
class CtrlTTimings:
    focus_settle: float = 0.08
    after_ctrl_t: float = 0.20
    clipboard_settle: float = 0.03
    after_paste_path: float = 0.06
    after_enter_path: float = 0.15


@dataclass
class ImgDialogTimings:
    try_interval: float = 0.12
    loop_sleep: float = 0.02
    post_click_sleep: float = 0.03
    enter_gap_sec: float = 0.04


@dataclass
class SpeedProfile:
    speed_factor: float = 1.00
    auto_backoff: bool = True
    backoff_step: float = 0.12
    backoff_max: float = 1.15
    poll_sleep_min: float = 0.015
    poll_sleep_default: float = 0.03

    hooks: HookTimings = field(default_factory=HookTimings)
    ctrl_t: CtrlTTimings = field(default_factory=CtrlTTimings)
    img_dlg: ImgDialogTimings = field(default_factory=ImgDialogTimings)

    @staticmethod
    def slow() -> "SpeedProfile":
        return SpeedProfile(
            speed_factor=1.15,
            auto_backoff=True,
            backoff_step=0.15,
            backoff_max=1.30,
            poll_sleep_min=0.02,
            poll_sleep_default=0.04,
            hooks=HookTimings(
                search_open_delay=0.06,
                select_home_delay=0.010,
                select_end_delay=0.016,
                delete_delay=0.018,
                extra_delete_delay=0.016,
                paste_name_delay=0.05,
                enter1_delay=0.08,
                enter2_delay=0.12,
            ),
            ctrl_t=CtrlTTimings(
                focus_settle=0.12,
                after_ctrl_t=0.28,
                clipboard_settle=0.06,
                after_paste_path=0.10,
                after_enter_path=0.22,
            ),
            img_dlg=ImgDialogTimings(
                try_interval=0.16,
                loop_sleep=0.03,
                post_click_sleep=0.05,
                enter_gap_sec=0.06,
            ),
        )

    @staticmethod
    def normal() -> "SpeedProfile":
        return SpeedProfile()

    @staticmethod
    def fast() -> "SpeedProfile":
        return SpeedProfile(
            speed_factor=0.65,
            auto_backoff=True,
            backoff_step=0.10,
            backoff_max=1.05,
            poll_sleep_min=0.01,
            poll_sleep_default=0.015,
            hooks=HookTimings(
                search_open_delay=0.03,
                select_home_delay=0.004,
                select_end_delay=0.008,
                delete_delay=0.010,
                extra_delete_delay=0.008,
                paste_name_delay=0.02,
                enter1_delay=0.04,
                enter2_delay=0.06,
            ),
            ctrl_t=CtrlTTimings(
                focus_settle=0.06,
                after_ctrl_t=0.16,
                clipboard_settle=0.02,
                after_paste_path=0.05,
                after_enter_path=0.12,
            ),
            img_dlg=ImgDialogTimings(
                try_interval=0.07,
                loop_sleep=0.010,
                post_click_sleep=0.015,
                enter_gap_sec=0.03,
            ),
        )