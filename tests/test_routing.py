import pytest

from digikam_piwigo_exporter.routing import ShareMappingError, ShareRouter


def test_resolves_share_tags_to_configured_album_paths() -> None:
    router = ShareRouter(
        {
            "share-family": "Shared / Family",
            "share-public": "Shared / Public",
        }
    )

    albums = router.albums_for_tags(["travel", "share-public", "share-family"])

    assert albums == ("Shared / Public", "Shared / Family")


def test_duplicate_share_tags_are_deduplicated_in_input_order() -> None:
    router = ShareRouter({"share-family": "Shared / Family"})

    albums = router.albums_for_tags(["share-family", "travel", "share-family"])

    assert albums == ("Shared / Family",)


def test_configured_share_tag_without_album_path_raises_clear_error() -> None:
    with pytest.raises(ShareMappingError, match="share-family"):
        ShareRouter({"share-family": ""})
