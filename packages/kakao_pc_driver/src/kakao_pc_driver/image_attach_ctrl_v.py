from __future__ import annotations

import time
from typing import Callable, Optional, Any


def _top_level_hwnd(user32: Any, hwnd: int) -> int:
    """
    foreground가 child로 튀는 케이스 대응:
    - GetAncestor(GA_ROOT=2)로 top-level hwnd를 얻는다.
    """
    try:
        h = int(hwnd or 0)
        if h <= 0:
            return 0
        GA_ROOT = 2
        root = int(user32.GetAncestor(h, GA_ROOT) or 0)
        return root if root > 0 else h
    except Exception:
        return int(hwnd or 0)


def _is_modal_dialog_same_pid_top(
    *,
    user32: Any,
    fg_hwnd: int,
    get_pid: Callable[[int], int],
    get_class_name: Callable[[int], str],
    kakao_main_hwnd: int,
) -> bool:
    try:
        fg = _top_level_hwnd(user32, int(fg_hwnd or 0))
        if fg <= 0:
            return False
        if int(get_pid(fg) or 0) != int(get_pid(int(kakao_main_hwnd) or 0) or 0):
            return False

        cls = str(get_class_name(fg) or "")
        if cls == "#32770":
            return True

        # ✅ 카카오톡 이미지 전송 UI가 EVA_* top-level로 뜨는 케이스 허용
        if cls.startswith("EVA_") or cls == "EVA_Window_Dblclk":
            return True

        return False
    except Exception:
        return False

def _is_clipboard_image_dialog_foreground_top(
    *,
    user32: Any,
    fg_hwnd: int,
    get_pid: Callable[[int], int],
    kakao_main_hwnd: int,
    lazy_pywinauto: Callable[[], Any],
) -> bool:
    """
    '클립보드 이미지 전송' 모달인지 판별(정밀):
    - fg가 child여도 top-level(#32770)로 올려서 texts() 확인
    """
    try:
        fg = _top_level_hwnd(user32, int(fg_hwnd or 0))
        if fg <= 0:
            return False
        if int(get_pid(fg) or 0) != int(get_pid(int(kakao_main_hwnd) or 0) or 0):
            return False

        Desktop, _, _ = lazy_pywinauto()
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


def attach_image_via_ctrl_v(
    *,
    dib_bytes: bytes,
    active_recipient: str,
    kakao_main_hwnd: int,
    chat_hwnd: int,
    # win32 / env
    user32: Any,
    get_foreground_hwnd: Callable[[], int],
    get_window_text: Callable[[int], str],
    get_class_name: Callable[[int], str],
    get_pid: Callable[[int], int],
    set_clipboard_dib: Callable[[bytes], None],
    lazy_pywinauto: Callable[[], Any],
    # actions
    ensure_foreground_chat: Callable[[], None],
    focus_chat_input_best_effort: Callable[[], bool],
    send_keys_chat: Callable[[str], None],
    sleep: Callable[[float], None],
    sleep_abs: Callable[[float], None],
    # dialog
    send_image_dialog_hook: Callable[..., bool],
    image_dialog_timeout_sec: float,
    key_delay: float,
    debug: bool,
    log: Callable[[str], None],
    timings: dict,
    prefer_hwnd: int,
    # post
    restore_chat_focus_after_image_dialog: Callable[[], None],
    # trace (optional)
    trace: Optional[Callable[..., None]] = None,
    dump_mismatch_debug: Optional[Callable[..., None]] = None,
    image_paste_settle_sec: float = 0.0,
) -> bool:
    """
    ✅ Ctrl+V 이미지 붙여넣기 + (top-level 기준) mismatch 가드 + 모달 엔터 전송
    - '권혁진' 케이스처럼 fg가 child로 튀는 경우: top-level로 올려서 정상 판정
    """
    def _t(label: str, **kv):
        if trace:
            try:
                trace(label, **kv)
            except Exception:
                pass

    # 1) 채팅 전면/포커스
    try:
        ensure_foreground_chat()
    except Exception:
        pass
    try:
        focus_chat_input_best_effort()
    except Exception:
        pass
    sleep_abs(0.01)

    # 2) 클립보드 set (DIB)
    try:
        set_clipboard_dib(dib_bytes)
    except Exception as e:
        log(f"[IMG-CV] set_clipboard_dib failed: {e}")
        return False

    sleep_abs(0.01)

    # 3) ^V 직전 가드 (top-level 기준)
    try:
        fg0 = int(get_foreground_hwnd() or 0)
        top0 = _top_level_hwnd(user32, fg0)
        ft0 = str(get_window_text(top0) or "")
        _t("IMG-CV:guard_before_v", fg_hwnd=fg0, top_hwnd=top0, top_title=ft0)

        # 모달이면 통과
        if _is_modal_dialog_same_pid_top(
            user32=user32,
            fg_hwnd=fg0,
            get_pid=get_pid,
            get_class_name=get_class_name,
            kakao_main_hwnd=int(kakao_main_hwnd),
        ):
            _t("IMG-CV:before_v_is_modal", top_hwnd=top0)
        elif active_recipient and (active_recipient not in ft0):
            _t("IMG-CV:recipient_mismatch_before_v", recipient=active_recipient, top_title=ft0, top_hwnd=top0)

            # 1회 복구 시도 후 실패 반환 (상위 retry 유도)
            try:
                ensure_foreground_chat()
                focus_chat_input_best_effort()
                sleep_abs(0.01)
            except Exception:
                pass
            return False
    except Exception:
        pass

    # 4) Ctrl+V
    _t("IMG-CV:before_ctrl_v")
    try:
        send_keys_chat("^v")
    except Exception as e:
        log(f"[IMG-CV] ctrl+v failed: {e}")
        return False
    _t("IMG-CV:after_ctrl_v")

    # 5) ^V 직후 가드 (top-level 기준)
    try:
        fg1 = int(get_foreground_hwnd() or 0)
        top1 = _top_level_hwnd(user32, fg1)
        ft1 = str(get_window_text(top1) or "")
        cls1 = str(get_class_name(top1) or "")
        _t("IMG-CV:guard_after_v", fg_hwnd=fg1, top_hwnd=top1, top_title=ft1, top_class=cls1)

        # (우선) same pid + #32770 모달이면 정상 플로우
        if _is_modal_dialog_same_pid_top(
            user32=user32,
            fg_hwnd=fg1,
            get_pid=get_pid,
            get_class_name=get_class_name,
            kakao_main_hwnd=int(kakao_main_hwnd),
        ):
            _t("IMG-CV:after_v_is_modal", top_hwnd=top1)
        # (정밀) 클립보드 이미지 전송 모달이면 정상
        elif _is_clipboard_image_dialog_foreground_top(
            user32=user32,
            fg_hwnd=fg1,
            get_pid=get_pid,
            kakao_main_hwnd=int(kakao_main_hwnd),
            lazy_pywinauto=lazy_pywinauto,
        ):
            _t("IMG-CV:after_v_is_clipboard_dialog", top_hwnd=top1)
        else:
            # ✅ top-level title 기준으로 수신자 mismatch 판정
            if active_recipient and (active_recipient not in ft1):
                if dump_mismatch_debug:
                    try:
                        dump_mismatch_debug(stage="after_ctrl_v_top", fg_hwnd=fg1)
                    except Exception:
                        pass

                _t(
                    "IMG-CV:recipient_mismatch_after_v",
                    recipient=active_recipient,
                    top_title=ft1,
                    top_hwnd=top1,
                    top_class=cls1,
                )

                try:
                    ensure_foreground_chat()
                    focus_chat_input_best_effort()
                    sleep_abs(0.01)
                except Exception:
                    pass
                return False
    except Exception:
        pass

    # 6) paste settle
    if float(image_paste_settle_sec or 0.0) > 0:
        _t("IMG-CV:paste_settle_sleep", sec=float(image_paste_settle_sec))
        sleep_abs(float(image_paste_settle_sec))

    # 7) 전송 모달 처리(+엔터)
    ok = False
    try:
        ok = bool(
            send_image_dialog_hook(
                timeout_sec=float(image_dialog_timeout_sec),
                key_delay=float(key_delay),
                debug=bool(debug),
                log=log,
                timings=dict(timings or {}),
                prefer_hwnd=int(prefer_hwnd or 0),
            )
        )
    except Exception as e:
        log(f"[IMG-CV] dialog hook exception: {e}")
        ok = False

    _t("IMG-CV:dialog_done", ok=ok)

    if not ok:
        return False

    # 8) 모달 성공 직후 포커스 복구
    try:
        restore_chat_focus_after_image_dialog()
    except Exception:
        pass

    return True


