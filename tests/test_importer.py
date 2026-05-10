from pathlib import Path

from PIL import Image

from digikam_piwigo_exporter.config import ImportConfig
from digikam_piwigo_exporter.importer import ImportAction, PiwigoImporter
from digikam_piwigo_exporter.scanner import scan_images


class FakePiwigo:
    def __init__(self) -> None:
        self.uploads: list[dict] = []
        self.associations: list[tuple[int, int]] = []
        self.info_updates: list[dict] = []
        self.created_or_found_albums: list[str] = []
        self.found_albums: list[str] = []
        self.albums = {
            "Trips": 1,
            "Shared / Family": 2,
        }
        self.existing_by_checksum: dict[str, int] = {}

    def login(self) -> None:
        pass

    def find_or_create_album(
        self,
        album_path: str,
        *,
        created_status: str | None = None,
    ) -> int:
        self.created_or_found_albums.append(album_path)
        return self.albums[album_path]

    def find_album(self, album_path: str) -> int | None:
        self.found_albums.append(album_path)
        return self.albums.get(album_path)

    def find_image_by_checksum(self, checksum: str) -> int | None:
        return self.existing_by_checksum.get(checksum)

    def upload_simple(self, **kwargs) -> int:
        self.uploads.append(kwargs)
        return 42

    def associate_image(self, *, image_id: int, category_id: int) -> None:
        self.associations.append((image_id, category_id))

    def update_image_info(self, *, image_id: int, level: int | None) -> None:
        self.info_updates.append({"image_id": image_id, "level": level})


def write_image(path: Path) -> None:
    Image.new("RGB", (1, 1), "white").save(path)


def write_sidecar(path: Path) -> None:
    path.with_suffix(".jpg.xmp").write_text(
        """<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:RDF>
    <rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/">
      <dc:title><rdf:Alt><rdf:li xml:lang="x-default">Photo title</rdf:li></rdf:Alt></dc:title>
      <dc:description><rdf:Alt><rdf:li xml:lang="x-default">Photo comment</rdf:li></rdf:Alt></dc:description>
      <dc:subject><rdf:Bag><rdf:li>tag-a</rdf:li><rdf:li>share-family</rdf:li></rdf:Bag></dc:subject>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>""",
        encoding="utf-8",
    )


def test_scan_images_recurses_supported_extensions(tmp_path: Path) -> None:
    write_image(tmp_path / "a.jpg")
    nested = tmp_path / "nested"
    nested.mkdir()
    write_image(nested / "b.PNG")
    (tmp_path / "note.txt").write_text("ignore", encoding="utf-8")

    assert [path.relative_to(tmp_path) for path in scan_images(tmp_path)] == [
        Path("a.jpg"),
        Path("nested/b.PNG"),
    ]


def test_dry_run_reports_upload_and_share_association_without_writes(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "photo.jpg"
    write_image(image_path)
    write_sidecar(image_path)
    piwigo = FakePiwigo()
    importer = PiwigoImporter(
        piwigo=piwigo,
        config=ImportConfig(share_albums={"share-family": "Shared / Family"}),
    )

    actions = importer.import_folder(tmp_path, "Trips", dry_run=True)

    assert [action.kind for action in actions] == [
        ImportAction.UPLOAD,
        ImportAction.ASSOCIATE,
    ]
    assert piwigo.uploads == []
    assert piwigo.associations == []
    assert piwigo.created_or_found_albums == []
    assert piwigo.found_albums == ["Trips", "Shared / Family"]


def test_dry_run_does_not_create_missing_albums(tmp_path: Path) -> None:
    image_path = tmp_path / "photo.jpg"
    write_image(image_path)
    write_sidecar(image_path)
    piwigo = FakePiwigo()
    piwigo.albums = {}
    importer = PiwigoImporter(
        piwigo=piwigo,
        config=ImportConfig(share_albums={"share-family": "Shared / Family"}),
    )

    actions = importer.import_folder(tmp_path, "Trips", dry_run=True)

    assert [action.kind for action in actions] == [
        ImportAction.UPLOAD,
        ImportAction.ASSOCIATE,
    ]
    assert [action.album_id for action in actions] == [None, None]
    assert piwigo.created_or_found_albums == []
    assert piwigo.found_albums == ["Trips", "Shared / Family"]


def test_import_uploads_metadata_and_associates_share_album(tmp_path: Path) -> None:
    image_path = tmp_path / "photo.jpg"
    write_image(image_path)
    write_sidecar(image_path)
    piwigo = FakePiwigo()
    importer = PiwigoImporter(
        piwigo=piwigo,
        config=ImportConfig(share_albums={"share-family": "Shared / Family"}),
    )

    actions = importer.import_folder(tmp_path, "Trips", dry_run=False)

    assert [action.kind for action in actions] == [
        ImportAction.UPLOAD,
        ImportAction.ASSOCIATE,
    ]
    assert piwigo.uploads[0]["category_id"] == 1
    assert piwigo.uploads[0]["name"] == "Photo title"
    assert piwigo.uploads[0]["comment"] == "Photo comment"
    assert piwigo.uploads[0]["tags"] == ["tag-a", "share-family"]
    assert piwigo.associations == [(42, 2)]


def test_existing_checksum_skips_upload_but_keeps_share_association(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "photo.jpg"
    write_image(image_path)
    write_sidecar(image_path)
    piwigo = FakePiwigo()
    importer = PiwigoImporter(
        piwigo=piwigo,
        config=ImportConfig(share_albums={"share-family": "Shared / Family"}),
    )
    checksum = importer.checksum(image_path)
    piwigo.existing_by_checksum[checksum] = 99

    actions = importer.import_folder(tmp_path, "Trips", dry_run=False)

    assert [action.kind for action in actions] == [
        ImportAction.SKIP,
        ImportAction.ASSOCIATE,
    ]
    assert piwigo.uploads == []
    assert piwigo.associations == [(99, 2)]


def test_existing_checksum_updates_privacy_level(tmp_path: Path) -> None:
    image_path = tmp_path / "photo.jpg"
    write_image(image_path)
    write_sidecar(image_path)
    piwigo = FakePiwigo()
    importer = PiwigoImporter(
        piwigo=piwigo,
        config=ImportConfig(
            share_albums={"share-family": "Shared / Family"},
            default_level=8,
        ),
    )
    checksum = importer.checksum(image_path)
    piwigo.existing_by_checksum[checksum] = 99

    importer.import_folder(tmp_path, "Trips", dry_run=False)

    assert piwigo.info_updates == [{"image_id": 99, "level": 8}]
