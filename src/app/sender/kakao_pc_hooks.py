# ✅ FILE: src/app/sender/kakao_pc_hooks.py
from __future__ import annotations

import time
from typing import Any, Callable, Mapping, Optional, Dict
from app.sender.kakao_dialog_send import send_clipboard_image_dialog_force
from dataclasses import dataclass






class ChatNotFound(RuntimeError):
    pass


@dataclass
class _Timings:
    # search
    search_open_delay: float = 0.01
    paste_name_delay: float = 0.01

    # ✅ clear search timings (driver에서 내려주는 값 반영)
    select_home_delay: float = 0.004
    select_end_delay: float = 0.004
    delete_delay: float = 0.006
    extra_delete_delay: float = 0.004

    # open wait (poll)
    open_wait1: float = 0.10
    open_wait2: float = 0.12

    # after-enter settle
    enter1_post_key_sleep: float = 0.003
    enter2_post_key_sleep: float = 0.003

def _get_t(timings: Dict[str, Any] | None) -> _Timings:
    d = dict(timings or {})
    t = _Timings()
    for k in t.__dict__.keys():
        if k in d:
            try:
                setattr(t, k, float(d[k]))
            except Exception:
                pass
    return t


def open_chat_by_name_hook(
    *,
    name: str,
    ensure_foreground_main: Callable[[], None],
    send_keys_main: Callable[[str], None],
    set_clipboard_text: Callable[[str], None],
    snapshot_visible_hwnds: Callable[[], set[int]],
    find_new_chat_hwnd: Callable[[str, set[int]], int],
    set_chat_hwnd: Callable[[int], None],  # hwnd==0 => open-in-main
    ensure_foreground_chat: Callable[[], None],
    send_keys_chat: Callable[[str], None],
    focus_chat_input_best_effort: Callable[[], bool],
    chat_find_retries: int,
    log: Callable[[str], None],
    get_search_ready: Callable[[], bool],
    set_search_ready: Callable[[bool], None],
    backspace_extra: int,
    poll_sleep: float,
    timings: Dict[str, Any] | None = None,
    get_foreground_hwnd=None,
    get_window_text=None,
    prefer_open_in_main: bool = True,
    debug: bool = False,
) -> None:
    name = (name or "").strip()
    if not name:
        raise ChatNotFound("empty name")

    t = _get_t(timings)

    def _sleep(sec: float) -> None:
        time.sleep(max(0.0, float(sec)))

    def _is_kakao_like_title(title: str) -> bool:
        tt = (title or "").lower()
        return ("카카오톡" in tt) or ("kakaotalk" in tt)

    def _fg_title() -> str:
        if get_foreground_hwnd is None or get_window_text is None:
            return ""
        try:
            fg = int(get_foreground_hwnd() or 0)
            if fg <= 0:
                return ""
            return str(get_window_text(fg) or "")
        except Exception:
            return ""

    def _fast_fg_match() -> int:
        if get_foreground_hwnd is None or get_window_text is None:
            return 0
        try:
            fg = int(get_foreground_hwnd() or 0)
            if fg <= 0:
                return 0
            title = str(get_window_text(fg) or "")
            if name and (name in title):
                return fg
        except Exception:
            return 0
        return 0

    def _poll_new_window(before: set[int], wait_sec: float) -> int:
        t_poll0 = time.perf_counter()
        loops = 0
        end = time.time() + max(0.0, float(wait_sec))
        while time.time() < end:
            loops += 1
            try:
                h = int(find_new_chat_hwnd(name, before) or 0)
            except Exception:
                h = 0
            if h > 0:
                _dbg(
                    log, debug,
                    f"[DBG] OPEN_CHAT:poll hit hwnd={h} loops={loops} poll_ms={int((time.perf_counter()-t_poll0)*1000)}"
                )
                return h
            _sleep(poll_sleep)

        _dbg(
            log, debug,
            f"[DBG] OPEN_CHAT:poll miss loops={loops} poll_ms={int((time.perf_counter()-t_poll0)*1000)} wait_sec={wait_sec}"
        )
        return 0

    # ---- step timer
    t0 = time.perf_counter()
    tp = t0

    def step(label: str) -> None:
        nonlocal tp
        now = time.perf_counter()
        _dbg(log, debug, f"[DBG] OPEN_CHAT:{label} step_ms={int((now-tp)*1000)} total_ms={int((now-t0)*1000)}")
        tp = now

    _dbg(log, debug, f"[DBG] OPEN_CHAT:begin name={name!r}")

    # 1) 메인 포그라운드
    # ✅ search_ready=True + 이미 카카오 포그라운드면 ensure_foreground_main() 스킵
    if get_search_ready() and (get_foreground_hwnd is not None) and (get_window_text is not None):
        try:
            fg = int(get_foreground_hwnd() or 0)
            ft = str(get_window_text(fg) or "")
            if ft and _is_kakao_like_title(ft):
                step("ensure_foreground_main(skip_fg_ok)")
            else:
                ensure_foreground_main()
                step("ensure_foreground_main")
        except Exception:
            ensure_foreground_main()
            step("ensure_foreground_main")
    else:
        ensure_foreground_main()
        step("ensure_foreground_main")

    # 2) 검색창 오픈(필요 시)
    if not get_search_ready():
        ensure_foreground_main()
        _sleep(0.01)

        send_keys_main("^f")
        step("ctrl_f")
        _sleep(t.search_open_delay)
        step("after_search_open_delay_2")

        ft = _fg_title()
        if ft and _is_kakao_like_title(ft):
            set_search_ready(True)
            step("set_search_ready_true")
        else:
            set_search_ready(False)
            step("set_search_ready_false")

    # 3) 검색어 지우기 (Ctrl+A 금지: HOME + SHIFT+END + DEL)
    # ✅ search_ready=True면: 바로 clear 시퀀스만 날리고 슬립 제거
    try:
        if not get_search_ready():
            ensure_foreground_main()
            # 필요 시에만 최소 안정화
            time.sleep(0.001)

        send_keys_main("^{HOME}^+{END}{DEL}")

        # ✅ 여기 뜸의 주범. 기본은 0으로.
        # (특정 PC에서 입력 누락되면 0.001~0.002만 주면 됨)
        # time.sleep(0.001)

    except Exception:
        try:
            send_keys_main("^{HOME}^+{END}{DEL}")
        except Exception:
            pass

    # 4) 이름 붙여넣기
    set_clipboard_text(name)
    # _sleep(0.003)
    send_keys_main("^v")
    _sleep(t.paste_name_delay)
    step("paste_name")

    # ✅ 핵심 변경: ENTER 전에 스냅샷을 떠야 "진짜 새 개인창"을 잡아냄
    before = snapshot_visible_hwnds()
    step("snapshot_before_enter")

    # 5) ENTER 1차
    send_keys_main("{ENTER}")
    _sleep(t.enter1_post_key_sleep)
    step("enter1_sent")

    # fast-path: foreground title match
    fg_hwnd = _fast_fg_match()
    if fg_hwnd > 0:
        set_chat_hwnd(fg_hwnd)
        step("set_chat_hwnd_fg_1")
        ensure_foreground_chat()
        step("ensure_foreground_chat_fg_1")
        focus_chat_input_best_effort()
        step("focus_chat_input_fg_1")
        _dbg(log, debug, f"[DBG] OPEN_CHAT:end ok=True(fg_fast) total_ms={int((time.perf_counter()-t0)*1000)}")
        return

    # fallback: 새 창 감지
    new_hwnd = _poll_new_window(before, t.open_wait1)
    if new_hwnd > 0:
        set_chat_hwnd(new_hwnd)
        step("set_chat_hwnd_new_1")
        ensure_foreground_chat()
        step("ensure_foreground_chat_1")
        focus_chat_input_best_effort()
        step("focus_chat_input_1")
        _dbg(log, debug, f"[DBG] OPEN_CHAT:end ok=True(new_win) total_ms={int((time.perf_counter()-t0)*1000)}")
        return

    # 6) ENTER 2차
    send_keys_main("{ENTER}")
    _sleep(t.enter2_post_key_sleep)
    step("enter2_sent")

    fg_hwnd = _fast_fg_match()
    if fg_hwnd > 0:
        set_chat_hwnd(fg_hwnd)
        step("set_chat_hwnd_fg_2")
        ensure_foreground_chat()
        step("ensure_foreground_chat_fg_2")
        focus_chat_input_best_effort()
        step("focus_chat_input_fg_2")
        _dbg(log, debug, f"[DBG] OPEN_CHAT:end ok=True(fg_fast2) total_ms={int((time.perf_counter()-t0)*1000)}")
        return

    new_hwnd = _poll_new_window(before, t.open_wait2)
    if new_hwnd > 0:
        set_chat_hwnd(new_hwnd)
        step("set_chat_hwnd_new_2")
        ensure_foreground_chat()
        step("ensure_foreground_chat_2")
        focus_chat_input_best_effort()
        step("focus_chat_input_2")
        _dbg(log, debug, f"[DBG] OPEN_CHAT:end ok=True(new_win2) total_ms={int((time.perf_counter()-t0)*1000)}")
        return

    # 새창이 안 뜨면 open-in-main
    if prefer_open_in_main:
        set_chat_hwnd(0)
        step("set_chat_hwnd_open_in_main")
        ensure_foreground_chat()
        step("ensure_foreground_chat_main")
        focus_chat_input_best_effort()
        step("focus_chat_input_main")
        _dbg(log, debug, f"[DBG] OPEN_CHAT:end ok=True(open_in_main) total_ms={int((time.perf_counter()-t0)*1000)}")
        return

    _dbg(log, debug, f"[DBG] OPEN_CHAT:end ok=False total_ms={int((time.perf_counter()-t0)*1000)}")
    raise ChatNotFound(f"'{name}' not opened")

def send_image_dialog_hook(
    *,
    timeout_sec: float,
    key_delay: float,
    debug: bool,
    log: Callable[[str], None],
    timings: Optional[Mapping[str, float]] = None,
    prefer_hwnd: int = 0,  # ✅ 추가
) -> bool:
    tm = dict(timings or {})
    log(
        f"[IMG-DLG] hook start timeout={timeout_sec:.2f}s "
        f"try_interval={float(tm.get('try_interval', 0.12)):.3f} "
        f"loop_sleep={float(tm.get('loop_sleep', 0.02)):.3f} "
        f"post_click_sleep={float(tm.get('post_click_sleep', 0.03)):.3f} "
        f"enter_gap_sec={float(tm.get('enter_gap_sec', 0.04)):.3f} "
        f"prefer_hwnd={int(prefer_hwnd or 0)}"
    )

    ok = send_clipboard_image_dialog_force(
        timeout_sec=float(timeout_sec),
        key_delay=float(key_delay),
        debug=bool(debug),
        enter_times=2,
        enter_gap_sec=float(tm.get("enter_gap_sec", 0.04)),
        try_interval=float(tm.get("try_interval", 0.12)),
        loop_sleep=float(tm.get("loop_sleep", 0.02)),
        post_click_sleep=float(tm.get("post_click_sleep", 0.03)),
        prefer_hwnd=int(prefer_hwnd or 0),  # ✅ 핵심
    )

    log(f"[IMG-DLG] hook result={ok}")
    return bool(ok)


def _dbg(log: Callable[[str], None], debug: bool, msg: str) -> None:
    if not debug:
        return
    try:
        log(msg)
    except Exception:
        pass


def _now_ms() -> int:
    return int(time.perf_counter() * 1000)