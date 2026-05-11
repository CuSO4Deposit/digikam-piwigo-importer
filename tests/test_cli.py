from digikam_piwigo_exporter.cli import build_parser
from digikam_piwigo_exporter.cli import main
from digikam_piwigo_exporter.reconcile_cli import build_parser as build_reconcile_parser


def test_parser_accepts_no_dedupe_check() -> None:
    args = build_parser().parse_args(
        [
            "--input",
            "album",
            "--album",
            "Trips",
            "--base-url",
            "https://photos.example",
            "--no-dedupe-check",
        ]
    )

    assert args.no_dedupe_check is True


def test_parser_accepts_update_existing_metadata() -> None:
    args = build_parser().parse_args(
        [
            "--input",
            "album",
            "--album",
            "Trips",
            "--base-url",
            "https://photos.example",
            "--update-existing-metadata",
        ]
    )

    assert args.update_existing_metadata is True


def test_update_existing_metadata_conflicts_with_no_dedupe_check(
    capsys,
) -> None:
    exit_code = main(
        [
            "--input",
            "album",
            "--album",
            "Trips",
            "--base-url",
            "https://photos.example",
            "--no-dedupe-check",
            "--update-existing-metadata",
        ]
    )

    assert exit_code == 2
    assert (
        "--update-existing-metadata cannot be used with --no-dedupe-check"
        in capsys.readouterr().err
    )


def test_reconcile_parser_does_not_require_input_or_album() -> None:
    args = build_reconcile_parser().parse_args(
        [
            "--base-url",
            "https://photos.example",
            "--config",
            "config.toml",
            "--dry-run",
        ]
    )

    assert args.base_url == "https://photos.example"
    assert args.dry_run is True
