from digikam_piwigo_exporter.cli import build_parser
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
