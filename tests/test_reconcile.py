from digikam_piwigo_exporter.config import ImportConfig
from digikam_piwigo_exporter.reconcile import ShareReconciler


class FakePiwigo:
    def __init__(self) -> None:
        self.albums = {"Shared / Family": 5}
        self.images_by_tag = {"share-family": [10, 11]}
        self.created_or_found_albums: list[str] = []
        self.associations: list[tuple[int, int]] = []

    def find_or_create_album(
        self,
        album_path: str,
        *,
        created_status: str | None = None,
    ) -> int:
        self.created_or_found_albums.append(album_path)
        return self.albums[album_path]

    def get_images_by_tag(self, tag_name: str) -> list[int]:
        return self.images_by_tag[tag_name]

    def associate_image(self, *, image_id: int, category_id: int) -> None:
        self.associations.append((image_id, category_id))


def test_reconciles_share_tag_images_to_configured_album() -> None:
    piwigo = FakePiwigo()
    reconciler = ShareReconciler(
        piwigo=piwigo,
        config=ImportConfig(share_albums={"share-family": "Shared / Family"}),
    )

    events = reconciler.reconcile(dry_run=False)

    assert piwigo.created_or_found_albums == ["Shared / Family"]
    assert piwigo.associations == [(10, 5), (11, 5)]
    assert [event.image_id for event in events] == [10, 11]


def test_reconcile_dry_run_does_not_associate() -> None:
    piwigo = FakePiwigo()
    reconciler = ShareReconciler(
        piwigo=piwigo,
        config=ImportConfig(share_albums={"share-family": "Shared / Family"}),
    )

    events = reconciler.reconcile(dry_run=True)

    assert piwigo.created_or_found_albums == ["Shared / Family"]
    assert piwigo.associations == []
    assert [event.image_id for event in events] == [10, 11]
