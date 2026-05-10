from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ImportConfig:
    username: str | None = None
    password: str | None = None
    api_key: str | None = None
    share_albums: dict[str, str] = field(default_factory=dict)
    default_level: int | None = None
    created_album_status: str | None = None


def load_config(path: Path | None) -> ImportConfig:
    data: dict = {}
    if path is not None:
        with path.open("rb") as handle:
            data = tomllib.load(handle)

    auth = data.get("auth", {})
    piwigo = data.get("piwigo", {})
    share_albums = data.get("share_albums", {})

    return ImportConfig(
        username=os.environ.get("PIWIGO_USERNAME") or auth.get("username"),
        password=os.environ.get("PIWIGO_PASSWORD") or auth.get("password"),
        api_key=os.environ.get("PIWIGO_API_KEY") or auth.get("api_key"),
        share_albums=dict(share_albums),
        default_level=piwigo.get("default_level"),
        created_album_status=piwigo.get("created_album_status"),
    )
