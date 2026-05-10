from __future__ import annotations

from collections.abc import Mapping, Sequence


class ShareMappingError(ValueError):
    pass


class ShareRouter:
    def __init__(self, share_albums: Mapping[str, str]) -> None:
        self._share_albums = {
            tag.strip(): album.strip()
            for tag, album in share_albums.items()
            if tag and tag.strip()
        }
        empty_tags = [
            tag
            for tag, album in share_albums.items()
            if tag and tag.strip() and not album.strip()
        ]
        if empty_tags:
            joined = ", ".join(sorted(empty_tags))
            raise ShareMappingError(f"Share tags missing album paths: {joined}")

    @property
    def share_tags(self) -> frozenset[str]:
        return frozenset(self._share_albums)

    def albums_for_tags(self, tags: Sequence[str]) -> tuple[str, ...]:
        albums: list[str] = []
        seen: set[str] = set()
        for tag in tags:
            album = self._share_albums.get(tag)
            if album and album not in seen:
                albums.append(album)
                seen.add(album)
        return tuple(albums)
