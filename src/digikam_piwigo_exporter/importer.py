from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from digikam_piwigo_exporter.config import ImportConfig
from digikam_piwigo_exporter.metadata import extract_metadata
from digikam_piwigo_exporter.routing import ShareRouter
from digikam_piwigo_exporter.scanner import scan_images


class PiwigoGateway(Protocol):
    def login(self) -> None: ...

    def find_or_create_album(self, album_path: str) -> int: ...

    def find_album(self, album_path: str) -> int | None: ...

    def find_image_by_checksum(self, checksum: str) -> int | None: ...

    def upload_simple(
        self,
        *,
        image_path: Path,
        category_id: int,
        name: str,
        comment: str | None,
        tags: list[str],
        level: int | None = None,
    ) -> int: ...

    def associate_image(self, *, image_id: int, category_id: int) -> None: ...

    def update_image_info(self, *, image_id: int, level: int | None) -> None: ...


class ImportAction(StrEnum):
    UPLOAD = "upload"
    SKIP = "skip"
    ASSOCIATE = "associate"


@dataclass(frozen=True)
class ImportEvent:
    kind: ImportAction
    image_path: Path
    message: str
    image_id: int | None = None
    album_id: int | None = None


class PiwigoImporter:
    def __init__(self, *, piwigo: PiwigoGateway, config: ImportConfig) -> None:
        self._piwigo = piwigo
        self._config = config
        self._router = ShareRouter(config.share_albums)

    def import_folder(
        self,
        input_folder: Path,
        album: str,
        *,
        dry_run: bool,
    ) -> list[ImportEvent]:
        if not input_folder.is_dir():
            raise NotADirectoryError(input_folder)

        events: list[ImportEvent] = []
        target_album_id = self._album_id(album, dry_run=dry_run)
        share_album_ids = {
            album_path: self._album_id(album_path, dry_run=dry_run)
            for album_path in dict.fromkeys(self._config.share_albums.values())
        }

        for image_path in scan_images(input_folder):
            metadata = extract_metadata(image_path)
            checksum = self.checksum(image_path)
            existing_id = self._piwigo.find_image_by_checksum(checksum)
            tags = [*metadata.tags, *metadata.hierarchical_tags]

            if existing_id is not None:
                image_id = existing_id
                events.append(
                    ImportEvent(
                        kind=ImportAction.SKIP,
                        image_path=image_path,
                        image_id=image_id,
                        message=f"existing checksum {checksum}",
                    )
                )
                if not dry_run and self._config.default_level is not None:
                    self._piwigo.update_image_info(
                        image_id=image_id,
                        level=self._config.default_level,
                    )
            else:
                events.append(
                    ImportEvent(
                        kind=ImportAction.UPLOAD,
                        image_path=image_path,
                        album_id=target_album_id,
                        message=f"upload to album {album}",
                    )
                )
                image_id = -1
                if not dry_run:
                    image_id = self._piwigo.upload_simple(
                        image_path=image_path,
                        category_id=target_album_id,
                        name=metadata.title,
                        comment=metadata.description,
                        tags=tags,
                        level=self._config.default_level,
                    )

            for share_album in self._router.albums_for_tags(tags):
                share_album_id = share_album_ids[share_album]
                events.append(
                    ImportEvent(
                        kind=ImportAction.ASSOCIATE,
                        image_path=image_path,
                        image_id=None if image_id == -1 else image_id,
                        album_id=share_album_id,
                        message=f"associate with {share_album}",
                    )
                )
                if not dry_run and image_id != -1:
                    self._piwigo.associate_image(
                        image_id=image_id,
                        category_id=share_album_id,
                    )

        return events

    @staticmethod
    def checksum(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _album_id(self, album_path: str, *, dry_run: bool) -> int | None:
        if dry_run:
            return self._piwigo.find_album(album_path)
        return self._piwigo.find_or_create_album(album_path)
