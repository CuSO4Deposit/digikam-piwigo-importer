from pathlib import Path

from PIL import Image

from digikam_piwigo_exporter.metadata import extract_metadata


def write_image(path: Path) -> None:
    image = Image.new("RGB", (1, 1), "white")
    image.save(path)


def test_extracts_metadata_from_matching_xmp_sidecar(tmp_path: Path) -> None:
    image_path = tmp_path / "photo.jpg"
    write_image(image_path)
    image_path.with_suffix(".jpg.xmp").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:RDF>
    <rdf:Description
      xmlns:dc="http://purl.org/dc/elements/1.1/"
      xmlns:lr="http://ns.adobe.com/lightroom/1.0/"
      xmlns:exif="http://ns.adobe.com/exif/1.0/">
      <dc:title><rdf:Alt><rdf:li xml:lang="x-default">Sidecar title</rdf:li></rdf:Alt></dc:title>
      <dc:description><rdf:Alt><rdf:li xml:lang="x-default">Sidecar description</rdf:li></rdf:Alt></dc:description>
      <dc:subject><rdf:Bag><rdf:li>tag-a</rdf:li><rdf:li>share-family</rdf:li></rdf:Bag></dc:subject>
      <lr:hierarchicalSubject>
        <rdf:Bag>
          <rdf:li>Places|Kyoto</rdf:li>
          <rdf:li>People|Family</rdf:li>
        </rdf:Bag>
      </lr:hierarchicalSubject>
      <exif:DateTimeOriginal>2024-03-04T05:06:07</exif:DateTimeOriginal>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
""",
        encoding="utf-8",
    )

    metadata = extract_metadata(image_path)

    assert metadata.title == "Sidecar title"
    assert metadata.description == "Sidecar description"
    assert metadata.tags == ("tag-a", "share-family")
    assert metadata.hierarchical_tags == ("Places|Kyoto", "People|Family")
    assert metadata.capture_date == "2024-03-04T05:06:07"


def test_sidecar_values_override_filename_fallback(tmp_path: Path) -> None:
    image_path = tmp_path / "fallback-name.jpg"
    write_image(image_path)
    image_path.with_suffix(".xmp").write_text(
        """<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:RDF>
    <rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/">
      <dc:title><rdf:Alt><rdf:li xml:lang="x-default">Preferred title</rdf:li></rdf:Alt></dc:title>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
""",
        encoding="utf-8",
    )

    metadata = extract_metadata(image_path)

    assert metadata.title == "Preferred title"


def test_embedded_xmp_is_used_when_sidecar_is_missing(tmp_path: Path) -> None:
    image_path = tmp_path / "embedded.jpg"
    image_path.write_bytes(
        b"prefix"
        b'<x:xmpmeta xmlns:x="adobe:ns:meta/" '
        b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        b"<rdf:RDF>"
        b'<rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/">'
        b"<dc:title><rdf:Alt><rdf:li>Embedded title</rdf:li></rdf:Alt></dc:title>"
        b"<dc:subject><rdf:Bag><rdf:li>embedded-tag</rdf:li></rdf:Bag></dc:subject>"
        b"</rdf:Description>"
        b"</rdf:RDF>"
        b"</x:xmpmeta>"
        b"suffix"
    )

    metadata = extract_metadata(image_path)

    assert metadata.title == "Embedded title"
    assert metadata.tags == ("embedded-tag",)
