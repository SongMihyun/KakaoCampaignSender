# -*- coding: utf-8 -*-
"""
KakaoTalk PC - Window handle discovery + Foreground/Top focus utility

핵심 기능
1) 창 핸들 찾기
   - 채팅방명(창 제목) 기반: room_title_regex
   - 클래스명 기반: class_name_allowlist / class_name_regex
   - 프로세스 기반: KakaoTalk.exe 로 확정 (psutil 권장)

2) 최상단 + 포커싱
   - SW_RESTORE (최소화 복원)
   - TopMost 토글 (전면 끌어올림)
   - SetForegroundWindow
   - ALT key 트릭 (포커스 제한 우회)
   - AttachThreadInput (입력 스레드 연결 우회)
"""

from __future__ import annotations

import re
import time
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple, Callable

import win32gui
import win32con
import win32api
import win32process

try:
    import psutil  # 권장
except Exception:
    psutil = None


# ----------------------------
# Config
# ----------------------------

DEFAULT_EXE_NAMES = {"KakaoTalk.exe"}  # 기본 프로세스 확정 기준(대소문자 주의 X)
DEFAULT_TITLE_KEYWORDS = ["카카오톡", "KakaoTalk"]

# 카카오톡은 업데이트/환경에 따라 창 클래스명이 달라질 수 있습니다.
# 아래 리스트는 "힌트"로만 사용하고, 최종은 room/title + exe 로 확정하는 방식이 안정적입니다.
DEFAULT_CLASS_ALLOWLIST = {
    # 자주 보이는 케이스(환경별 상이)
    "EVA_Window_Dblclk",
    "Qt5QWindowIcon",
    "Qt5152QWindowIcon",
    "Qt6QWindowIcon",
    "Chrome_WidgetWin_1",  # 일부 런처/임베드 환경에서 나타날 수 있음
}


# ----------------------------
# Data model
# ----------------------------

@dataclass
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    pid: int
    exe: Optional[str] = None


# ----------------------------
# Window enumeration
# ----------------------------

def _get_exe_name_by_pid(pid: int) -> Optional[str]:
    """
    pid -> exe basename
    psutil이 있으면 매우 안정적.
    없으면 None 반환 (프로세스 확정 필터를 약화시키고 title/class로 판단하도록)
    """
    if psutil is None:
        return None
    try:
        p = psutil.Process(pid)
        return p.name()  # e.g., "KakaoTalk.exe"
    except Exception:
        return None


def list_top_level_windows(include_invisible: bool = False) -> List[WindowInfo]:
    """
    최상위(Top-level) 윈도우를 열거.
    """
    result: List[WindowInfo] = []

    def enum_cb(hwnd, _):
        try:
            if not include_invisible and not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd) or ""
            class_name = win32gui.GetClassName(hwnd) or ""
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            exe = _get_exe_name_by_pid(pid)
            result.append(WindowInfo(hwnd=hwnd, title=title, class_name=class_name, pid=pid, exe=exe))
        except Exception:
            # enum 중 예외 발생해도 전체가 깨지지 않도록 무시
            return

    win32gui.EnumWindows(enum_cb, None)
    return result


# ----------------------------
# Find KakaoTalk windows
# ----------------------------

def _normalize_exe(exe: Optional[str]) -> Optional[str]:
    return exe.lower() if exe else None


def filter_windows(
    windows: List[WindowInfo],
    exe_names: Optional[set[str]] = None,
    title_keywords: Optional[List[str]] = None,
    room_title_regex: Optional[str] = None,
    class_name_allowlist: Optional[set[str]] = None,
    class_name_regex: Optional[str] = None,
) -> List[WindowInfo]:
    """
    다양한 기준을 조합해서 후보를 추립니다.

    우선순위(추천):
    1) exe_names로 KakaoTalk.exe 확정 (psutil 설치 시 강력)
    2) room_title_regex(채팅방명)로 채팅창 확정
    3) title_keywords로 메인/일반 창 후보
    4) class_name allow/regex는 보조 신호(환경별 편차 큼)
    """
    exe_names_norm = {x.lower() for x in exe_names} if exe_names else None
    class_allow_norm = {x for x in class_name_allowlist} if class_name_allowlist else None

    room_re = re.compile(room_title_regex, re.IGNORECASE) if room_title_regex else None
    class_re = re.compile(class_name_regex) if class_name_regex else None

    out: List[WindowInfo] = []
    for w in windows:
        # exe 필터
        if exe_names_norm is not None:
            ex = _normalize_exe(w.exe)
            if ex is None or ex not in exe_names_norm:
                continue

        # 채팅방 title regex
        if room_re is not None:
            if not room_re.search(w.title):
                continue

        # 타이틀 키워드(보조)
        if title_keywords:
            if not any(k.lower() in (w.title or "").lower() for k in title_keywords):
                # room_title_regex가 이미 걸러줬다면 여기서 걸러지면 안 될 수도 있어,
                # room_title_regex가 존재하면 title_keywords는 강제하지 않는 게 운영상 더 안정적입니다.
                # 따라서 room_title_regex가 없을 때만 title_keywords를 강제 적용.
                if room_re is None:
                    continue

        # 클래스명 allowlist/regex (보조)
        if class_allow_norm is not None and len(class_allow_norm) > 0:
            if w.class_name not in class_allow_norm:
                # class_name_regex가 있으면 allowlist 미통과라도 regex로 허용
                if class_re is None or not class_re.search(w.class_name):
                    # class 기준을 강제하고 싶지 않으면 이 블록을 주석 처리하세요.
                    pass

        if class_re is not None:
            if not class_re.search(w.class_name):
                # regex는 강제하고 싶지 않으면 주석 처리 가능
                pass

        out.append(w)

    return out


def find_kakaotalk_window(
    room_name: Optional[str] = None,
    prefer_chatroom: bool = True,
    exe_names: set[str] = DEFAULT_EXE_NAMES,
) -> WindowInfo:
    """
    - room_name이 있으면: '채팅방명 기반'으로 가장 강하게 특정
    - 없으면: 카카오톡 메인창 후보를 찾음

    prefer_chatroom=True: room_name 있으면 채팅창을 우선
    """
    windows = list_top_level_windows(include_invisible=False)

    if room_name:
        # 채팅방명은 창 제목에 그대로 들어가는 경우가 많아서 정규식으로 찾습니다.
        # 예: "플레이홀릭" 또는 "플레이홀릭 (123)" 같은 케이스 대응
        room_regex = re.escape(room_name)
        candidates = filter_windows(
            windows,
            exe_names=exe_names,
            room_title_regex=room_regex,
            # title_keywords는 room 검색 시 강제하지 않는 게 안전
            title_keywords=None,
            class_name_allowlist=None,
            class_name_regex=None,
        )
        # 후보가 여러 개면 "가장 최근에 활성화/앞에 보이는 창" 기준 정교화가 필요하지만,
        # 실무에서는 대개 1개로 떨어집니다.
        if candidates:
            # prefer_chatroom이면 바로 반환
            if prefer_chatroom:
                return candidates[0]

    # 메인창/일반창 후보 찾기
    main_candidates = filter_windows(
        windows,
        exe_names=exe_names,
        title_keywords=DEFAULT_TITLE_KEYWORDS,
        class_name_allowlist=DEFAULT_CLASS_ALLOWLIST,
        class_name_regex=None,
    )
    if main_candidates:
        return main_candidates[0]

    # exe로 못 잡는 환경(=psutil 미설치 등) 대비: 타이틀만으로 fallback
    fallback = [w for w in windows if any(k.lower() in w.title.lower() for k in DEFAULT_TITLE_KEYWORDS)]
    if fallback:
        return fallback[0]

    raise RuntimeError("카카오톡 창을 찾지 못했습니다. (카카오톡 실행 여부/스토어 버전/권한/타이틀 조건 확인)")


# ----------------------------
# Focus / Foreground utilities
# ----------------------------

def _alt_key_trick():
    """포커스 제한 우회에 종종 도움이 되는 ALT 키 토글"""
    win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)  # ALT down
    time.sleep(0.03)
    win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)  # ALT up


def _topmost_toggle(hwnd: int):
    """TopMost를 잠깐 켰다가 끄는 토글(전면 끌어올림 강화)"""
    win32gui.SetWindowPos(
        hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
    )
    win32gui.SetWindowPos(
        hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
    )


def _attach_thread_input_foreground(hwnd: int) -> bool:
    """
    SetForegroundWindow가 막힐 때, 현재 포그라운드 스레드와 대상 스레드를 AttachThreadInput으로 연결 후 시도.
    성공하면 True.
    """
    try:
        fg_hwnd = win32gui.GetForegroundWindow()
        if not fg_hwnd:
            return False

        fg_tid, _ = win32process.GetWindowThreadProcessId(fg_hwnd)
        target_tid, _ = win32process.GetWindowThreadProcessId(hwnd)

        if fg_tid == 0 or target_tid == 0:
            return False

        win32api.AttachThreadInput(fg_tid, target_tid, True)
        try:
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
            win32gui.SetActiveWindow(hwnd)
        finally:
            win32api.AttachThreadInput(fg_tid, target_tid, False)

        return win32gui.GetForegroundWindow() == hwnd
    except Exception:
        return False


def focus_kakaotalk(hwnd: int, retries: int = 3, sleep_sec: float = 0.08) -> bool:
    """
    최상단 + 포커스 시도 플로우(성공률 위주)
    1) 복원
    2) TopMost 토글
    3) SetForegroundWindow
    4) ALT 트릭 + 재시도
    5) AttachThreadInput 방식 우회
    """
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError("유효하지 않은 hwnd 입니다.")

    # 최소화/숨김 복원
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    time.sleep(sleep_sec)

    for i in range(retries):
        try:
            _topmost_toggle(hwnd)
        except Exception:
            pass

        try:
            win32gui.BringWindowToTop(hwnd)
        except Exception:
            pass

        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass

        time.sleep(sleep_sec)

        if win32gui.GetForegroundWindow() == hwnd:
            return True

        # 포커스 제한 우회 트릭
        try:
            _alt_key_trick()
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass

        time.sleep(sleep_sec)

        if win32gui.GetForegroundWindow() == hwnd:
            return True

        # 마지막 우회(스레드 입력 연결)
        if _attach_thread_input_foreground(hwnd):
            return True

    return win32gui.GetForegroundWindow() == hwnd


# ----------------------------
# Diagnostics / CLI
# ----------------------------

def debug_print_candidates(exe_names: set[str] = DEFAULT_EXE_NAMES):
    """
    카카오톡 자동발송 디버깅에서 가장 유용:
    - 현재 시스템에서 '카카오톡 관련'으로 보이는 창들의
      title / class / pid / exe 를 출력
    """
    wins = list_top_level_windows(include_invisible=False)
    # exe 기준 필터(가능하면)
    if psutil is not None:
        wins = [w for w in wins if (w.exe or "").lower() in {x.lower() for x in exe_names}]
    # 그래도 없으면 타이틀로 fallback
    if not wins:
        wins = [w for w in list_top_level_windows(False) if any(k.lower() in w.title.lower() for k in DEFAULT_TITLE_KEYWORDS)]

    print("=== KakaoTalk window candidates ===")
    for w in wins:
        print(f"hwnd={w.hwnd} | title='{w.title}' | class='{w.class_name}' | pid={w.pid} | exe={w.exe}")
    print("===================================")


def main():
    """
    사용 예)
    - 후보 확인:
        python kakaotalk_window.py --list
    - 메인창 포커싱:
        python kakaotalk_window.py
    - 특정 채팅방 포커싱:
        python kakaotalk_window.py --room "플레이홀릭"
    """
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="카카오톡 후보 창 목록 출력")
    ap.add_argument("--room", type=str, default=None, help="채팅방명(창 제목 포함)으로 특정 창 포커싱")
    ap.add_argument("--retries", type=int, default=3, help="포커스 재시도 횟수")
    args = ap.parse_args()

    if args.list:
        debug_print_candidates()
        return

    w = find_kakaotalk_window(room_name=args.room)
    ok = focus_kakaotalk(w.hwnd, retries=args.retries)

    if ok:
        print(f"[OK] Focused: hwnd={w.hwnd}, title='{w.title}', class='{w.class_name}', pid={w.pid}, exe={w.exe}")
        sys.exit(0)
    else:
        print(f"[FAIL] Could not focus: hwnd={w.hwnd}, title='{w.title}'. "
              f"권한 불일치(관리자/일반), 전체화면 앱, 보안 데스크톱(UAC) 여부를 점검하세요.")
        sys.exit(2)


if __name__ == "__main__":
    main()
