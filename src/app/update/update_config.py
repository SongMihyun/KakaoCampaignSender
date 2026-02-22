# src/app/update/update_config.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UpdateConfig:
    owner: str
    repo: str
    channel: str = "stable"  # 추후 beta 채널 분리 가능

    @property
    def latest_json_url(self) -> str:
        # ✅ Release의 "latest"에 업로드된 asset 경로
        return f"https://github.com/{self.owner}/{self.repo}/releases/latest/download/latest.json"


# ✅ 프로젝트에 맞게 수정
UPDATE_CONFIG = UpdateConfig(
    owner="YOUR_GITHUB_OWNER",
    repo="YOUR_GITHUB_REPO",
)