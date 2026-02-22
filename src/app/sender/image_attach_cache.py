# ✅ FILE: src/app/sender/image_attach_cache.py
from __future__ import annotations

import hashlib
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

DEFAULT_PREFIX = "kakao_sender_attach"
DEFAULT_TTL_SEC = 60 * 60 * 6  # 6시간


@dataclass
class CacheEntry:
    path: Path
    size: int
    last_used_ts: float
    created_ts: float


_cache: Dict[str, CacheEntry] = {}
_cache_max_items: int = 256


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_unlink(p: Path) -> None:
    try:
        if p.exists():
            p.unlink()
    except Exception:
        pass


def _prune_by_limits(*, ttl_sec: float) -> None:
    now = time.time()

    expired = [k for k, e in _cache.items() if (now - e.last_used_ts) > ttl_sec]
    for k in expired:
        _safe_unlink(_cache[k].path)
        _cache.pop(k, None)

    if len(_cache) <= _cache_max_items:
        return

    items = sorted(_cache.items(), key=lambda kv: kv[1].last_used_ts)
    overflow = len(_cache) - _cache_max_items
    for i in range(max(0, overflow)):
        k, e = items[i]
        _safe_unlink(e.path)
        _cache.pop(k, None)


def set_cache_limits(*, max_items: int = 256) -> None:
    global _cache_max_items
    _cache_max_items = max(16, int(max_items))


def get_or_create_temp_png(
    *,
    png_bytes: bytes,
    prefix: str = DEFAULT_PREFIX,
    ttl_sec: float = DEFAULT_TTL_SEC,
    cache_dir: Optional[Path] = None,
) -> Path:
    if not png_bytes:
        raise ValueError("png_bytes is empty")

    key = _sha256_hex(png_bytes)
    now = time.time()

    t_prune0 = time.perf_counter()
    _prune_by_limits(ttl_sec=ttl_sec)
    t_prune_ms = int((time.perf_counter() - t_prune0) * 1000)

    hit = _cache.get(key)
    if hit and hit.path.exists() and hit.size == len(png_bytes):
        hit.last_used_ts = now
        # DEBUG(필요시): prune_ms와 cache hit 확인
        print(f"[IMG-CACHE] hit prune_ms={t_prune_ms} path={hit.path}")
        return hit.path

    base_dir = cache_dir or Path(tempfile.gettempdir())
    base_dir.mkdir(parents=True, exist_ok=True)

    fname = f"{prefix}_{key[:12]}.png"
    path = base_dir / fname
    t_write0 = time.perf_counter()
    try:
        if (not path.exists()) or (path.stat().st_size != len(png_bytes)):
            path.write_bytes(png_bytes)
    except Exception:
        ts_path = base_dir / f"{prefix}_{int(now * 1000)}_{key[:12]}.png"
        ts_path.write_bytes(png_bytes)
        path = ts_path
    t_write_ms = int((time.perf_counter() - t_write0) * 1000)
    # DEBUG(필요시)
    print(f"[IMG-CACHE] write_ms={t_write_ms} prune_ms={t_prune_ms} path={path} size={len(png_bytes)}")

    _cache[key] = CacheEntry(
        path=path,
        size=len(png_bytes),
        last_used_ts=now,
        created_ts=now,
    )
    return path


def clear_image_cache(*, delete_files: bool = True) -> None:
    global _cache
    if delete_files:
        for e in list(_cache.values()):
            _safe_unlink(e.path)
    _cache = {}


def cache_stats() -> Tuple[int, int]:
    total = 0
    for e in _cache.values():
        total += int(e.size or 0)
    return (len(_cache), total)