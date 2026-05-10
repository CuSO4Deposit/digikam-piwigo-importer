from pathlib import Path

import httpx

from digikam_piwigo_exporter.piwigo import PiwigoClient


def json_response(payload: dict) -> httpx.Response:
    return httpx.Response(200, json={"stat": "ok", "result": payload})


def test_login_posts_credentials_to_ws_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response({})

    client = PiwigoClient(
        "https://photos.example",
        username="alice",
        password="secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    client.login()

    assert requests[0].url == "https://photos.example/ws.php?format=json"
    body = requests[0].content.decode()
    assert "method=pwg.session.login" in body
    assert "username=alice" in body
    assert "password=secret" in body


def test_upload_simple_posts_image_and_metadata(tmp_path: Path) -> None:
    image_path = tmp_path / "photo.jpg"
    image_path.write_bytes(b"fake image")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response({"image_id": 42})

    client = PiwigoClient(
        "https://photos.example/",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    image_id = client.upload_simple(
        image_path=image_path,
        category_id=7,
        name="Title",
        comment="Description",
        tags=["tag-a", "Places|Kyoto"],
        level=0,
    )

    assert image_id == 42
    body = requests[0].content.decode(errors="ignore")
    assert "pwg.images.addSimple" in body
    assert "Title" in body
    assert "Description" in body
    assert "tag-a,Places|Kyoto" in body
    assert "photo.jpg" in body


def test_find_or_create_album_uses_existing_matching_path() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        data = dict(httpx.QueryParams(request.content.decode()))
        calls.append(data["method"])
        return json_response(
            {
                "categories": [
                    {"id": 5, "name": "Family", "global_rank": "Shared / Family"}
                ]
            }
        )

    client = PiwigoClient(
        "https://photos.example",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert client.find_or_create_album("Shared / Family") == 5
    assert calls == ["pwg.categories.getList"]


def test_associate_image_posts_category_update() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response({})

    client = PiwigoClient(
        "https://photos.example",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    client.associate_image(image_id=42, category_id=9)

    body = requests[0].content.decode()
    assert "method=pwg.images.setInfo" in body
    assert "image_id=42" in body
    assert "categories=9" in body
