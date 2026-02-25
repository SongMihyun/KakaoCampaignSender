# ✅ FILE: src/app/sender/kakao_pc_driver.py
from __future__ import annotations

import os
import sys
import time
import ctypes
import logging
import threading
import hashlib
from io import BytesIO
from PIL import Image

from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Tuple, Any, Callable, Optional
from contextlib import contextmanager

from app.sender.kakao_pc_hooks import open_chat_by_name_hook, send_image_dialog_hook, ChatNotFound, _is_kakao_toast_quick_reply
from app.sender.image_attach_ctrl_t import send_png_via_ctrl_t
from ctypes import wintypes
from app.sender.image_attach_ctrl_v import attach_image_via_ctrl_v


# ✅ 단일 Win32 코어 사용
from app.sender.win32_core import (
    user32,
    kernel32,
    SW_RESTORE,
    CF_UNICODETEXT,
    CF_DIB,
    GMEM_MOVEABLE,
    lazy_pywinauto,
    get_foreground_hwnd,
    is_window,
    get_window_text,
    get_window_rect,
    rect_center,
    get_pid,
    foreground_hwnd_if_same_process,
    is_kakaotalk_title,
    fallback_click_point,
    sendinput_click,
    force_foreground_strict,
    set_clipboard_text,
    set_clipboard_dib,
    get_class_name,
)

from app.sender import win32_core as w32

def _lazy_pywinauto():
    # 기존 코드와 호환 유지(내부에서 사용 중이면 그대로)
    return lazy_pywinauto()


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
        return SpeedProfile(
            speed_factor=1.00,
            auto_backoff=True,
            backoff_step=0.12,
            backoff_max=1.15,
            poll_sleep_min=0.015,
            poll_sleep_default=0.03,
            hooks=HookTimings(),
            ctrl_t=CtrlTTimings(),
            img_dlg=ImgDialogTimings(),
        )

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


class KakaoSenderDriver:
    def start(self) -> None:
        raise NotImplementedError

    def recover(self) -> None:
        raise NotImplementedError

    def send_to_name(self, name: str, message: str, image_bytes_list: List[bytes]) -> None:
        raise NotImplementedError

    def send_campaign_items(self, name: str, campaign_items: List[Any]) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError


@dataclass
class KakaoTarget:
    title: str
    handle: int


class StopNow(RuntimeError):
    pass


class TransferAbortedByClose(RuntimeError):
    """'전송 중인 파일' 팝업에서 '확인'으로 종료되어 전송이 취소된 케이스"""
    pass


class CloseForcedByConfirm(RuntimeError):
    """
    close 단계에서 6번째 시도에 '확인'으로 강제 종료된 케이스.
    - 요구사항: 이 케이스는 "실패"로 간주해 로그에 남겨야 함.
    """
    pass


class KakaoPcDriver(KakaoSenderDriver):
    def __init__(
        self,
        target_handle: int,
        *,
        speed_mode: str = "fast",
        speed_profile: Optional[SpeedProfile] = None,
        focus_delay: float = 0.06,
        key_delay: float = 0.02,
        block_input: bool = False,
        use_alt_tab_confirm: bool = True,
        alt_tab_max_steps: int = 10,
        alt_tab_pause: float = 0.05,
        chat_input_ratio_y: float = 0.90,
        send_interval_sec: float = 0.03,
        chat_find_retries: int = 10,
        send_key_mode: str = "enter",
        image_send_wait_sec: float = 0.08,
        image_dialog_timeout_sec: float = 0.90,
        image_paste_settle_sec: float = 0.03,
        debug_log: bool = False,
        log_prefix: str = "kakao_pc_driver",
        send_max_attempts: int = 3,
        esc_presses_after_close: int = 1,
        ctrl_f_presses_after_close: int = 2,
        campaign_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        channel: Optional[str] = "KAKAO_PC",
        not_found_log_path: Optional[str] = None,
        open_in_main: bool = True,
        **_ignored: Any,
    ) -> None:
        self._hwnd = int(target_handle)

        if speed_profile is not None:
            self._profile = speed_profile
        else:
            m = (speed_mode or "fast").strip().lower()
            if m in ("slow", "slw"):
                self._profile = SpeedProfile.slow()
            elif m in ("normal", "default", "std", "standard", "norm"):
                self._profile = SpeedProfile.normal()
            else:
                self._profile = SpeedProfile.fast()

        self._speed_factor = float(self._profile.speed_factor)

        self._dib_cache: dict[str, bytes] = {}

        self._focus_delay = float(focus_delay)
        self._key_delay = float(key_delay)

        self._stop = False
        self._stop_event = threading.Event()

        self._block_input = bool(block_input)

        self._use_alt_tab_confirm = bool(use_alt_tab_confirm)
        self._alt_tab_max_steps = max(0, int(alt_tab_max_steps))
        self._alt_tab_pause = float(alt_tab_pause)

        self._kakao_locked = False
        self._chat_hwnd: int = 0

        self._mode: str = "MAIN"

        self._chat_input_ratio_y = float(chat_input_ratio_y)
        self._send_interval = max(0.02, float(send_interval_sec))
        self._chat_find_retries = max(3, int(chat_find_retries))

        self._image_send_wait = max(0.04, float(image_send_wait_sec))
        self._image_dialog_timeout = max(0.5, float(image_dialog_timeout_sec))
        self._image_paste_settle_sec = max(0.0, float(image_paste_settle_sec))

        self._search_ready: bool = False

        self._send_max_attempts = max(1, int(send_max_attempts))

        self._esc_presses_after_close = max(0, min(2, int(esc_presses_after_close)))
        self._ctrl_f_presses_after_close = max(1, min(2, int(ctrl_f_presses_after_close)))

        self._main_fallback_points: List[Tuple[int, int]] = []
        self._main_rect_cache: Tuple[int, int, int, int] = (0, 0, 0, 0)

        self._debug_log = bool(debug_log)
        self._logger = logging.getLogger(str(log_prefix or "kakao_pc_driver"))

        env_trace = str(os.getenv("KAKAO_TRACE", "")).strip().lower() in ("1", "true", "on", "yes")
        want_info = self._debug_log or env_trace

        self._logger.setLevel(logging.INFO if want_info else logging.WARNING)

        if want_info:
            fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
            if not self._logger.handlers:
                h = logging.StreamHandler(sys.stdout)
                h.setLevel(logging.INFO)
                h.setFormatter(fmt)
                self._logger.addHandler(h)
            self._logger.propagate = False

        self._desk: Optional[Any] = None

        self._campaign_id = (campaign_id or "").strip()
        self._batch_id = (batch_id or "").strip()
        self._channel = (channel or "KAKAO_PC").strip() or "KAKAO_PC"

        if not_found_log_path and str(not_found_log_path).strip():
            self._not_found_log_path = str(not_found_log_path).strip()
        else:
            self._not_found_log_path = os.path.join(os.getcwd(), "kakao_not_found_recipients.csv")

        self._last_image_bytes: bytes = b""
        self._ctrl_t_fallback_done: bool = False

        self._img_rr_mod: int = 4
        self._img_rr_idx: int = 0

        self._active_recipient: str = ""
        self._chat_in_main: bool = False

        self._last_focus_perf: float = 0.0
        self._last_focus_hwnd: int = 0

        # ✅ 입력창 컨트롤 캐시 (hwnd별)
        self._chat_input_ctrl_cache: dict[int, Any] = {}
        self._chat_input_ctrl_cache_ts: dict[int, float] = {}

        self._open_in_main = bool(open_in_main)
        self._chat_in_main = False  # 이미 있으니 이 줄은 "초기화 위치"만 보장하면 됩니다.

    # ----------------------------
    # speed helpers
    # ----------------------------
    def _sf(self, sec: float) -> float:
        s = max(0.0, float(sec))
        f = max(0.2, min(1.5, float(self._speed_factor)))
        return max(0.0, s * f)

    def _backoff(self) -> None:
        if not self._profile.auto_backoff:
            return
        self._speed_factor = min(self._profile.backoff_max, self._speed_factor + self._profile.backoff_step)
        if self._debug_log:
            self._logger.info(f"[SPEED] backoff -> speed_factor={self._speed_factor:.2f}")

    def _reset_speed(self) -> None:
        self._speed_factor = float(self._profile.speed_factor)

    # ----------------------------
    # logging helpers (CSV)
    # ----------------------------
    def _log_recipient_status(self, name: str, status: str) -> None:
        name = (name or "").strip()
        if not name:
            return

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = (status or "").strip() or "UNKNOWN"

        try:
            self._logger.info(
                "[RECIPIENT] "
                f"campaign={self._campaign_id} "
                f"batch={self._batch_id} "
                f"channel={self._channel} "
                f"recipient='{name}' "
                f"status={status} "
                f"time={ts}"
            )
        except Exception:
            pass

        try:
            os.makedirs(os.path.dirname(self._not_found_log_path) or ".", exist_ok=True)
            file_exists = os.path.exists(self._not_found_log_path)

            def _csv_escape(v: str) -> str:
                v = (v or "")
                if any(ch in v for ch in [",", "\n", "\r", '"']):
                    v = v.replace('"', '""')
                    return f'"{v}"'
                return v

            row = [ts, self._campaign_id, self._batch_id, self._channel, name, status]

            with open(self._not_found_log_path, "a", encoding="utf-8") as f:
                if not file_exists:
                    f.write("timestamp,campaign_id,batch_id,channel,recipient,status\n")
                f.write(",".join(_csv_escape(x) for x in row) + "\n")
        except Exception:
            pass

    def _log_not_found_recipient(self, name: str) -> None:
        self._log_recipient_status(name, "NOT_FOUND")

    def _check_stop(self) -> None:
        if self._stop or self._stop_event.is_set():
            raise StopNow("STOP_REQUESTED")

    def _sleep(self, sec: float) -> None:
        end = time.time() + self._sf(sec)
        while time.time() < end:
            self._check_stop()
            time.sleep(max(self._profile.poll_sleep_min, self._sf(self._profile.poll_sleep_default)))

    def _sleep_abs(self, sec: float) -> None:
        end = time.time() + max(0.0, float(sec))
        while time.time() < end:
            self._check_stop()
            time.sleep(0.02)

    def _log(self, msg: str) -> None:
        try:
            self._logger.info(msg)
        except Exception:
            print(msg)

    # ----------------------------
    # trace helpers (debug)
    # ----------------------------
    def _trace_on(self) -> bool:
        try:
            if self._debug_log:
                return True
            return str(os.getenv("KAKAO_TRACE", "")).strip() in ("1", "true", "TRUE", "on", "ON")
        except Exception:
            return bool(self._debug_log)

    def _trace(self, label: str, **kv: Any) -> None:
        if not self._trace_on():
            return
        try:
            ts = time.perf_counter()
            extra = " ".join([f"{k}={repr(v)}" for k, v in kv.items()])
            self._logger.info(f"[TRACE {ts:.6f}] {label} {extra}".rstrip())
            if not self._logger.handlers:
                print(f"[TRACE {ts:.6f}] {label} {extra}".rstrip())
        except Exception:
            pass

    def _get_desktop(self):
        if self._desk is not None:
            return self._desk
        Desktop, _, _ = _lazy_pywinauto()
        self._desk = Desktop(backend="win32")
        return self._desk

    def _send_keys_fast(self, keys: str) -> None:
        self._check_stop()
        _, send_keys, _ = _lazy_pywinauto()
        send_keys(keys, with_spaces=True, pause=self._sf(self._key_delay))
        self._check_stop()

    def _send_keys(self, keys: str, *, to_chat: bool) -> None:
        self._check_stop()
        _, send_keys, _ = _lazy_pywinauto()

        if to_chat:
            self._ensure_foreground_chat()
        else:
            if self._mode == "CHAT":
                return

            # ✅ 핵심: 이미 메인이 포그라운드면 "0.22s 폴링"을 타지 않는다
            try:
                if w32.get_foreground_hwnd() != int(self._hwnd):
                    self._ensure_foreground_main_fast()
            except Exception:
                # 예외 시엔 기존 동작(최후수단)
                self._ensure_foreground_main_fast()

        self._check_stop()
        send_keys(keys, with_spaces=True, pause=self._sf(self._key_delay))
        self._check_stop()

    @staticmethod
    def list_targets() -> List[KakaoTarget]:
        try:
            Desktop, _, _ = _lazy_pywinauto()
            desk = Desktop(backend="win32")
            wins = desk.windows(title_re=".*(카카오톡|KakaoTalk).*", visible_only=True)
            if not wins:
                wins = desk.windows(title_re=".*(카카오톡|KakaoTalk).*")
            out: List[KakaoTarget] = []
            for w in wins:
                try:
                    h = int(w.handle)
                    t = str(w.window_text() or "").strip()
                    if h and t:
                        out.append(KakaoTarget(title=t, handle=h))
                except Exception:
                    continue
            uniq = {x.handle: x for x in out}
            return list(uniq.values())
        except Exception:
            return []

    def start(self) -> None:
        self._stop = False
        self._stop_event.clear()
        self._img_rr_idx = 0

        self._get_desktop()
        self._lock_kakao_target_once()

        # chat hwnd 유효성
        if self._chat_hwnd and is_window(self._chat_hwnd) and self._chat_hwnd != self._hwnd:
            self._mode = "CHAT"
            self._ensure_foreground_chat()
            try:
                self._focus_chat_input_best_effort()
            except Exception:
                pass
            return

        self._mode = "MAIN"
        self._ensure_foreground_main_fast()
        self._search_ready = False
        self._cache_main_fallback_points()

    def recover(self) -> None:
        self._check_stop()
        self._lock_kakao_target_once()

        if self._mode == "CHAT":
            if self._chat_hwnd and is_window(self._chat_hwnd):
                self._ensure_foreground_chat()
                try:
                    self._focus_chat_input_best_effort()
                except Exception:
                    pass
                return
            self._mode = "MAIN"

        self._ensure_foreground_main_fast()
        self._cache_main_fallback_points()

    def stop(self) -> None:
        self._stop = True
        try:
            self._stop_event.set()
        except Exception:
            pass

    def _alt_tab_once(self, pause: float = 0.08) -> None:
        _, send_keys, _ = _lazy_pywinauto()
        self._check_stop()
        p = self._sf(pause)
        try:
            send_keys("{VK_MENU down}", pause=p)
            self._sleep(p)
            send_keys("{TAB}", pause=p)
            self._sleep(p)
        finally:
            try:
                send_keys("{VK_MENU up}", pause=p)
            except Exception:
                pass
            self._sleep(p)

    def _confirm_kakao_by_alt_tab(self, *, raise_on_fail: bool) -> bool:
        self._check_stop()

        fg = get_foreground_hwnd()
        fg_title = get_window_text(fg)
        if fg and is_kakaotalk_title(fg_title):
            self._hwnd = fg
            return True

        steps = max(1, self._alt_tab_max_steps) if self._alt_tab_max_steps > 0 else 0
        for _ in range(steps):
            self._check_stop()
            self._alt_tab_once(pause=self._alt_tab_pause)
            self._sleep(self._alt_tab_pause)
            fg = get_foreground_hwnd()
            fg_title = get_window_text(fg)
            if fg and is_kakaotalk_title(fg_title):
                self._hwnd = fg
                return True

        if raise_on_fail:
            raise RuntimeError("Alt+Tab으로 KakaoTalk 창을 찾지 못했습니다.\n- 카카오톡 실행/로그인 상태 확인\n")
        return False

    def _lock_kakao_target_once(self) -> None:
        if self._kakao_locked:
            return
        self._check_stop()

        title = get_window_text(self._hwnd)
        if self._hwnd and is_kakaotalk_title(title):
            self._kakao_locked = True
            self._use_alt_tab_confirm = False
            return

        if self._use_alt_tab_confirm:
            self._confirm_kakao_by_alt_tab(raise_on_fail=True)
            self._kakao_locked = True
            self._use_alt_tab_confirm = False
            return

        raise RuntimeError("카카오톡 창 핸들이 유효하지 않습니다. 창 목록 새로고침 후 다시 선택하세요.")

    def _cache_main_fallback_points(self) -> None:
        rect = get_window_rect(self._hwnd)
        if rect == (0, 0, 0, 0):
            return
        if rect == self._main_rect_cache:
            return
        self._main_rect_cache = rect

        l, t, r, b = rect
        w = r - l
        h = b - t
        if w < 300 or h < 300:
            return

        # ✅ 광고 영역(상단 중앙)을 피하고,
        #    좌측 채팅 리스트(상대적으로 안전) 쪽을 찍는다.
        #    - x: 좌측 18~24%
        #    - y: 상단 22~45% (배너/탭 영역 회피)
        pts: List[Tuple[int, int]] = [
            (int(l + w * 0.22), int(t + h * 0.28)),
            (int(l + w * 0.22), int(t + h * 0.38)),
            (int(l + w * 0.22), int(t + h * 0.48)),
        ]

        # 중복 제거
        self._main_fallback_points = list(dict.fromkeys(pts))

        if self._debug_log:
            self._log(f"[MAIN] fallback points updated(safe-left): {self._main_fallback_points}")

    # ----------------------------
    # foreground
    # ----------------------------
    def _ensure_foreground_chat(self) -> None:
        self._check_stop()

        # ✅ open-in-main 모드면: 메인창을 채팅 대상으로 간주
        if bool(getattr(self, "_chat_in_main", False)):
            self._mode = "CHAT"
            self._ensure_foreground_main_fast()
            self._sleep(min(0.02, self._focus_delay))
            return

        # chat hwnd 유효성
        if not self._chat_hwnd:
            self._mode = "MAIN"
            self._ensure_foreground_main_fast()
            return

        if not w32.is_window(self._chat_hwnd):
            self._chat_hwnd = 0
            self._mode = "MAIN"
            self._ensure_foreground_main_fast()
            return

        self._mode = "CHAT"

        # 이미 포그라운드면 최소 settle
        if w32.get_foreground_hwnd() == int(self._chat_hwnd):
            self._sleep(min(0.02, self._focus_delay))
            return

        t_fg = time.perf_counter()
        self._trace_fg("FG:before_force_chat")
        try:
            w32.force_foreground_strict(self._chat_hwnd, retries=3, sleep=self._sf(0.03))

            # =====================================================
            # ✅ ShadowWnd 보정(핵심)
            # - 포그라운드가 KakaoTalkShadowWnd면 실제 채팅창 hwnd로 재동기화
            # =====================================================
            try:
                fg = int(w32.get_foreground_hwnd() or 0)
                ft = str(w32.get_window_text(fg) or "")
                if "KakaoTalkShadowWnd" in ft:
                    real = w32.foreground_hwnd_if_same_process(self._hwnd)
                    if real and int(real) != fg and w32.is_window(int(real)):
                        self._trace("FG:shadow_detected", fg_hwnd=fg, fg_title=ft, real_hwnd=int(real))
                        self._chat_hwnd = int(real)
                        w32.force_foreground_strict(int(real), retries=2, sleep=self._sf(0.02))
            except Exception:
                pass

        finally:
            self._trace("FG:force_chat_done", ms=int((time.perf_counter() - t_fg) * 1000))
            self._trace_fg("FG:after_force_chat")

        self._sleep(min(0.03, self._focus_delay))

    def _snapshot_visible_hwnds(self) -> set[int]:
        out: set[int] = set()
        try:
            desk = self._get_desktop()
            for w in desk.windows(visible_only=True):
                try:
                    out.add(int(w.handle))
                except Exception:
                    continue
        except Exception:
            pass
        return out

    def _find_new_chat_hwnd(self, name: str, before: set[int]) -> int:
        try:
            desk = self._get_desktop()
            wins = desk.windows(visible_only=True)

            name = (name or "").strip()

            new_hwnds: list[int] = []
            new_name_hwnds: list[int] = []
            any_name_hwnds: list[int] = []

            for w in wins:
                try:
                    h = int(w.handle)
                    if not h or h == self._hwnd:
                        continue

                    # ✅ 토스트 배제
                    if _is_kakao_toast_quick_reply(
                            hwnd=h,
                            main_hwnd=int(self._hwnd),
                            get_pid=w32.get_pid,
                            get_window_rect=w32.get_window_rect,
                            lazy_pywinauto=_lazy_pywinauto,
                    ):
                        continue

                    t = str(w.window_text() or "").strip()
                    is_new = (h not in before)
                    if is_new:
                        new_hwnds.append(h)
                    if name and t and (name in t):
                        any_name_hwnds.append(h)
                        if is_new:
                            new_name_hwnds.append(h)
                except Exception:
                    continue

            if new_name_hwnds:
                return new_name_hwnds[-1]
            if len(new_hwnds) == 1:
                return new_hwnds[0]
            if any_name_hwnds:
                return any_name_hwnds[-1]
            if new_hwnds:
                return new_hwnds[-1]
        except Exception:
            pass
        return 0

    def _focus_chat_input_best_effort(self, *, fast_only: bool = False) -> bool:
        self._check_stop()

        target_hwnd = int(self._chat_hwnd or self._hwnd)
        if not target_hwnd or not w32.is_window(int(target_hwnd)):
            return False

        # ✅ open-in-main이면: 광고/링크 카드 클릭 리스크가 있어서 "좌표 클릭" 금지
        in_main = bool(getattr(self, "_chat_in_main", False))

        # (0) 캐시 set_focus (가장 빠르고 안전)
        ctrl = self._get_cached_chat_input_ctrl(target_hwnd)
        if ctrl is not None:
            try:
                ctrl.set_focus()
                time.sleep(0.004)
                self._last_focus_perf = time.perf_counter()
                self._last_focus_hwnd = int(target_hwnd)
                return True
            except Exception:
                self._invalidate_chat_input_cache(target_hwnd)

        # ✅ OPEN_CHAT 단계(fast_only)에서는 무거운 탐색/클릭 금지
        #    - 단, open-in-main에서는 좌표 클릭을 하면 사고가 나므로
        #      fast_only라도 "컨트롤 탐색(set_focus)"는 허용(최소 1회)
        if fast_only and (not in_main):
            # 개인창 fast_only: 여기서 끝 (좌표 클릭도 생략)
            return False

        # (C) 컨트롤 탐색 + 캐싱 (open-in-main에서도 안전하게 여기로 유도)
        ctrl2 = self._find_and_cache_chat_input_ctrl(target_hwnd)
        if ctrl2 is not None:
            try:
                ctrl2.set_focus()
                time.sleep(0.006)
                self._last_focus_perf = time.perf_counter()
                self._last_focus_hwnd = int(target_hwnd)
                return True
            except Exception:
                self._invalidate_chat_input_cache(target_hwnd)

        # ---- 아래는 "개인창"에서만 허용되는 빠른 좌표 클릭 루트 ----
        if in_main:
            # open-in-main은 여기서 종료 (좌표 클릭 금지)
            return False

        # (A) SendInput 클릭 (개인창에서만)
        try:
            l, t, r, b = w32.get_window_rect(int(target_hwnd))
            if (r - l) > 200 and (b - t) > 200:
                x = int(l + (r - l) * 0.50)
                y_candidates = [
                    int(t + (b - t) * self._chat_input_ratio_y),
                    int(b - 90),
                    int(b - 120),
                ]
                for y in y_candidates:
                    ok = w32.sendinput_click(x, y)
                    time.sleep(0.005)
                    if ok:
                        self._last_focus_perf = time.perf_counter()
                        self._last_focus_hwnd = int(target_hwnd)
                        return True
        except Exception:
            pass

        # ✅ 여기서 fast_only면 더 이상 진행 금지
        if fast_only:
            return False

        # (B) pywinauto click fallback (개인창에서만)
        try:
            _, _, click = _lazy_pywinauto()
            l, t, r, b = w32.get_window_rect(int(target_hwnd))
            if (r - l) > 200 and (b - t) > 200:
                x = int(l + (r - l) * 0.50)
                y = int(b - 100)
                click(coords=(x, y))
                time.sleep(0.008)
                self._last_focus_perf = time.perf_counter()
                self._last_focus_hwnd = int(target_hwnd)
                return True
        except Exception:
            pass

        return False

    def _get_chat_input_text_best_effort(self) -> str:
        Desktop, _, _ = _lazy_pywinauto()
        target_hwnd = self._chat_hwnd or self._hwnd
        try:
            win = Desktop(backend="win32").window(handle=target_hwnd)
            candidates = []
            for cls in ("RICHEDIT50W", "RichEdit20W", "RichEdit", "Edit"):
                try:
                    candidates.extend(win.descendants(class_name=cls))
                except Exception:
                    pass

            def _bottom_y(ctrl) -> int:
                try:
                    r = ctrl.rectangle()
                    return int(r.bottom)
                except Exception:
                    return -1

            if candidates:
                ctrl = sorted(candidates, key=_bottom_y, reverse=True)[0]
                try:
                    return (ctrl.window_text() or "").strip()
                except Exception:
                    pass
        except Exception:
            pass
        return ""

    def _patch_chat_hwnd_from_foreground(self, name: str) -> None:
        self._check_stop()
        fg = w32.get_foreground_hwnd()
        if not fg or fg == int(self._hwnd):
            return

        title = w32.get_window_text(int(fg))
        if name and (name in title) and w32.is_window(int(fg)):
            self._chat_hwnd = int(fg)
            self._mode = "CHAT"
            if self._debug_log:
                self._log(f"[CHAT] patched from foreground hwnd={fg} title='{title}'")

    # ----------------------------
    # open chat hook
    # ----------------------------
    def _open_chat_by_name(self, name: str) -> bool:
        t0 = time.perf_counter()
        self._trace("OPEN_CHAT:begin", name=(name or "").strip())

        self._check_stop()
        name = (name or "").strip()
        if not name:
            return False

        # ✅ open context reset
        self._chat_in_main = False
        self._chat_hwnd = 0
        self._mode = "MAIN"
        self._search_ready = False  # 매 수신자마다 검색창 상태 재확보

        self._chat_input_ctrl_cache.clear()
        self._chat_input_ctrl_cache_ts.clear()

        self._active_recipient = name
        self._last_image_bytes = b""
        self._ctrl_t_fallback_done = False

        def _send_keys_main(keys: str) -> None:
            self._send_keys(keys, to_chat=False)

        def _send_keys_chat(keys: str) -> None:
            self._send_keys(keys, to_chat=True)

        def _set_chat_hwnd(hwnd: int) -> None:
            """
            hwnd 의미
            - hwnd > 0 : 새 개인창 핸들
            - hwnd == 0: open-in-main (메인창 내 채팅)
            """
            h = int(hwnd or 0)
            if h <= 0:
                self._chat_in_main = True
                self._chat_hwnd = int(self._hwnd)  # 메인창
                self._mode = "CHAT"
                return

            self._chat_in_main = False
            self._chat_hwnd = h
            self._mode = "CHAT"

        def _get_search_ready() -> bool:
            return bool(self._search_ready)

        def _set_search_ready(v: bool) -> None:
            self._search_ready = bool(v)

        # ------------------------------
        # hook 실행
        # ------------------------------
        try:
            t_hook0 = time.perf_counter()
            self._trace("OPEN_CHAT:hook_call")

            open_chat_by_name_hook(
                name=name,
                ensure_foreground_main=lambda: self._ensure_foreground_main_fast(),
                send_keys_main=_send_keys_main,
                set_clipboard_text=w32.set_clipboard_text,
                snapshot_visible_hwnds=self._snapshot_visible_hwnds,
                find_new_chat_hwnd=self._find_new_chat_hwnd,
                set_chat_hwnd=_set_chat_hwnd,
                ensure_foreground_chat=self._ensure_foreground_chat,
                send_keys_chat=_send_keys_chat,
                focus_chat_input_best_effort=self._focus_chat_input_best_effort,
                chat_find_retries=self._chat_find_retries,
                log=self._log,
                debug=self._debug_log,
                get_search_ready=_get_search_ready,
                set_search_ready=_set_search_ready,
                backspace_extra=0,
                poll_sleep=max(self._profile.poll_sleep_min, self._sf(self._profile.poll_sleep_default)),
                prefer_open_in_main=bool(self._open_in_main),
                timings={
                    "search_open_delay": self._sf(self._profile.hooks.search_open_delay),
                    "select_home_delay": self._sf(self._profile.hooks.select_home_delay),
                    "select_end_delay": self._sf(self._profile.hooks.select_end_delay),
                    "delete_delay": self._sf(self._profile.hooks.delete_delay),
                    "extra_delete_delay": self._sf(self._profile.hooks.extra_delete_delay),
                    "paste_name_delay": self._sf(self._profile.hooks.paste_name_delay),
                    "open_wait1": self._sf(0.16),
                    "open_wait2": self._sf(0.18),
                    "enter1_post_key_sleep": self._sf(0.008),
                    "enter2_post_key_sleep": self._sf(0.008),
                },
                get_foreground_hwnd=w32.get_foreground_hwnd,
                get_window_text=w32.get_window_text,
                is_search_no_result=self._is_main_search_no_result,
            )

            self._trace(
                "OPEN_CHAT:hook_done",
                ms=int((time.perf_counter() - t_hook0) * 1000),
                chat_hwnd=int(self._chat_hwnd),
                mode=self._mode,
                chat_in_main=bool(self._chat_in_main),
            )

        except ChatNotFound:
            self._log_not_found_recipient(name)
            self._chat_in_main = False
            self._chat_hwnd = 0
            self._mode = "MAIN"
            self._trace("OPEN_CHAT:fail", total_ms=int((time.perf_counter() - t0) * 1000), chat_hwnd=0)
            return False

        # ------------------------------
        # ✅ 핵심: 개인창만 성공 처리
        # ------------------------------
        if bool(self._chat_in_main):
            # open-in-main이면 전송하면 안 됨 -> 스킵하고 다음 사람
            self._trace("OPEN_CHAT:skip_open_in_main", recipient=name, main_hwnd=int(self._hwnd))
            self._log_recipient_status(name, "SKIP_OPEN_IN_MAIN")

            self._chat_in_main = False
            self._chat_hwnd = 0
            self._mode = "MAIN"
            try:
                self._ensure_foreground_main_fast()
            except Exception:
                pass
            return False

        # 개인창 hwnd 유효성 체크
        if not (self._chat_hwnd and self._chat_hwnd != self._hwnd and w32.is_window(int(self._chat_hwnd))):
            self._log_not_found_recipient(name)
            self._chat_hwnd = 0
            self._mode = "MAIN"
            self._trace("OPEN_CHAT:fail", total_ms=int((time.perf_counter() - t0) * 1000), chat_hwnd=0)
            return False

        # 개인창 전면화
        try:
            self._mode = "CHAT"
            self._ensure_foreground_chat()
        except Exception:
            pass

        self._trace("OPEN_CHAT:success", total_ms=int((time.perf_counter() - t0) * 1000),
                    chat_hwnd=int(self._chat_hwnd))
        return True

    # ----------------------------
    # retry runner
    # ----------------------------
    def _run_with_retry(self, label: str, fn: Callable[[], bool]) -> bool:
        attempts = int(self._send_max_attempts or 1)
        for i in range(1, attempts + 1):
            self._check_stop()
            try:
                ok = bool(fn())
            except StopNow:
                raise
            except Exception as e:
                self._log(f"[{label}] attempt {i}/{attempts} exception: {e}")
                ok = False

            if ok:
                if i > 1:
                    self._log(f"[{label}] success on attempt {i}/{attempts}")
                self._reset_speed()
                return True

            self._log(f"[{label}] fail attempt {i}/{attempts} -> backoff")
            self._backoff()
            self._sleep(0.12)

        return False

    @staticmethod
    def _text_remain_means_fail(remain: str, sent_text: str) -> bool:
        r = (remain or "").strip()
        s = (sent_text or "").strip()
        if not s or not r:
            return False
        key = s[:120]
        return key.lower() in r.lower()

    # ----------------------------
    # send text
    # ----------------------------
    def _paste_text_and_send_once(self, text: str) -> bool:
        self._check_stop()
        text = (text or "").strip()
        if not text:
            return True

        t0 = time.perf_counter()
        self._trace("TEXT:once_begin", chars=len(text))

        if self._chat_hwnd and not w32.is_window(int(self._chat_hwnd)):
            self._chat_hwnd = 0
            self._mode = "MAIN"

        self._ensure_foreground_chat()
        self._focus_chat_input_best_effort()
        self._sleep(max(0.02, self._send_interval))

        t_cb0 = time.perf_counter()
        w32.set_clipboard_text(text)  # ✅ win32_core 사용
        self._trace("TEXT:clipboard_set", ms=int((time.perf_counter() - t_cb0) * 1000))
        self._sleep(0.02)

        self._send_keys("^v", to_chat=True)
        self._sleep(0.02)

        self._send_keys("{ENTER}", to_chat=True)
        self._trace("TEXT:enter_sent")
        self._sleep(0.04)

        remain = self._get_chat_input_text_best_effort()
        fail = self._text_remain_means_fail(remain, text)
        self._trace("TEXT:once_end", ok=(not fail), total_ms=int((time.perf_counter() - t0) * 1000),
                    remain_len=len(remain))
        return not fail

    def _paste_text_and_send(self, text: str) -> bool:
        text = (text or "").strip()
        if not text:
            return True
        return self._run_with_retry("TEXT", lambda: self._paste_text_and_send_once(text))

    # ----------------------------
    # send image
    # ----------------------------
    def _paste_image_and_send_once(self, png_bytes: bytes) -> bool:
        self._check_stop()
        if not png_bytes:
            return True

        t0 = time.perf_counter()
        self._trace("IMG:once_begin", bytes_len=len(png_bytes))
        self._last_image_bytes = png_bytes

        # hwnd 만료 체크
        if self._chat_hwnd and not w32.is_window(int(self._chat_hwnd)):
            self._chat_hwnd = 0
            self._mode = "MAIN"

        # (1) DIB 변환/캐시
        t_dib0 = time.perf_counter()
        dib = self._png_to_dib_bytes(png_bytes)
        self._trace("IMG:dib_ready", ms=int((time.perf_counter() - t_dib0) * 1000), dib_len=len(dib))

        # (2) Ctrl+V 붙여넣기 + 모달 엔터 전송 (분리 모듈)
        ok = attach_image_via_ctrl_v(
            dib_bytes=dib,
            active_recipient=str(self._active_recipient or ""),
            kakao_main_hwnd=int(self._hwnd),
            chat_hwnd=int(self._chat_hwnd or self._hwnd),

            # win32/env
            user32=w32.user32,
            get_foreground_hwnd=w32.get_foreground_hwnd,
            get_window_text=w32.get_window_text,
            get_class_name=w32.get_class_name,
            get_pid=w32.get_pid,
            set_clipboard_dib=w32.set_clipboard_dib,
            lazy_pywinauto=_lazy_pywinauto,  # ✅ 반드시 전달

            # actions
            ensure_foreground_chat=self._ensure_foreground_chat,
            focus_chat_input_best_effort=lambda: bool(self._focus_chat_input_best_effort()),
            send_keys_chat=lambda keys: self._send_keys(keys, to_chat=True),
            sleep=self._sleep,
            sleep_abs=self._sleep_abs,

            # dialog
            send_image_dialog_hook=send_image_dialog_hook,
            image_dialog_timeout_sec=self._sf(self._image_dialog_timeout),
            key_delay=self._sf(self._key_delay),
            debug=bool(self._debug_log),
            log=self._log,
            timings={
                "try_interval": self._sf(self._profile.img_dlg.try_interval),
                "loop_sleep": self._sf(self._profile.img_dlg.loop_sleep),
                "post_click_sleep": self._sf(self._profile.img_dlg.post_click_sleep),
                "enter_gap_sec": self._sf(self._profile.img_dlg.enter_gap_sec),
            },
            prefer_hwnd=int(self._chat_hwnd or self._hwnd),

            # post
            restore_chat_focus_after_image_dialog=self._restore_chat_focus_after_image_dialog,

            # trace/debug
            trace=self._trace,
            dump_mismatch_debug=self._dump_mismatch_debug,
            image_paste_settle_sec=float(self._image_paste_settle_sec or 0.0),
        )

        if not ok:
            self._trace("IMG:once_end", ok=False, total_ms=int((time.perf_counter() - t0) * 1000))
            return False

        # (3) 후처리
        self._sleep(max(0.02, self._send_interval))
        self._trace("IMG:once_end", ok=True, total_ms=int((time.perf_counter() - t0) * 1000))
        return True

    def _paste_image_and_send(self, png_bytes: bytes) -> bool:
        if not png_bytes:
            return True

        # 3번은 클립보드, 1번은 Ctrl+T
        rr_mod = 4
        idx = int(getattr(self, "_img_rr_idx", 0))
        use_ctrl_t = (idx % rr_mod) == (rr_mod - 1)
        self._img_rr_idx = idx + 1

        if use_ctrl_t:
            self._trace("IMG:route", route="CTRL_T", rr_idx=idx)
            return self._run_with_retry(
                "IMG_CTRL_T",
                lambda: self._send_image_via_ctrl_t_once(png_bytes),
            )

        self._trace("IMG:route", route="CLIPBOARD", rr_idx=idx)
        return self._run_with_retry(
            "IMG",
            lambda: self._paste_image_and_send_once(png_bytes),
        )

    def _send_image_via_ctrl_t_once(self, png_bytes: bytes) -> bool:
        self._check_stop()
        if not png_bytes:
            return True

        try:
            self._ensure_foreground_chat()
            self._focus_chat_input_best_effort()
            self._sleep_abs(0.02)
        except Exception:
            pass

        try:
            ok = send_png_via_ctrl_t(
                png_bytes=png_bytes,
                send_keys_fast=self._send_keys_fast,
                set_clipboard_text=w32.set_clipboard_text,
                ensure_foreground_chat=self._ensure_foreground_chat,
                focus_chat_input_best_effort=self._focus_chat_input_best_effort,
                sleep_abs=self._sleep_abs,
                send_image_dialog_hook=send_image_dialog_hook,
                timeout_sec=max(1.2, self._sf(float(self._image_dialog_timeout))),
                key_delay=self._sf(self._key_delay),
                debug=self._debug_log,
                log=self._log,
                prefer_hwnd=int(self._chat_hwnd or self._hwnd),
                get_foreground_hwnd=w32.get_foreground_hwnd,
                timings={
                    "focus_settle": self._sf(self._profile.ctrl_t.focus_settle),
                    "after_ctrl_t": self._sf(self._profile.ctrl_t.after_ctrl_t),
                    "clipboard_settle": self._sf(self._profile.ctrl_t.clipboard_settle),
                    "after_paste_path": self._sf(self._profile.ctrl_t.after_paste_path),
                    "after_enter_path": self._sf(self._profile.ctrl_t.after_enter_path),
                },
                dlg_timings={
                    "try_interval": self._sf(self._profile.img_dlg.try_interval),
                    "loop_sleep": self._sf(self._profile.img_dlg.loop_sleep),
                    "post_click_sleep": self._sf(self._profile.img_dlg.post_click_sleep),
                    "enter_gap_sec": self._sf(self._profile.img_dlg.enter_gap_sec),
                },
            )
        except Exception as e:
            self._log(f"[CTRL+T] send exception: {e}")
            return False

        if ok:
            try:
                self._restore_chat_focus_after_image_dialog()
            except Exception:
                pass

        return bool(ok)

    # ----------------------------
    # image dialog 이후 포커스 복구 (핵심 안정화)
    # ----------------------------
    def _restore_chat_focus_after_image_dialog(self) -> None:
        """
        이미지 전송 다이얼로그 처리 직후:
        - 채팅창을 확실히 전면화
        - 입력창에 set_focus
        - last_focus 캐시 갱신
        """
        try:
            target = int(self._chat_hwnd or self._hwnd)
            if not target or not w32.is_window(target):
                return

            # 1) 강제 전면화
            try:
                w32.force_foreground_strict(target, retries=3, sleep=self._sf(0.03))
            except Exception:
                pass

            # 2) 입력창 포커스
            try:
                self._focus_chat_input_best_effort(fast_only=False)
            except Exception:
                pass

            # 3) last focus 갱신 (focus skip 로직 안정화)
            self._last_focus_hwnd = target
            self._last_focus_perf = time.perf_counter()

            self._trace("IMG:focus_restored", hwnd=target)

        except Exception:
            pass






    # ---------------------------------------------------------
    # 팝업 처리(전송 중 파일)
    # ---------------------------------------------------------
    def _dismiss_file_sending_close_popup(
        self,
        *,
        timeout_sec: float = 1.2,
        force_action: str = "",
    ) -> str:
        self._check_stop()

        end = time.time() + max(0.3, float(timeout_sec))
        desk = None
        try:
            desk = self._get_desktop()
        except Exception:
            desk = None

        KEY_A = "전송 중인 파일"
        KEY_B = "전송"

        force_action = (force_action or "").upper().strip()

        while time.time() < end:
            self._check_stop()
            try:
                if desk is None:
                    Desktop, _, _ = _lazy_pywinauto()
                    desk = Desktop(backend="win32")

                dialogs = desk.windows(class_name="#32770", visible_only=True)
                found_any = False

                for dlg in dialogs:
                    try:
                        texts = " ".join([t for t in dlg.texts() if t]).strip()
                        if (KEY_A in texts) and (KEY_B in texts):
                            found_any = True

                            if force_action == "CONFIRM":
                                primary = ("확인", "예", "계속", "닫기", "OK", "Yes")
                                secondary = ("취소", "아니오", "No", "Cancel")
                            else:
                                primary = ("취소", "아니오", "No", "Cancel")
                                secondary = ("확인", "예", "계속", "닫기", "OK", "Yes")

                            def _click_any(btn_titles) -> Optional[str]:
                                for bn in btn_titles:
                                    try:
                                        btn = dlg.child_window(title=bn, control_type="Button")
                                        if btn.exists(timeout=0.1):
                                            btn.click_input()
                                            self._sleep_abs(0.10)
                                            if bn in ("취소", "아니오", "No", "Cancel"):
                                                return "CANCEL"
                                            return "CONFIRM"
                                    except Exception:
                                        continue
                                return None

                            r = _click_any(primary)
                            if r is None:
                                r = _click_any(secondary)

                            if r in ("CANCEL", "CONFIRM"):
                                return r

                            try:
                                dlg.set_focus()
                                self._sleep_abs(0.04)
                                self._send_keys_fast("{ENTER}")
                                self._sleep_abs(0.10)
                                return "CONFIRM"
                            except Exception:
                                pass

                    except Exception:
                        continue

                if not found_any:
                    return ""

            except Exception:
                pass

            time.sleep(0.08)

        return ""

    def _close_chat_esc_with_popup_handling(self) -> None:
        self._check_stop()

        max_esc_attempts = 6
        retry_gap_sec = 0.18

        for attempt in range(1, max_esc_attempts + 1):
            self._check_stop()

            if not (self._chat_hwnd and is_window(self._chat_hwnd)):
                return

            self._sleep_abs(0.10)

            try:
                self._send_keys_fast("{ESC}")
            except Exception:
                pass

            self._sleep_abs(0.12)

            if not (self._chat_hwnd and is_window(self._chat_hwnd)):
                return

            force = "CONFIRM" if attempt == 6 else "CANCEL"

            pop_result = ""
            try:
                pop_result = self._dismiss_file_sending_close_popup(timeout_sec=0.9, force_action=force)
            except Exception:
                pop_result = ""

            if pop_result == "CANCEL":
                self._sleep_abs(retry_gap_sec)
                continue

            if pop_result == "CONFIRM":
                raise CloseForcedByConfirm("close 단계에서 '확인'으로 강제 종료됨(실패로 기록)")

            self._sleep_abs(0.10)

        raise RuntimeError("개인창 닫기 재시도 초과: ESC 6회 수행 후에도 창이 닫히지 않습니다.")

    def _close_chat(self) -> None:
        self._check_stop()

        t0 = time.perf_counter()
        self._trace(
            "CLOSE_CHAT:begin",
            chat_hwnd=int(self._chat_hwnd),
            main_hwnd=int(self._hwnd),
            mode=self._mode,
        )

        # ✅ open-in-main 모드(기존 유지)
        if bool(getattr(self, "_chat_in_main", False)):
            try:
                self._ensure_foreground_main_fast()
                self._sleep_abs(0.03)

                for _ in range(max(1, int(self._esc_presses_after_close or 1))):
                    try:
                        self._send_keys_fast("{ESC}")
                    except Exception:
                        pass
                    self._sleep_abs(0.03)

                # open-in-main은 여기서 Ctrl+F 열어두는게 실제로 이득인 경우가 많아 유지
                for _ in range(max(1, int(self._ctrl_f_presses_after_close or 1))):
                    try:
                        self._send_keys_fast("^f")
                    except Exception:
                        pass
                    self._sleep_abs(0.03)

            except Exception:
                pass

            if self._chat_hwnd:
                self._invalidate_chat_input_cache(int(self._chat_hwnd))

            self._chat_hwnd = 0
            self._mode = "MAIN"
            self._chat_in_main = False
            self._search_ready = True

            self._trace("CLOSE_CHAT:end", total_ms=int((time.perf_counter() - t0) * 1000))
            return

        # ------------------------------
        # 개인창 close (기존 유지)
        # ------------------------------
        forced_fail = False
        forced_err: Optional[Exception] = None

        if self._chat_hwnd and self._chat_hwnd != self._hwnd:
            t1 = time.perf_counter()
            try:
                self._ensure_foreground_chat()
                self._sleep(0.03)

                t2 = time.perf_counter()
                self._close_chat_esc_with_popup_handling()
                self._trace("CLOSE_CHAT:esc_done", ms=int((time.perf_counter() - t2) * 1000))

            except CloseForcedByConfirm as e:
                forced_fail = True
                forced_err = e
                self._log_recipient_status(self._active_recipient, "CLOSE_FORCED_CONFIRM")
                self._trace("CLOSE_CHAT:forced_confirm", recipient=self._active_recipient)

            except StopNow:
                raise
            except Exception as e:
                self._trace("CLOSE_CHAT:close_exception", err=str(e))

            self._sleep(0.10)
            self._trace("CLOSE_CHAT:chat_block_done", ms=int((time.perf_counter() - t1) * 1000))

        # reset
        self._chat_hwnd = 0
        self._mode = "MAIN"
        self._chat_in_main = False

        # ✅ 메인 복귀
        t3 = time.perf_counter()
        self._ensure_foreground_main_fast()
        self._trace("CLOSE_CHAT:back_to_main", ms=int((time.perf_counter() - t3) * 1000))

        # ✅ 핵심 변경: 여기서 Ctrl+F를 "절대" 다시 치지 않는다.
        #    (이미 검색창 커서가 살아있으면 Ctrl+F가 오히려 깜빡임/포커스 튐 유발)
        self._search_ready = True
        self._trace("CLOSE_CHAT:assume_search_ready", ready=True)

        self._trace("CLOSE_CHAT:end", total_ms=int((time.perf_counter() - t0) * 1000))

        if forced_fail and forced_err is not None:
            raise forced_err

    def _force_send_image_via_ctrl_t_once(self) -> bool:
        self._check_stop()

        if self._ctrl_t_fallback_done:
            return False
        self._ctrl_t_fallback_done = True

        png_bytes = self._last_image_bytes or b""
        if not png_bytes:
            self._log("[CTRL+T] skip: last_image_bytes is empty")
            return False

        ok = False
        try:

            ok = send_png_via_ctrl_t(
                png_bytes=png_bytes,
                send_keys_fast=self._send_keys_fast,
                set_clipboard_text=set_clipboard_text,  # ✅ win32_core
                ensure_foreground_chat=self._ensure_foreground_chat,
                focus_chat_input_best_effort=self._focus_chat_input_best_effort,
                sleep_abs=self._sleep_abs,
                send_image_dialog_hook=send_image_dialog_hook,
                timeout_sec=max(1.2, self._sf(float(self._image_dialog_timeout))),
                key_delay=self._sf(self._key_delay),
                debug=self._debug_log,
                log=self._log,

                # ✅ 여기 2줄 추가
                prefer_hwnd=int(self._chat_hwnd or self._hwnd),
                get_foreground_hwnd=w32.get_foreground_hwnd,

                timings={
                    "focus_settle": self._sf(self._profile.ctrl_t.focus_settle),
                    "after_ctrl_t": self._sf(self._profile.ctrl_t.after_ctrl_t),
                    "clipboard_settle": self._sf(self._profile.ctrl_t.clipboard_settle),
                    "after_paste_path": self._sf(self._profile.ctrl_t.after_paste_path),
                    "after_enter_path": self._sf(self._profile.ctrl_t.after_enter_path),
                },
                dlg_timings={
                    "try_interval": self._sf(self._profile.img_dlg.try_interval),
                    "loop_sleep": self._sf(self._profile.img_dlg.loop_sleep),
                    "post_click_sleep": self._sf(self._profile.img_dlg.post_click_sleep),
                    "enter_gap_sec": self._sf(self._profile.img_dlg.enter_gap_sec),
                },
            )
        except Exception as e:
            self._log(f"[CTRL+T] fallback exception: {e}")
            ok = False

        self._log(f"[CTRL+T] fallback send result={ok}")
        return bool(ok)

    # ----------------------------
    # send APIs
    # ----------------------------
    def send_campaign_items(self, name: str, campaign_items: List[Any]) -> None:
        t0 = time.perf_counter()
        self._trace("SEND_CAMPAIGN:begin", name=(name or "").strip(), items_type=str(type(campaign_items)))

        self._check_stop()
        self._lock_kakao_target_once()

        name = (name or "").strip()
        if not name:
            raise ValueError("수신자 이름이 비어있습니다.")

        # ✅ 전송 중에는 개인창만 허용
        _prev_open_in_main = bool(self._open_in_main)
        self._open_in_main = False
        try:
            # ---- 기존 로직 그대로 ----
            items = list(campaign_items or [])

            prepared: list[tuple[str, str, bytes]] = []
            for it in items:
                typ = str(getattr(it, "item_type", "") or "").upper().strip()
                if typ == "TEXT":
                    t = (getattr(it, "text", "") or "").strip()
                    prepared.append(("TEXT", t, b""))
                else:
                    b = getattr(it, "image_bytes", b"") or b""
                    try:
                        b = bytes(b)
                    except Exception:
                        pass
                    prepared.append(("IMG", "", b))

            opened = self._open_chat_by_name(name)
            if not opened:
                return

            failures: List[str] = []
            sent_any = False
            try:
                for idx, (typ, t, b) in enumerate(prepared, start=1):
                    self._check_stop()

                    if typ == "TEXT":
                        if t:
                            ok = self._paste_text_and_send(t)
                            sent_any = True
                            if not ok:
                                failures.append(f"{idx}:TEXT:retry_exceeded")
                    else:
                        if b:
                            ok = self._paste_image_and_send(b)
                            sent_any = True
                            if not ok:
                                failures.append(f"{idx}:IMG:retry_exceeded")

                    self._sleep(max(0.02, self._send_interval))

                if not sent_any:
                    raise RuntimeError("캠페인 아이템이 비어있어 전송할 내용이 없습니다.")
            finally:
                try:
                    self._close_chat()
                except CloseForcedByConfirm:
                    failures.append("CLOSE_FORCED_CONFIRM")
                except Exception as e:
                    self._trace("SEND_CAMPAIGN:close_chat_exception", err=str(e))

            if failures:
                raise RuntimeError("일부 아이템 전송 실패:\n" + "\n".join(failures))

        finally:
            # ✅ 원복
            self._open_in_main = _prev_open_in_main

    def send_to_name(self, name: str, message: str, image_bytes_list: List[bytes]) -> None:
        self._check_stop()
        self._lock_kakao_target_once()

        name = (name or "").strip()
        if not name:
            raise ValueError("수신자 이름이 비어있습니다.")

        opened = self._open_chat_by_name(name)
        if not opened:
            return

        failures: List[str] = []
        try:
            msg = (message or "").strip()
            if msg:
                ok = self._paste_text_and_send(msg)
                if not ok:
                    failures.append("TEXT:retry_exceeded")

            for i, b in enumerate((image_bytes_list or []), start=1):
                self._check_stop()
                if not b:
                    continue
                ok = self._paste_image_and_send(b)
                if not ok:
                    failures.append(f"IMG#{i}:retry_exceeded")
                self._sleep(max(0.02, self._send_interval))
        finally:
            try:
                self._close_chat()
            except CloseForcedByConfirm:
                failures.append("CLOSE_FORCED_CONFIRM")
            except StopNow:
                raise
            except Exception as e:
                self._trace("SEND_TO_NAME:close_chat_exception", err=str(e))

        if failures:
            raise RuntimeError("일부 전송 실패:\n" + "\n".join(failures))

    # ----------------------------
    # main foreground
    # ----------------------------
    def _ensure_foreground_main_fast(self) -> None:
        self._check_stop()

        # (1) 최대한 "클릭 없이" 포그라운드 잡기
        try:
            w32.user32.ShowWindow(wintypes.HWND(self._hwnd), w32.SW_RESTORE)
        except Exception:
            pass
        try:
            w32.user32.SetForegroundWindow(wintypes.HWND(self._hwnd))
        except Exception:
            pass

        grace_end = time.time() + self._sf(0.22)
        while time.time() < grace_end:
            self._check_stop()

            # 메인과 같은 프로세스의 채팅창이 올라온 경우 즉시 CHAT 모드로
            fg_chat = w32.foreground_hwnd_if_same_process(self._hwnd)
            if fg_chat:
                self._chat_hwnd = int(fg_chat)
                self._mode = "CHAT"
                return

            if w32.get_foreground_hwnd() == int(self._hwnd):
                return

            time.sleep(max(self._profile.poll_sleep_min, self._sf(self._profile.poll_sleep_default)))

        # (2) 여기까지 오면 "포그라운드가 안 잡힘"
        #     ✅ 기존처럼 중앙/상단을 찍지 말고,
        #     ✅ 좌측 리스트 안전영역만 1회 클릭(광고 오작동 방지)
        self._cache_main_fallback_points()
        if self._main_fallback_points:
            x, y = self._main_fallback_points[0]
            w32.fallback_click_point(x, y)
            self._sleep(0.02)

        # 클릭 후 한번 더 확인
        if w32.get_foreground_hwnd() == int(self._hwnd):
            return

        fg_chat = w32.foreground_hwnd_if_same_process(self._hwnd)
        if fg_chat:
            self._chat_hwnd = int(fg_chat)
            self._mode = "CHAT"
            return

    def _is_clipboard_image_dialog_foreground(self, fg_hwnd: int) -> bool:
        """
        현재 foreground hwnd가 '클립보드 이미지 전송' 모달(#32770)인지 판별.
        - 이 모달은 title이 '' 인 경우가 많아서, title로는 판별 불가.
        - 같은 프로세스(pid) + #32770 + texts에 '클립보드 이미지 전송' 포함이면 True.
        """
        try:
            fg = int(fg_hwnd or 0)
            if fg <= 0:
                return False

            # 같은 프로세스인지(카카오톡 프로세스)
            try:
                if int(w32.get_pid(fg) or 0) != int(w32.get_pid(self._hwnd) or 0):
                    return False
            except Exception:
                return False

            # pywinauto로 다이얼로그/텍스트 확인 (가드에 걸릴 때만 호출되므로 부담 적음)
            Desktop, _, _ = _lazy_pywinauto()
            dlg = Desktop(backend="win32").window(handle=fg)

            try:
                if str(getattr(dlg.element_info, "class_name", "") or "") != "#32770":
                    return False
            except Exception:
                return False

            try:
                blob = " ".join([t for t in (dlg.texts() or []) if t]).strip()
            except Exception:
                blob = ""

            return ("클립보드 이미지 전송" in blob)

        except Exception:
            return False

    def _is_modal_dialog_same_pid(self, fg_hwnd: int) -> bool:
        """
        ✅ same pid + #32770 이면 '카카오톡 모달'로 간주.
        - '클립보드 이미지 전송' 뿐 아니라, 전송 관련/확인창/차단 팝업 등도 동일 class로 뜸
        - title이 비어있는 케이스가 많아서 class/pid 기반으로 우선 통과 처리
        """
        try:
            fg = int(fg_hwnd or 0)
            if fg <= 0:
                return False

            if int(w32.get_pid(fg) or 0) != int(w32.get_pid(self._hwnd) or 0):
                return False

            cls = str(w32.get_class_name(fg) or "")
            return cls == "#32770"
        except Exception:
            return False

    # ----------------------------
    # image helpers
    # ----------------------------
    def _png_to_dib_bytes(self, png_bytes: bytes) -> bytes:
        key = hashlib.sha1(png_bytes).hexdigest()
        cached = self._dib_cache.get(key)
        if cached:
            return cached

        with Image.open(BytesIO(png_bytes)) as img:
            img = img.convert("RGB")
            output = BytesIO()
            img.save(output, format="BMP")
            bmp = output.getvalue()

        dib = bmp[14:]
        self._dib_cache[key] = dib
        return dib

    def _top_level_hwnd(self, hwnd: int) -> int:
        """
        ✅ foreground가 child로 튀는 케이스 대응:
        - GetAncestor(GA_ROOT=2)로 top-level hwnd를 얻는다.
        """
        try:
            h = int(hwnd or 0)
            if h <= 0:
                return 0
            GA_ROOT = 2
            root = int(w32.user32.GetAncestor(h, GA_ROOT) or 0)
            return root if root > 0 else h
        except Exception:
            return int(hwnd or 0)

    def _fg_top_level(self) -> int:
        """현재 foreground hwnd를 top-level 기준으로 정규화해서 반환"""
        try:
            fg = int(w32.get_foreground_hwnd() or 0)
            return int(self._top_level_hwnd(fg) or 0)
        except Exception:
            return 0


    # ----------------------------
    # trace utils
    # ----------------------------
    @contextmanager
    def _trace_span(self, label: str, **kv: Any):
        t0 = time.perf_counter()
        self._trace(f"{label}:begin", **kv)
        try:
            yield
            ok = True
        except Exception as e:
            ok = False
            self._trace(f"{label}:exc", err=str(e))
            raise
        finally:
            ms = int((time.perf_counter() - t0) * 1000)
            self._trace(f"{label}:end", ok=ok, ms=ms)

    def _trace_fg(self, label: str):
        try:
            fg = w32.get_foreground_hwnd()
            title = w32.get_window_text(int(fg))
            self._trace(label, fg_hwnd=int(fg), fg_title=title)
        except Exception:
            pass

    def _dump_mismatch_debug(self, *, stage: str, fg_hwnd: int) -> None:
        """
        mismatch 발생 시 원인 확정용 덤프.
        - foreground hwnd/title/class/pid/rect
        - main/chat hwnd 정보
        - 가능하면(#32770) pywinauto texts 일부도 수집
        """
        try:
            fg = int(fg_hwnd or 0)
            main = int(self._hwnd or 0)
            chat = int(self._chat_hwnd or 0)

            fg_title = ""
            fg_class = ""
            fg_pid = 0
            fg_rect = (0, 0, 0, 0)

            try:
                fg_title = str(w32.get_window_text(fg) or "")
            except Exception:
                pass
            try:
                fg_class = str(w32.get_class_name(fg) or "")
            except Exception:
                pass
            try:
                fg_pid = int(w32.get_pid(fg) or 0)
            except Exception:
                pass
            try:
                fg_rect = tuple(w32.get_window_rect(fg))
            except Exception:
                pass

            main_pid = 0
            try:
                main_pid = int(w32.get_pid(main) or 0)
            except Exception:
                pass

            payload = {
                "stage": stage,
                "recipient": (self._active_recipient or ""),
                "fg_hwnd": fg,
                "fg_title": fg_title,
                "fg_class": fg_class,
                "fg_pid": fg_pid,
                "main_hwnd": main,
                "main_pid": main_pid,
                "chat_hwnd": chat,
                "mode": (self._mode or ""),
                "chat_in_main": bool(getattr(self, "_chat_in_main", False)),
                "fg_rect": fg_rect,
            }

            # #32770 모달이면 texts까지 시도(가벼운 1회)
            if fg and fg_class == "#32770":
                try:
                    Desktop, _, _ = _lazy_pywinauto()
                    dlg = Desktop(backend="win32").window(handle=fg)
                    txts = []
                    try:
                        txts = [t for t in (dlg.texts() or []) if t]
                    except Exception:
                        txts = []
                    # 너무 길면 앞부분만
                    payload["dlg_texts"] = txts[:20]
                except Exception:
                    pass

            self._trace("IMG:mismatch_dump", **payload)

        except Exception:
            # 덤프 실패는 로직에 영향 주지 않음
            pass

    def _invalidate_chat_input_cache(self, hwnd: int) -> None:
        """특정 hwnd의 입력창 컨트롤 캐시 무효화"""
        try:
            h = int(hwnd or 0)
        except Exception:
            return
        if h <= 0:
            return
        try:
            self._chat_input_ctrl_cache.pop(h, None)
            self._chat_input_ctrl_cache_ts.pop(h, None)
        except Exception:
            pass

    def _get_cached_chat_input_ctrl(self, hwnd: int) -> Optional[Any]:
        """캐시된 입력창 컨트롤을 반환(유효성 확인 포함)"""
        h = int(hwnd or 0)
        if h <= 0:
            return None

        ctrl = self._chat_input_ctrl_cache.get(h)
        if ctrl is None:
            return None

        # 캐시 TTL (너무 오래된 컨트롤은 다시 찾도록)
        try:
            ts = float(self._chat_input_ctrl_cache_ts.get(h, 0.0))
        except Exception:
            ts = 0.0

        # ✅ TTL 15분 (필요하면 조정)
        if ts and (time.time() - ts) > 900:
            self._invalidate_chat_input_cache(h)
            return None

        # 컨트롤이 살아있는지 최소 확인
        try:
            _ = ctrl.element_info  # pywinauto wrapper 여부 체크
        except Exception:
            self._invalidate_chat_input_cache(h)
            return None

        return ctrl
    def _find_and_cache_chat_input_ctrl(self, hwnd: int) -> Optional[Any]:
        """hwnd에서 입력창 후보 컨트롤을 찾아 캐시에 저장 후 반환"""
        h = int(hwnd or 0)
        if h <= 0 or not w32.is_window(h):
            return None

        try:
            Desktop, _, _ = _lazy_pywinauto()
            win = Desktop(backend="win32").window(handle=h)

            candidates: list[Any] = []
            for cls in ("RICHEDIT50W", "RichEdit20W", "RichEdit", "Edit"):
                try:
                    candidates.extend(win.descendants(class_name=cls))
                except Exception:
                    pass

            def _bottom_y(ctrl) -> int:
                try:
                    r = ctrl.rectangle()
                    return int(r.bottom)
                except Exception:
                    return -1

            if not candidates:
                return None

            # 일반적으로 입력창이 맨 아래에 있음
            ctrl = sorted(candidates, key=_bottom_y, reverse=True)[0]

            # 캐시 저장
            try:
                self._chat_input_ctrl_cache[h] = ctrl
                self._chat_input_ctrl_cache_ts[h] = time.time()
            except Exception:
                pass

            return ctrl

        except Exception:
            return None

    def _is_main_search_no_result(self) -> bool:
        """
        메인 검색 결과가 '없음' 상태인지 감지.
        - 카카오톡 검색 리스트에 '검색 결과가 없습니다' 문구가 뜨는 케이스를 대상으로 함.
        - win32 backend 기준: window_text/texts() 기반의 보수적 감지.
        """
        try:
            Desktop, _, _ = _lazy_pywinauto()
            win = Desktop(backend="win32").window(handle=int(self._hwnd))

            texts = []
            try:
                texts = win.texts()
            except Exception:
                texts = []

            blob = " ".join([t for t in (texts or []) if t]).strip()
            if not blob:
                try:
                    blob = str(win.window_text() or "").strip()
                except Exception:
                    blob = ""

            keys = (
                "검색 결과가 없습니다",
                "검색결과가 없습니다",
                "검색 결과 없음",
                "검색 결과를 찾을 수 없습니다",
                "검색 결과가 없어요",
                "결과가 없습니다",
            )
            return any(k in blob for k in keys)

        except Exception:
            return False

__all__ = [
    "KakaoSenderDriver",
    "KakaoPcDriver",
    "KakaoTarget",
    "StopNow",
    "SpeedProfile",
    "TransferAbortedByClose",
    "CloseForcedByConfirm",
]