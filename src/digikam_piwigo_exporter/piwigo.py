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

    def find_or_create_album(self, album_path: str) -> int:
        existing = self.find_album(album_path)
        if existing is not None:
            return existing

        parent_id: int | None = None
        parts = [part.strip() for part in album_path.split("/") if part.strip()]
        if not parts:
            raise PiwigoApiError("Album path is empty")

        current_path = ""
        for part in parts:
            current_path = f"{current_path} / {part}" if current_path else part
            existing = self.find_album(current_path)
            if existing is None:
                payload: dict[str, Any] = {"name": part}
                if parent_id is not None:
                    payload["parent"] = parent_id
                result = self.call("pwg.categories.add", **payload)
                parent_id = _extract_id(result, "id")
            else:
                parent_id = existing

        if parent_id is None:
            raise PiwigoApiError(f"Could not resolve album: {album_path}")
        return parent_id

    def find_album(self, album_path: str) -> int | None:
        result = self.call("pwg.categories.getList", recursive="true")
        categories = result.get(
            "categories", result if isinstance(result, list) else []
        )
        matches: list[int] = []
        for category in categories:
            category_id = int(category["id"])
            names = {
                str(category.get("global_rank", "")).strip(),
                str(category.get("name", "")).strip(),
            }
            if album_path.strip() in names:
                matches.append(category_id)
        if len(matches) > 1:
            raise PiwigoApiError(f"Ambiguous album path or name: {album_path}")
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
