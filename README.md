# DigiKam Piwigo Importer

Command-line importer for publishing a DigiKam-managed album folder to a
self-hosted Piwigo instance through Piwigo's authenticated Web API.

This tool exists because the usual import paths each lose something important:

- DigiKam's Piwigo export does not reliably preserve tags.
- Piwigo filesystem sync has restrictive filename rules and can miss metadata
  such as descriptions.

The importer treats DigiKam's exported image files and XMP sidecars as the
source of truth, reads metadata locally, and sends title, description, tags,
and album associations explicitly to Piwigo.

It also supports a Piwigo-friendly access model: special DigiKam tags can be
mapped to additional Piwigo albums, so album-based Piwigo permissions can be
used without duplicating image files.

## Development

Enter the dev shell and run tests:

```sh
nix develop
pytest -v
```

Or run commands directly:

```sh
nix develop -c pytest -v
```

## Authentication

Credentials are not hardcoded. Use environment variables:

```sh
export PIWIGO_USERNAME='alice'
export PIWIGO_PASSWORD='secret'
```

If your Piwigo supports API keys, you can use:

```sh
export PIWIGO_API_KEY='pkid-XXXXXXXX-XXXXXXXXXXXX:YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY'
```

API key auth uses the `X-PIWIGO-API` HTTP header. The value must include both
the public key id and secret, separated by `:`:
`pkid-XXXXXXXX-XXXXXXXXXXXX:YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY`.
Config-file auth is supported, but environment variables take precedence. The
API key is always sent with the standard `X-PIWIGO-API` header.

Check the configured credentials without importing:

```sh
digikam-piwigo-import \
  --base-url https://photos.example.com \
  --input /tmp \
  --album "Unused" \
  --config config.toml \
  --check-auth
```

## Usage

Dry run:

```sh
digikam-piwigo-import \
  --input /photos/DigiKam/Album \
  --album "Trips / Kyoto" \
  --base-url https://photos.example.com \
  --config examples/config.toml \
  --dry-run
```

Import:

```sh
digikam-piwigo-import \
  --input /photos/DigiKam/Album \
  --album "Trips / Kyoto" \
  --base-url https://photos.example.com \
  --config examples/config.toml
```

First import without checksum lookups:

```sh
digikam-piwigo-import \
  --input /photos/DigiKam/Album \
  --album "Trips / Kyoto" \
  --base-url https://photos.example.com \
  --config examples/config.toml \
  --no-dedupe-check
```

Repair share-album associations for photos already in Piwigo:

```sh
digikam-piwigo-reconcile-shares \
  --base-url https://photos.example.com \
  --config examples/config.toml \
  --dry-run
```

The API explorer for a Piwigo instance is usually available at:

```text
https://photos.example.com/tools/ws.htm
```

## Metadata Behavior

The importer scans recursively for:

- `.jpg`, `.jpeg`, `.png`
- `.tif`, `.tiff`
- `.webp`
- `.heic`, `.heif`

For each image, matching XMP sidecars are checked in this order:

1. `photo.jpg.xmp`
2. `photo.xmp`

Sidecar metadata wins over fallback values. The importer extracts:

- title, sent as Piwigo `name`
- description, sent as Piwigo `comment`
- flat tags, sent as Piwigo `tags`
- hierarchical tags, also sent as Piwigo `tags`
- capture date, currently extracted for planning/future update support

## Share Routing

Piwigo permissions are album-based, so sharing intent is expressed with DigiKam
tags and mapped to albums in config:

```toml
[share_albums]
share-family = "Shared / Family"
share-friends = "Shared / Friends"
share-public = "Shared / Public"
```

An image tagged `share-family` is uploaded once to the target album, then
associated with `Shared / Family`. Configure Piwigo user/group ACLs on those
albums.

If photos were uploaded before a share-tag mapping existed, run
`digikam-piwigo-reconcile-shares`. It queries Piwigo's tag index with
`pwg.tags.getImages` for each configured share tag and appends matching images
to the mapped album. It does not read local DigiKam files or upload images.

For album-based access control, keep image privacy level public:

```toml
[piwigo]
default_level = 0
created_album_status = "private"
```

Piwigo evaluates both album ACLs and per-image privacy level. If you set
`default_level = 8`, the image itself is restricted to admins even when it is
in an album that other users can access.

`created_album_status = "private"` makes albums created by this importer
private at creation time. Existing albums are not changed; manage their ACLs in
Piwigo.

## Idempotency

The importer computes a SHA-256 checksum for each local file and asks Piwigo
for an existing image before uploading. Existing images are skipped and still
get share-album associations checked.

Use `--no-dedupe-check` for a known-empty first import to skip per-file
`pwg.images.search` calls. This is faster, but it is not idempotent: if the
same files already exist in Piwigo, they will be uploaded again.

Dry-run mode logs planned uploads, skips, and associations without write calls.

## Current API Notes

Uploads use `pwg.images.addSimple` with multipart form data. Share
reconciliation uses Piwigo's tag index. The client uses `httpx` and calls:

- `pwg.session.login`
- `pwg.categories.getAdminList`
- `pwg.categories.add`
- `pwg.images.addSimple`
- `pwg.images.search`
- `pwg.images.setInfo`
- `pwg.tags.getImages`

If your instance exposes a different idempotency search method, adjust
`PiwigoClient.find_image_by_checksum`.
