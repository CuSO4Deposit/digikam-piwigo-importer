from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Protocol

from digikam_piwigo_exporter.config import ImportConfig


class ReconcileGateway(Protocol):
    def find_or_create_album(
        self,
        album_path: str,
        *,
        created_status: str | None = None,
    ) -> int: ...

    def get_images_by_tag(self, tag_name: str) -> Iterable[int]: ...

    def associate_image(self, *, image_id: int, category_id: int) -> None: ...


class ReconcileAction(StrEnum):
    ASSOCIATE = "associate"


@dataclass(frozen=True)
class ReconcileEvent:
    kind: ReconcileAction
    tag: str
    album: str
    album_id: int
    image_id: int
    message: str


class ShareReconciler:
    def __init__(self, *, piwigo: ReconcileGateway, config: ImportConfig) -> None:
        self._piwigo = piwigo
        self._config = config

    def reconcile(self, *, dry_run: bool) -> list[ReconcileEvent]:
        events: list[ReconcileEvent] = []
        for tag, album in self._config.share_albums.items():
            album_id = self._piwigo.find_or_create_album(
                album,
                created_status=self._config.created_album_status,
            )
            for image_id in self._piwigo.get_images_by_tag(tag):
                events.append(
                    ReconcileEvent(
                        kind=ReconcileAction.ASSOCIATE,
                        tag=tag,
                        album=album,
                        album_id=album_id,
                        image_id=image_id,
                        message=f"associate tag {tag} image with {album}",
                    )
                )
                if not dry_run:
                    self._piwigo.associate_image(
                        image_id=image_id,
                        category_id=album_id,
                    )
        return events
