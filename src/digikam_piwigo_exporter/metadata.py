from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "exif": "http://ns.adobe.com/exif/1.0/",
    "photoshop": "http://ns.adobe.com/photoshop/1.0/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "tiff": "http://ns.adobe.com/tiff/1.0/",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "lr": "http://ns.adobe.com/lightroom/1.0/",
}


@dataclass(frozen=True)
class ImageMetadata:
    title: str
    description: str | None = None
    tags: tuple[str, ...] = ()
    hierarchical_tags: tuple[str, ...] = ()
    capture_date: str | None = None


def extract_metadata(image_path: Path) -> ImageMetadata:
    sidecar = _find_sidecar(image_path)
    sidecar_metadata = _read_xmp_sidecar(sidecar) if sidecar else None
    fallback = ImageMetadata(title=image_path.stem)

    if sidecar_metadata is None:
        return fallback

    return ImageMetadata(
        title=sidecar_metadata.title or fallback.title,
        description=sidecar_metadata.description or fallback.description,
        tags=sidecar_metadata.tags or fallback.tags,
        hierarchical_tags=sidecar_metadata.hierarchical_tags
        or fallback.hierarchical_tags,
        capture_date=sidecar_metadata.capture_date or fallback.capture_date,
    )


def _find_sidecar(image_path: Path) -> Path | None:
    candidates = (
        image_path.with_suffix(f"{image_path.suffix}.xmp"),
        image_path.with_suffix(".xmp"),
    )
    return next((candidate for candidate in candidates if candidate.exists()), None)


def _read_xmp_sidecar(path: Path) -> ImageMetadata:
    root = ElementTree.parse(path).getroot()

    return ImageMetadata(
        title=_first_alt_text(root, "dc:title") or "",
        description=_first_alt_text(root, "dc:description"),
        tags=tuple(_bag_values(root, "dc:subject")),
        hierarchical_tags=tuple(_bag_values(root, "lr:hierarchicalSubject")),
        capture_date=_first_text(root, "exif:DateTimeOriginal")
        or _first_text(root, "xmp:CreateDate")
        or _first_text(root, "photoshop:DateCreated"),
    )


def _first_alt_text(root: ElementTree.Element, path: str) -> str | None:
    for node in root.findall(f".//{path}/rdf:Alt/rdf:li", NS):
        if node.text and node.text.strip():
            return node.text.strip()
    return None


def _bag_values(root: ElementTree.Element, path: str) -> list[str]:
    values: list[str] = []
    for node in root.findall(f".//{path}/rdf:Bag/rdf:li", NS):
        if node.text and node.text.strip():
            values.append(node.text.strip())
    return values


def _first_text(root: ElementTree.Element, path: str) -> str | None:
    node = root.find(f".//{path}", NS)
    if node is not None and node.text and node.text.strip():
        return node.text.strip()

    namespace, name = path.split(":", maxsplit=1)
    attr_value = root.find(f".//*[@{{{NS[namespace]}}}{name}]")
    if attr_value is not None:
        value = attr_value.attrib.get(f"{{{NS[namespace]}}}{name}")
        if value and value.strip():
            return value.strip()
    return None
