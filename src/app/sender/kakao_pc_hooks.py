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


def _is_kakao_toast_quick_reply(
    *,
    hwnd: int,
    main_hwnd: int,
    get_pid,
    get_window_rect,
    lazy_pywinauto,
) -> bool:
    """
    카카오톡 알림(빠른답장) 토스트 창 판별.
    - 같은 pid + 작은 창 + texts에 '메시지 입력'/'전송' 포함이면 토스트로 간주
    """
    try:
        h = int(hwnd or 0)
        if h <= 0:
            return False

        if int(get_pid(h) or 0) != int(get_pid(int(main_hwnd)) or 0):
            return False

        l, t, r, b = get_window_rect(h)
        w = int(r - l)
        hgt = int(b - t)

        # 토스트는 보통 작다(환경 따라 조금 넉넉히)
        if w > 900 or hgt > 500:
            return False

        Desktop, _, _ = lazy_pywinauto()
        win = Desktop(backend="win32").window(handle=int(hwnd))

        try:
            txts = [x for x in (win.texts() or []) if x]
        except Exception:
            txts = []

        blob = " ".join(txts)
        # 스크린샷 기준 키워드
        if ("메시지 입력" in blob) and ("전송" in blob):
            return True

        return False
    except Exception:
        return False


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
    is_search_no_result: Callable[[], bool] | None = None,
    get_window_rect=None,
    lazy_pywinauto=None,
    main_hwnd: int = 0,
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

    def _is_shadow(title: str) -> bool:
        # ✅ ShadowWnd는 “채팅창”이 아님. 채택 금지
        return "KakaoTalkShadowWnd" in (title or "")

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
            if _is_shadow(title):
                return 0

            # ✅ 토스트(빠른답장) 창이면 채택 금지
            if (get_window_rect is not None) and (lazy_pywinauto is not None) and int(main_hwnd or 0) > 0:
                try:
                    if _is_kakao_toast_quick_reply(
                            hwnd=fg,
                            main_hwnd=int(main_hwnd),
                            get_pid=lambda h: 0,  # 여기선 hooks에 get_pid가 없으면 driver에서 넘겨주세요(아래 참고)
                            get_window_rect=get_window_rect,
                            lazy_pywinauto=lazy_pywinauto,
                    ):
                        return 0
                except Exception:
                    pass

            if name and (name in title):
                return fg
        except Exception:
            return 0
        return 0

    def _poll_new_window(before: set[int], wait_sec: float) -> int:
        """
        ✅ 새 창 감지 결과가 ShadowWnd면 무시하고 계속 폴링
        """
        t_poll0 = time.perf_counter()
        loops = 0
        end = time.time() + max(0.0, float(wait_sec))
        while time.time() < end:
            loops += 1
            try:
                h = int(find_new_chat_hwnd(name, before) or 0)
            except Exception:
                h = 0

            if h > 0 and get_window_text is not None:
                try:
                    ht = str(get_window_text(h) or "")
                    if _is_shadow(ht):
                        h = 0
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

    def _check_no_result(where: str) -> None:
        if not callable(is_search_no_result):
            return
        try:
            if is_search_no_result():
                _dbg(log, debug, f"[DBG] OPEN_CHAT:no_result where={where}")
                raise ChatNotFound(f"'{name}' search no result")
        except ChatNotFound:
            raise
        except Exception:
            return

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

    def _force_focus_search_edit() -> None:
        # 검색 입력칸 포커스가 자주 풀리므로 2~3회 강제
        for _ in range(3):
            try:
                ensure_foreground_main()
                _sleep(0.008)
                send_keys_main("^f")
                _sleep(max(0.01, t.search_open_delay))
                set_search_ready(True)
            except Exception:
                pass

    def _clear_search_text() -> None:
        ensure_foreground_main()
        _sleep(0.008)

        # 1) 1차: Ctrl+Home → Ctrl+Shift+End → Del
        try:
            _force_focus_search_edit()
            send_keys_main("^{HOME}")
            _sleep(t.select_home_delay)
            send_keys_main("^+{END}")
            _sleep(t.select_end_delay)
            send_keys_main("{DEL}")
            _sleep(t.delete_delay)
            # 잔여 문자 대비
            send_keys_main("{DEL}")
            _sleep(t.extra_delete_delay)
            return
        except Exception:
            pass

        # 2) 2차 폴백: Home → Shift+End → Del (컨트롤 조합이 안 먹는 컨트롤 대비)
        try:
            _force_focus_search_edit()
            send_keys_main("{HOME}")
            _sleep(t.select_home_delay)
            send_keys_main("+{END}")
            _sleep(t.select_end_delay)
            send_keys_main("{DEL}")
            _sleep(t.delete_delay)
            return
        except Exception:
            pass

        # 3) 최후 폴백: Backspace 연타 (포커스만 맞으면 거의 지워짐)
        try:
            _force_focus_search_edit()
            send_keys_main("{END}")
            _sleep(0.003)
            send_keys_main("{BACKSPACE}" * 40)
            _sleep(t.delete_delay)
        except Exception:
            pass

    # ✅ 여기 추가
    _clear_search_text()

    # 4) 이름 붙여넣기
    set_clipboard_text(name)
    _sleep(0.005)
    send_keys_main("^v")
    _sleep(t.paste_name_delay)
    step("paste_name")

    _check_no_result("after_paste_name_before_enter")

    # ✅ ENTER 전에 스냅샷
    before = snapshot_visible_hwnds()
    step("snapshot_before_enter")

    # 5) ENTER 1차
    send_keys_main("{ENTER}")
    _sleep(t.enter1_post_key_sleep)
    step("enter1_sent")

    _check_no_result("after_enter1")

    # fast-path: foreground title match (ShadowWnd는 _fast_fg_match에서 배제됨)
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

    # fallback: 새 창 감지 (ShadowWnd 배제)
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

    _check_no_result("after_enter2")

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

    _check_no_result("before_open_in_main")

    # open-in-main
    if prefer_open_in_main:
        # ✅ '검색 결과 없음'만 아니면 open-in-main 시도는 하되,
        # ✅ "채팅 입력창 포커스 성공"으로 검증되었을 때만 성공 처리한다.
        _check_no_result("before_open_in_main")

        set_chat_hwnd(0)

        # 검색창 닫고(ESC), 메인 채팅 컨텍스트로 전환 시도
        try:
            send_keys_main("{ESC}")
        except Exception:
            pass
        _sleep(0.01)

        step("set_chat_hwnd_open_in_main")

        # 메인 전면화 (driver의 ensure_foreground_chat은 open-in-main을 고려함)
        ensure_foreground_chat()
        step("ensure_foreground_chat_main")

        # ✅ 핵심: "진짜로 채팅이 열린 상태"인지 검증
        # - 친구탭/검색탭이면 입력창(RichEdit/Edit) 포커스가 실패하는 경우가 많음
        ok_focus = False
        try:
            ok_focus = bool(focus_chat_input_best_effort())
        except Exception:
            ok_focus = False

        step(f"focus_chat_input_main ok={ok_focus}")

        if ok_focus:
            _dbg(
                log, debug,
                f"[DBG] OPEN_CHAT:end ok=True(open_in_main_verified) total_ms={int((time.perf_counter() - t0) * 1000)}"
            )
            return

        # ✅ 검증 실패 => 없는 사람으로 처리하고 즉시 종료 (다음 사람으로 넘어가게)
        _dbg(
            log, debug,
            f"[DBG] OPEN_CHAT:open_in_main_verify_failed -> NOT_FOUND name={name!r}"
        )
        raise ChatNotFound(f"'{name}' not opened (open_in_main verify failed)")

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