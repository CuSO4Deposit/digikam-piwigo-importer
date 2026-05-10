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
        self._client = http_client or httpx.Client(
            timeout=60.0,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        )

    @property
    def ws_url(self) -> str:
        return f"{self.base_url}/ws.php?format=json"

    def login(self) -> None:
        if self.api_key:
            self.check_authenticated()
            return
        if not self.username or not self.password:
            raise PiwigoApiError("Missing Piwigo username/password or API key")
        self.call(
            "pwg.session.login",
            username=self.username,
            password=self.password,
        )

    def get_status(self) -> Any:
        return self.call("pwg.session.getStatus")

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
            categories = self._get_categories(parent_id)
            existing = self._find_child_category(categories, part, parent_id)
            if existing is not None:
                parent_id = existing
                continue

            payload: dict[str, Any] = {"name": part}
            if parent_id is not None:
                payload["parent"] = parent_id
            if created_status is not None:
                payload["status"] = created_status
            result = self.call("pwg.categories.add", **payload)
            parent_id = _extract_id(result, "id")

        if parent_id is None:
            raise PiwigoApiError(f"Could not resolve album: {album_path}")
        return parent_id

    def find_album(self, album_path: str) -> int | None:
        parts = [part.strip() for part in album_path.split("/") if part.strip()]
        if not parts:
            return None
        categories = self._get_categories()
        return self._find_exact_album_path(categories, album_path)

    def _get_categories(self, parent_id: int | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"recursive": "false"}
        if parent_id is not None:
            params["cat_id"] = str(parent_id)
        result = self.call("pwg.categories.getAdminList", **params)
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
            if _category_path(category) == normalized_path
        ]
        if len(matches) > 1:
            raise PiwigoApiError(f"Ambiguous album path: {album_path}")
        return matches[0] if matches else None

    def _matching_child_categories(
        self,
        categories: list[dict[str, Any]],
        name: str,
        parent_id: int | None,
    ) -> list[int]:
        return [
            int(category["id"])
            for category in categories
            if str(category.get("name", "")).strip() == name
            and _category_parent_id(category) == parent_id
        ]

    def _find_child_category(
        self,
        categories: list[dict[str, Any]],
        name: str,
        parent_id: int | None,
    ) -> int | None:
        matches = self._matching_child_categories(categories, name, parent_id)
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

        with image_path.open("rb") as image:
            response = self._client.post(
                self.ws_url,
                data=data,
                files={"image": (image_path.name, image)},
                headers=self._auth_headers(),
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
        response = self._client.post(
            self.ws_url,
            data=data,
            headers=self._auth_headers(),
        )
        return self._parse_response(response)

    def check_authenticated(self) -> None:
        status = self.get_status()
        if str(status.get("status", "guest")).lower() == "guest":
            raise PiwigoApiError(
                "Piwigo API key authenticated as guest; expected an admin-capable key"
            )

    def _auth_headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {"X-PIWIGO-API": self.api_key}

    def close(self) -> None:
        self._client.close()

    def _parse_response(self, response: httpx.Response) -> Any:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            body = response.text.strip()
            message = f"Piwigo HTTP error {response.status_code}"
            if body:
                message = f"{message}: {body}"
            raise PiwigoApiError(message) from error
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


def _category_path(category: dict[str, Any]) -> str:
    fullname = str(category.get("fullname") or "").strip()
    if fullname:
        return _normalize_album_path(fullname)
    global_rank = str(category.get("global_rank") or "").strip()
    if "/" in global_rank:
        return _normalize_album_path(global_rank)
    return str(category.get("name") or "").strip()


def _normalize_album_path(album_path: str) -> str:
    return " / ".join(part.strip() for part in album_path.split("/") if part.strip())
