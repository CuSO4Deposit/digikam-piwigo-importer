from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx


class PiwigoApiError(RuntimeError):
    pass


class PiwigoClient:
    def __init__(
        self,
        base_url: str,
        *,
        username: str | None = None,
        password: str | None = None,
        api_key: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.api_key = api_key
        self._client = http_client or httpx.Client(timeout=60.0)

    @property
    def ws_url(self) -> str:
        return f"{self.base_url}/ws.php?format=json"

    def login(self) -> None:
        if self.api_key:
            return
        if not self.username or not self.password:
            raise PiwigoApiError("Missing Piwigo username/password or API key")
        self.call(
            "pwg.session.login",
            username=self.username,
            password=self.password,
        )

    def find_or_create_album(
        self,
        album_path: str,
        *,
        created_status: str | None = None,
    ) -> int:
        parts = [part.strip() for part in album_path.split("/") if part.strip()]
        if not parts:
            raise PiwigoApiError("Album path is empty")

        categories = self._get_categories()
        existing = self._find_exact_album_path(categories, album_path)
        if existing is not None:
            return existing

        parent_id: int | None = None
        for part in parts:
            existing = self._find_child_category(categories, part, parent_id)
            if existing is None:
                created_parent_id = parent_id
                payload: dict[str, Any] = {"name": part}
                if parent_id is not None:
                    payload["parent"] = parent_id
                if created_status is not None:
                    payload["status"] = created_status
                result = self.call("pwg.categories.add", **payload)
                parent_id = _extract_id(result, "id")
                categories.append(
                    {
                        "id": parent_id,
                        "name": part,
                        "id_uppercat": created_parent_id,
                    }
                )
            else:
                parent_id = existing

        if parent_id is None:
            raise PiwigoApiError(f"Could not resolve album: {album_path}")
        return parent_id

    def find_album(self, album_path: str) -> int | None:
        parts = [part.strip() for part in album_path.split("/") if part.strip()]
        if not parts:
            return None
        parent_id: int | None = None
        categories = self._get_categories()
        existing = self._find_exact_album_path(categories, album_path)
        if existing is not None:
            return existing
        for part in parts:
            parent_id = self._find_child_category(categories, part, parent_id)
            if parent_id is None:
                return None
        return parent_id

    def _get_categories(self) -> list[dict[str, Any]]:
        result = self.call("pwg.categories.getList", recursive="true")
        categories = result.get(
            "categories", result if isinstance(result, list) else []
        )
        return list(categories)

    def _find_exact_album_path(
        self,
        categories: list[dict[str, Any]],
        album_path: str,
    ) -> int | None:
        normalized_path = _normalize_album_path(album_path)
        matches = [
            int(category["id"])
            for category in categories
            if _normalize_album_path(str(category.get("global_rank", "")))
            == normalized_path
        ]
        if len(matches) > 1:
            raise PiwigoApiError(f"Ambiguous album path: {album_path}")
        return matches[0] if matches else None

    def _find_child_category(
        self,
        categories: list[dict[str, Any]],
        name: str,
        parent_id: int | None,
    ) -> int | None:
        matches: list[int] = []
        for category in categories:
            category_id = int(category["id"])
            category_parent = _category_parent_id(category)
            if (
                str(category.get("name", "")).strip() == name
                and category_parent == parent_id
            ):
                matches.append(category_id)
        if len(matches) > 1:
            parent_label = "root" if parent_id is None else str(parent_id)
            raise PiwigoApiError(
                f"Ambiguous album name {name!r} under parent {parent_label}"
            )
        return matches[0] if matches else None

    def upload_simple(
        self,
        *,
        image_path: Path,
        category_id: int,
        name: str,
        comment: str | None,
        tags: Iterable[str],
        level: int | None = None,
    ) -> int:
        data: dict[str, Any] = {
            "method": "pwg.images.addSimple",
            "category": str(category_id),
            "name": name,
            "tags": ",".join(tags),
        }
        if comment:
            data["comment"] = comment
        if level is not None:
            data["level"] = str(level)
        if self.api_key:
            data["api_key"] = self.api_key

        with image_path.open("rb") as image:
            response = self._client.post(
                self.ws_url,
                data=data,
                files={"image": (image_path.name, image)},
            )
        result = self._parse_response(response)
        return _extract_id(result, "image_id")

    def associate_image(self, *, image_id: int, category_id: int) -> None:
        self.call(
            "pwg.images.setInfo",
            image_id=str(image_id),
            categories=str(category_id),
            multiple_value_mode="append",
        )

    def update_image_info(self, *, image_id: int, level: int | None) -> None:
        if level is None:
            return
        self.call(
            "pwg.images.setInfo",
            image_id=str(image_id),
            level=str(level),
        )

    def find_image_by_checksum(self, checksum: str) -> int | None:
        result = self.call("pwg.images.search", query=checksum)
        images = result.get("images", result if isinstance(result, list) else [])
        matches = [
            int(image["id"])
            for image in images
            if checksum
            in {
                str(image.get("md5sum", "")),
                str(image.get("checksum", "")),
                str(image.get("comment", "")),
                str(image.get("name", "")),
            }
        ]
        if len(matches) > 1:
            raise PiwigoApiError(f"Ambiguous existing image checksum: {checksum}")
        return matches[0] if matches else None

    def call(self, method: str, **params: Any) -> Any:
        data = {"method": method, **params}
        if self.api_key:
            data["api_key"] = self.api_key
        response = self._client.post(self.ws_url, data=data)
        return self._parse_response(response)

    def close(self) -> None:
        self._client.close()

    def _parse_response(self, response: httpx.Response) -> Any:
        response.raise_for_status()
        payload = response.json()
        if payload.get("stat") != "ok":
            message = payload.get("message") or payload.get("err") or payload
            raise PiwigoApiError(f"Piwigo API error: {message}")
        return payload.get("result", {})


def _extract_id(result: Any, key: str) -> int:
    if isinstance(result, dict):
        value = result.get(key) or result.get("id")
        if value is not None:
            return int(value)
    raise PiwigoApiError(f"Piwigo response did not include {key}: {result!r}")


def _category_parent_id(category: dict[str, Any]) -> int | None:
    uppercats = category.get("uppercats")
    if uppercats not in (None, ""):
        text = str(uppercats)
        separator = "," if "," in text else "/"
        parts = [part for part in text.split(separator) if part]
        if len(parts) <= 1:
            return None
        return int(parts[-2])

    value = (
        category.get("id_uppercat")
        or category.get("parent")
        or category.get("parent_id")
    )
    if value in (None, ""):
        return None
    if isinstance(value, int):
        if value == 0:
            return None
        return value
    text = str(value)
    parent_id = int(text)
    return None if parent_id == 0 else parent_id


def _normalize_album_path(album_path: str) -> str:
    return " / ".join(part.strip() for part in album_path.split("/") if part.strip())
