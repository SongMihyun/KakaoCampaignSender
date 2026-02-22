# src/app/platform/win_file_picker_sta.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple
import ctypes
import threading
import queue

from ctypes import wintypes


# -----------------------------
# Public types
# -----------------------------
@dataclass(frozen=True)
class Filter:
    name: str
    pattern: str  # e.g. "*.xlsx" or "*.png;*.jpg;*.jpeg"


# -----------------------------
# Win32 / COM basics
# -----------------------------
ole32 = ctypes.WinDLL("ole32", use_last_error=True)

HRESULT = wintypes.LONG
ULONG = wintypes.ULONG
DWORD = wintypes.DWORD
LPWSTR = wintypes.LPWSTR
LPCWSTR = wintypes.LPCWSTR

S_OK = 0
S_FALSE = 1

COINIT_APARTMENTTHREADED = 0x2

# File dialog options (FOS_*)
FOS_OVERWRITEPROMPT = 0x00000002
FOS_FORCEFILESYSTEM = 0x00000040
FOS_ALLOWMULTISELECT = 0x00000200
FOS_PATHMUSTEXIST = 0x00000800
FOS_FILEMUSTEXIST = 0x00001000
FOS_NOCHANGEDIR = 0x00000008


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


def _guid(d1: int, d2: int, d3: int, d4: bytes) -> GUID:
    g = GUID()
    g.Data1 = d1
    g.Data2 = d2
    g.Data3 = d3
    for i in range(8):
        g.Data4[i] = d4[i]
    return g


# CLSID / IID
CLSID_FileOpenDialog = _guid(0xDC1C5A9C, 0xE88A, 0x4DDE, b"\xA5\xA1\x60\xF8\x2A\x20\xAE\xF7")
CLSID_FileSaveDialog = _guid(0xC0B4E2F3, 0xBA21, 0x4773, b"\x8D\xBA\x33\x5E\xC9\x46\xEB\x8B")

IID_IFileOpenDialog = _guid(0xD57C7288, 0xD4AD, 0x4768, b"\xBE\x02\x9D\x96\x95\x32\xD9\x60")
IID_IFileSaveDialog = _guid(0x84BCCD23, 0x5FDE, 0x4CDB, b"\xAE\xA4\xAF\x64\xB8\x3D\x78\xAB")

# SIGDN
SIGDN_FILESYSPATH = 0x80058000

# COMDLG_FILTERSPEC
class COMDLG_FILTERSPEC(ctypes.Structure):
    _fields_ = [("pszName", LPCWSTR), ("pszSpec", LPCWSTR)]


# -----------------------------
# Minimal COM interface wrappers via vtable
# -----------------------------
QueryInterfaceProto = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
AddRefProto = ctypes.WINFUNCTYPE(ULONG, ctypes.c_void_p)
ReleaseProto = ctypes.WINFUNCTYPE(ULONG, ctypes.c_void_p)

# IModalWindow::Show
ShowProto = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.HWND)

# IFileDialog subset
SetFileTypesProto = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(COMDLG_FILTERSPEC))
SetFileTypeIndexProto = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.UINT)
SetTitleProto = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, LPCWSTR)
GetOptionsProto = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(DWORD))
SetOptionsProto = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, DWORD)
GetResultProto = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))  # IShellItem**
SetDefaultExtensionProto = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, LPCWSTR)

# IFileOpenDialog extra
GetResultsProto = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))  # IShellItemArray**

# IShellItem
GetDisplayNameProto = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(LPWSTR))

# IShellItemArray
GetCountProto = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(DWORD))
GetItemAtProto = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, DWORD, ctypes.POINTER(ctypes.c_void_p))  # IShellItem**


def _vtbl_fn(obj_ptr: ctypes.c_void_p, index: int, proto):
    vtbl = ctypes.cast(ctypes.cast(obj_ptr, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    return proto(vtbl[index])


ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, DWORD]
ole32.CoInitializeEx.restype = HRESULT

ole32.CoUninitialize.argtypes = []
ole32.CoUninitialize.restype = None

ole32.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, DWORD, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
ole32.CoCreateInstance.restype = HRESULT

ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
ole32.CoTaskMemFree.restype = None

CLSCTX_INPROC_SERVER = 1


def _hr_u32(hr: int) -> int:
    # 항상 32-bit unsigned로 표시/판단
    return ctypes.c_uint32(int(hr)).value


def _raise_if_failed(hr: int, msg: str) -> None:
    u = _hr_u32(hr)
    if u != 0:  # S_OK only
        raise OSError(f"{msg} (HRESULT=0x{u:08X})")


def _set_filters(dlg_ptr: ctypes.c_void_p, filters: Sequence[Filter]) -> None:
    if not filters:
        return

    specs = (COMDLG_FILTERSPEC * len(filters))()
    for i, f in enumerate(filters):
        specs[i].pszName = f.name
        specs[i].pszSpec = f.pattern

    # vtable layout:
    # 0-2 IUnknown, 3 Show
    # 4 SetFileTypes, 5 SetFileTypeIndex, ...
    fn_settypes = _vtbl_fn(dlg_ptr, 4, SetFileTypesProto)
    fn_setindex = _vtbl_fn(dlg_ptr, 5, SetFileTypeIndexProto)

    hr = fn_settypes(dlg_ptr, len(filters), specs)
    _raise_if_failed(hr, "SetFileTypes 실패")

    hr = fn_setindex(dlg_ptr, 1)
    _raise_if_failed(hr, "SetFileTypeIndex 실패")


def _set_title(dlg_ptr: ctypes.c_void_p, title: str) -> None:
    if not title:
        return
    fn = _vtbl_fn(dlg_ptr, 17, SetTitleProto)
    hr = fn(dlg_ptr, title)
    _raise_if_failed(hr, "SetTitle 실패")


def _set_default_ext(dlg_ptr: ctypes.c_void_p, default_ext: str) -> None:
    """
    ✅ 핵심 수정:
    IFileDialog::SetDefaultExtension 는 vtable index 22 입니다.
    (21은 AddPlace 슬롯이라 호출이 꼬여서 0xFFFFFFFF... 같은 값이 나올 수 있음)
    """
    if not default_ext:
        return
    fn = _vtbl_fn(dlg_ptr, 22, SetDefaultExtensionProto)
    hr = fn(dlg_ptr, default_ext)
    # default extension은 실패해도 치명적이진 않지만, 여기선 정확히 체크
    _raise_if_failed(hr, "SetDefaultExtension 실패")


def _get_options(dlg_ptr: ctypes.c_void_p) -> int:
    fn = _vtbl_fn(dlg_ptr, 10, GetOptionsProto)
    opt = DWORD(0)
    hr = fn(dlg_ptr, ctypes.byref(opt))
    _raise_if_failed(hr, "GetOptions 실패")
    return int(opt.value)


def _set_options(dlg_ptr: ctypes.c_void_p, options: int) -> None:
    fn = _vtbl_fn(dlg_ptr, 9, SetOptionsProto)
    hr = fn(dlg_ptr, DWORD(options))
    _raise_if_failed(hr, "SetOptions 실패")


def _show_dialog(dlg_ptr: ctypes.c_void_p, owner_hwnd: int = 0) -> int:
    fn = _vtbl_fn(dlg_ptr, 3, ShowProto)
    hr = fn(dlg_ptr, wintypes.HWND(owner_hwnd))
    return int(hr)


def _get_result_item_path(shell_item_ptr: ctypes.c_void_p) -> str:
    fn_getname = _vtbl_fn(shell_item_ptr, 5, GetDisplayNameProto)  # IShellItem::GetDisplayName
    psz = LPWSTR()
    hr = fn_getname(shell_item_ptr, SIGDN_FILESYSPATH, ctypes.byref(psz))
    _raise_if_failed(hr, "IShellItem.GetDisplayName 실패")
    try:
        return psz.value
    finally:
        ole32.CoTaskMemFree(psz)


def _release(ptr: Optional[ctypes.c_void_p]) -> None:
    if not ptr:
        return
    try:
        fn = _vtbl_fn(ptr, 2, ReleaseProto)
        fn(ptr)
    except Exception:
        pass


def _pick_open_impl(
    *,
    multi: bool,
    title: str,
    filters: Sequence[Filter],
    default_ext: str,
    owner_hwnd: int = 0,
) -> List[str]:
    dlg = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(
        ctypes.byref(CLSID_FileOpenDialog),
        None,
        CLSCTX_INPROC_SERVER,
        ctypes.byref(IID_IFileOpenDialog),
        ctypes.byref(dlg),
    )
    _raise_if_failed(hr, "CoCreateInstance(FileOpenDialog) 실패")

    try:
        _set_title(dlg, title)
        if filters:
            _set_filters(dlg, filters)
        if default_ext:
            _set_default_ext(dlg, default_ext)

        opt = _get_options(dlg)
        opt |= FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST | FOS_FILEMUSTEXIST | FOS_NOCHANGEDIR
        if multi:
            opt |= FOS_ALLOWMULTISELECT
        _set_options(dlg, opt)

        hr_show = _show_dialog(dlg, owner_hwnd)
        if _hr_u32(hr_show) != 0:
            # 취소 포함: 빈 리스트
            return []

        if not multi:
            fn_getresult = _vtbl_fn(dlg, 20, GetResultProto)
            item = ctypes.c_void_p()
            hr = fn_getresult(dlg, ctypes.byref(item))
            _raise_if_failed(hr, "GetResult 실패")
            try:
                return [_get_result_item_path(item)]
            finally:
                _release(item)

        fn_getresults = _vtbl_fn(dlg, 27, GetResultsProto)  # IFileOpenDialog::GetResults
        arr = ctypes.c_void_p()
        hr = fn_getresults(dlg, ctypes.byref(arr))
        _raise_if_failed(hr, "GetResults 실패")

        try:
            fn_count = _vtbl_fn(arr, 7, GetCountProto)  # IShellItemArray::GetCount
            cnt = DWORD(0)
            hr = fn_count(arr, ctypes.byref(cnt))
            _raise_if_failed(hr, "IShellItemArray.GetCount 실패")

            fn_itemat = _vtbl_fn(arr, 8, GetItemAtProto)  # GetItemAt
            paths: List[str] = []
            for i in range(int(cnt.value)):
                it = ctypes.c_void_p()
                hr = fn_itemat(arr, DWORD(i), ctypes.byref(it))
                if _hr_u32(hr) != 0:
                    continue
                try:
                    paths.append(_get_result_item_path(it))
                finally:
                    _release(it)
            return paths
        finally:
            _release(arr)
    finally:
        _release(dlg)


def _pick_save_impl(
    *,
    title: str,
    filters: Sequence[Filter],
    default_ext: str,
    default_filename: str,
    owner_hwnd: int = 0,
) -> str:
    dlg = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(
        ctypes.byref(CLSID_FileSaveDialog),
        None,
        CLSCTX_INPROC_SERVER,
        ctypes.byref(IID_IFileSaveDialog),
        ctypes.byref(dlg),
    )
    _raise_if_failed(hr, "CoCreateInstance(FileSaveDialog) 실패")

    try:
        _set_title(dlg, title)
        if filters:
            _set_filters(dlg, filters)
        if default_ext:
            _set_default_ext(dlg, default_ext)

        # IFileDialog::SetFileName vtable index 15
        if default_filename:
            SetFileNameProto = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, LPCWSTR)
            fn_setfilename = _vtbl_fn(dlg, 15, SetFileNameProto)
            fn_setfilename(dlg, default_filename)

        opt = _get_options(dlg)
        opt |= FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST | FOS_OVERWRITEPROMPT | FOS_NOCHANGEDIR
        _set_options(dlg, opt)

        hr_show = _show_dialog(dlg, owner_hwnd)
        if _hr_u32(hr_show) != 0:
            return ""

        fn_getresult = _vtbl_fn(dlg, 20, GetResultProto)
        item = ctypes.c_void_p()
        hr = fn_getresult(dlg, ctypes.byref(item))
        _raise_if_failed(hr, "GetResult 실패")
        try:
            return _get_result_item_path(item)
        finally:
            _release(item)
    finally:
        _release(dlg)


# -----------------------------
# STA thread runner
# -----------------------------
class _StaRunner:
    def __init__(self) -> None:
        self._q: "queue.Queue[Tuple[callable, queue.Queue]]" = queue.Queue()
        self._t = threading.Thread(target=self._loop, name="STAFilePicker", daemon=True)
        self._t.start()

    def _loop(self) -> None:
        hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        # S_OK(0) / S_FALSE(1) 허용
        if int(hr) not in (S_OK, S_FALSE):
            # 초기화 실패면 계속은 도나, 호출 시마다 실패가 날 수 있음
            pass

        try:
            while True:
                fn, reply = self._q.get()
                try:
                    res = fn()
                    reply.put((True, res))
                except Exception as e:
                    reply.put((False, e))
        finally:
            try:
                ole32.CoUninitialize()
            except Exception:
                pass

    def call(self, fn):
        reply: "queue.Queue[Tuple[bool, object]]" = queue.Queue()
        self._q.put((fn, reply))
        ok, payload = reply.get()
        if ok:
            return payload
        raise payload  # type: ignore


_runner = _StaRunner()


# -----------------------------
# Public API
# -----------------------------
def pick_open_file(
    *,
    title: str = "파일 선택",
    filters: Sequence[Filter] = (),
    default_ext: str = "",
    owner_hwnd: int = 0,
) -> str:
    def _do():
        paths = _pick_open_impl(multi=False, title=title, filters=filters, default_ext=default_ext, owner_hwnd=owner_hwnd)
        return paths[0] if paths else ""

    return str(_runner.call(_do))


def pick_open_files(
    *,
    title: str = "파일 선택(복수)",
    filters: Sequence[Filter] = (),
    default_ext: str = "",
    owner_hwnd: int = 0,
) -> List[str]:
    def _do():
        return _pick_open_impl(multi=True, title=title, filters=filters, default_ext=default_ext, owner_hwnd=owner_hwnd)

    return list(_runner.call(_do))


def pick_save_file(
    *,
    title: str = "저장 위치 선택",
    filters: Sequence[Filter] = (),
    default_ext: str = "",
    default_filename: str = "",
    owner_hwnd: int = 0,
) -> str:
    def _do():
        return _pick_save_impl(
            title=title,
            filters=filters,
            default_ext=default_ext,
            default_filename=default_filename,
            owner_hwnd=owner_hwnd,
        )

    return str(_runner.call(_do))
