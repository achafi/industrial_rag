"""Local P&ID rendering, OCR and geometry, extracted from the validated notebook."""
from pathlib import Path
from importlib.metadata import version
import hashlib
import io
import json
import math
import re
import tempfile
import time
import unicodedata

import cairosvg
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from rapidocr_onnxruntime import RapidOCR
from pid_instruments import build_instrument_inventory

REVIEW_THRESHOLD = 0.8
REFERENCE_LAYOUT = json.loads(Path(__file__).with_name("reference_layout.json").read_text())

def deny_external_resource(url, resource_type):
    raise ValueError("SVG references an external resource. Upload a self-contained drawing.")

def render_input(path, target_width, page=1):
    suffix = path.suffix.lower()
    if page < 1:
        raise ValueError("PAGE must be one-based.")
    if suffix != ".pdf" and page != 1:
        raise ValueError("SVG and PNG inputs have one page.")
    if suffix == ".svg":
        png = cairosvg.surface.PNGSurface.convert(bytestring=path.read_bytes(), output_width=target_width,
                              background_color="white", url_fetcher=deny_external_resource)
        return Image.open(io.BytesIO(png)).convert("RGB")
    if suffix == ".pdf":
        import pypdfium2 as pdfium
        document = pdfium.PdfDocument(str(path))
        try:
            if page > len(document):
                raise ValueError(f"PDF has {len(document)} pages, requested {page}.")
            pdf_page = document[page - 1]
            try:
                bitmap = pdf_page.render(scale=target_width / pdf_page.get_width())
                try:
                    return bitmap.to_pil().convert("RGB").copy()
                finally:
                    bitmap.close()
            finally:
                pdf_page.close()
        finally:
            document.close()
    if suffix == ".png":
        with Image.open(path) as source:
            rgba = ImageOps.exif_transpose(source).convert("RGBA")
            background = Image.new("RGBA", rgba.size, "white")
            background.alpha_composite(rgba)
            rgb = background.convert("RGB")
            height = round(rgb.height * target_width / rgb.width)
            return rgb.resize((target_width, height), Image.Resampling.LANCZOS)
    raise ValueError("Supported inputs: SVG, PDF, PNG")


def tile_starts(length, size, overlap):
    if length <= size:
        return [0]
    starts = list(range(0, length - size + 1, size - overlap))
    if starts[-1] != length - size:
        starts.append(length - size)
    return starts


def unrotate_points(points, angle, width, height):
    """Inverse of np.rot90 on continuous image-boundary coordinates."""
    points = np.asarray(points, dtype=float)
    x, y = points[:, 0], points[:, 1]
    if angle == 0:
        return points.copy()
    if angle == 90:
        return np.column_stack((width - y, x))
    if angle == 270:
        return np.column_stack((y, height - x))
    raise ValueError("Only 0, 90 and 270 degree passes are supported.")


def internal_edge_flags(box, tile_bounds, page_width, page_height, margin):
    x0, y0, x1, y1 = box
    left, top, right, bottom = tile_bounds
    return [name for name, touches in (
        ("left", left > 0 and x0 - left <= margin),
        ("top", top > 0 and y0 - top <= margin),
        ("right", right < page_width and right - x1 <= margin),
        ("bottom", bottom < page_height and bottom - y1 <= margin),
    ) if touches]


def normalize_text(text):
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(str.maketrans({char: "-" for char in "‐‑‒–—−"}))
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s*-\s*", "-", text)


def overlap_fraction(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, x1 - x0) * max(0, y1 - y0)
    smaller = min((a[2] - a[0]) * (a[3] - a[1]),
                  (b[2] - b[0]) * (b[3] - b[1]))
    return intersection / smaller if smaller else 0.0


def same_text_region(a, b):
    if (a["tile"], a["rotation_ccw"]) == (b["tile"], b["rotation_ccw"]):
        return False
    if overlap_fraction(a["box"], b["box"]) < 0.70:
        return False
    ax0, ay0, ax1, ay1 = a["box"]
    bx0, by0, bx1, by1 = b["box"]
    aw, ah, bw, bh = ax1 - ax0, ay1 - ay0, bx1 - bx0, by1 - by0
    av, bv = ah > 1.5 * aw, bh > 1.5 * bw
    # Preserve adjacent labels with different orientations rather than
    # allowing a large rotated region to swallow a horizontal label.
    if av != bv:
        return False
    if av or bv:
        return abs((ax0 + ax1 - bx0 - bx1) / 2) <= 0.5 * max(aw, bw)
    return abs((ay0 + ay1 - by0 - by1) / 2) <= 0.5 * max(ah, bh)


def selection_priority(item):
    x0, y0, x1, y1 = item["box"]
    return (not item["near_internal_tile_edge"],
            item["confidence"] >= REVIEW_THRESHOLD,
            max(x1 - x0, y1 - y0), item["confidence"])


def deduplicate_candidates(items):
    retained = []
    for candidate in sorted(items, key=selection_priority, reverse=True):
        duplicate = next((item for item in retained if same_text_region(item, candidate)), None)
        if duplicate is None:
            retained.append({**candidate, "alternatives": []})
        else:
            duplicate["alternatives"].append({
                "candidate_id": candidate["candidate_id"],
                "text_raw": candidate["text_raw"], "confidence": candidate["confidence"],
                "tile": candidate["tile"], "bounding_box_pixels": candidate["box"],
                "rotation_ccw": candidate["rotation_ccw"],
                "internal_tile_edges": candidate["internal_tile_edges"],
            })
    return retained


def drawing_border_reason(box, width, height, content_bounds):
    """Exclude only boxes entirely outside the inner drawing frame."""
    left = content_bounds["x_min"] * width
    top = content_bounds["y_min"] * height
    right = content_bounds["x_max"] * width
    bottom = content_bounds["y_max"] * height
    if box["x_max"] <= left:
        return "drawing_border_left"
    if box["x_min"] >= right:
        return "drawing_border_right"
    if box["y_max"] <= top:
        return "drawing_border_top"
    if box["y_min"] >= bottom:
        return "drawing_border_bottom"
    return None


def classify_region(box, width, height, content_bounds, zones):
    if drawing_border_reason(box, width, height, content_bounds):
        return "drawing_border"
    cx = (box["x_min"] + box["x_max"]) / (2 * width)
    cy = (box["y_min"] + box["y_max"]) / (2 * height)
    # Explicit priority if manually configured zones overlap.
    for region_type in ("title_block", "equipment_data_table"):
        for zone in zones.get(region_type, []):
            if zone["x_min"] <= cx <= zone["x_max"] and zone["y_min"] <= cy <= zone["y_max"]:
                return region_type
    return "process_drawing"


def validate_layout(layout):
    for zone in [layout["DRAWING_CONTENT_BOUNDS"],
                 *(z for zones in layout["REGION_ZONES"].values() for z in zones),
                 *(r["bounds_normalized"] for r in layout["REGION_INSTANCES"])]:
        if not (0 <= zone["x_min"] < zone["x_max"] <= 1
                and 0 <= zone["y_min"] < zone["y_max"] <= 1):
            raise ValueError("Layout bounds must increase and be between 0 and 1.")


def generic_layout(border_percent=0.0, region_rows=()):
    margin = border_percent / 100
    if not 0 <= margin < 0.1:
        raise ValueError("Border width must be between 0% and 10%.")
    zones = {"equipment_data_table": [], "title_block": []}
    instances = []
    for i, row in enumerate(region_rows):
        if row["region_type"] not in zones:
            raise ValueError("Custom rectangles must be equipment tables or title blocks.")
        bounds = {key: float(row[key]) for key in ("x_min", "y_min", "x_max", "y_max")}
        zones[row["region_type"]].append(bounds)
        instances.append({"region_id": f"custom-region-{i+1}", "region_type": row["region_type"],
                          "bounds_normalized": bounds})
    layout = {"DRAWING_CONTENT_BOUNDS": dict(x_min=margin, y_min=margin, x_max=1-margin, y_max=1-margin),
              "REGION_ZONES": zones, "REGION_INSTANCES": instances}
    validate_layout(layout)
    return layout


def render_bytes(data, suffix, width=5000, page=1):
    if not data:
        raise ValueError("The uploaded file is empty.")
    if len(data) > 25 * 1024 * 1024:
        raise ValueError("The maximum file size is 25 MB.")
    if suffix.lower() not in {".svg", ".png", ".pdf"}:
        raise ValueError("Supported formats are SVG, PDF and PNG.")
    if not 1000 <= width <= 6000:
        raise ValueError("Render width must be between 1,000 and 6,000 pixels.")
    with tempfile.TemporaryDirectory(prefix="pid-render-") as directory:
        path = Path(directory) / f"source{suffix.lower()}"
        path.write_bytes(data)
        image = render_input(path, width, page)
    if image.width * image.height > 50_000_000:
        raise ValueError("Rendered page is too large. Reduce the render width.")
    return image


def classify_payload(payload, layout):
    validate_layout(layout)
    w, h = payload["image_width"], payload["image_height"]
    for d in payload["detections"]:
        d["region_type"] = classify_region(d["bounding_box"], w, h,
                                          layout["DRAWING_CONTENT_BOUNDS"], layout["REGION_ZONES"])
        d["searchable"] = d["region_type"] != "drawing_border"
        d["exclusion_reason"] = drawing_border_reason(d["bounding_box"], w, h, layout["DRAWING_CONTENT_BOUNDS"])
    payload["metadata"]["layout"] = layout
    payload["metadata"]["region_classification"] = "configured normalized rectangles; no automatic table detection"
    payload["instrument_inventory"] = build_instrument_inventory(payload)
    return payload


def run_ocr(image, *, document_id, source_name, source_sha256, page=1, layout=None,
            rotations=(0, 90, 270), tile_size=1600, overlap=320, progress=None):
    """Run once per submitted drawing; keep OCR engines local to this run."""
    width, height = image.size
    if not 0 <= overlap < tile_size or not rotations or any(r not in (0, 90, 270) for r in rotations):
        raise ValueError("Invalid tile or rotation settings.")
    engine = RapidOCR(text_score=0.0, det_limit_side_len=tile_size, det_limit_type="max",
                      intra_op_num_threads=4, inter_op_num_threads=1)
    tiles = [(x, y) for y in tile_starts(height, tile_size, overlap)
             for x in tile_starts(width, tile_size, overlap)]
    candidates = []
    started = time.perf_counter()
    completed = 0
    for tile_number, (left, top) in enumerate(tiles, 1):
        bounds = [left, top, min(left + tile_size, width), min(top + tile_size, height)]
        tile = image.crop(bounds)
        rgb = np.asarray(tile)
        for angle in rotations:
            result, _ = engine(np.rot90(rgb, k=angle // 90)[:, :, ::-1].copy())
            for polygon, text, confidence in result or []:
                if not text.strip():
                    continue
                local = unrotate_points(polygon, angle, tile.width, tile.height)
                local[:, 0] = np.clip(local[:, 0], 0, tile.width)
                local[:, 1] = np.clip(local[:, 1], 0, tile.height)
                points = local + [left, top]
                x0, y0 = np.floor(points.min(axis=0)).astype(int)
                x1, y1 = np.ceil(points.max(axis=0)).astype(int)
                if x1 <= x0 or y1 <= y0 or (angle and y1-y0 < 1.5*(x1-x0)):
                    continue
                if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                    continue
                box = [int(x0), int(y0), int(x1), int(y1)]
                edges = internal_edge_flags(box, bounds, width, height, 12)
                candidates.append(dict(candidate_id=f"candidate-{len(candidates)+1:05d}",
                    text_raw=str(text), confidence=float(confidence), box=box, polygon=points.tolist(),
                    tile=tile_number, rotation_ccw=angle, tile_bounds=bounds,
                    internal_tile_edges=edges, near_internal_tile_edge=bool(edges)))
            completed += 1
            if progress:
                progress(completed / (len(tiles)*len(rotations)),
                         f"Tile {tile_number}/{len(tiles)} · {angle}° pass")
    kept = deduplicate_candidates(candidates)
    kept.sort(key=lambda d: (d["box"][1], d["box"][0], d["text_raw"]))
    detections = []
    for i, item in enumerate(kept, 1):
        x0, y0, x1, y1 = item["box"]
        detections.append(dict(id=f"text-{i:04d}", text_raw=item["text_raw"],
            text_normalized=normalize_text(item["text_raw"]), confidence=item["confidence"],
            bounding_box=dict(x_min=x0, y_min=y0, x_max=x1, y_max=y1),
            center=dict(x=(x0+x1)/2, y=(y0+y1)/2),
            bounding_box_normalized=dict(x_min=x0/width, y_min=y0/height, x_max=x1/width, y_max=y1/height),
            center_normalized=dict(x=(x0+x1)/2/width, y=(y0+y1)/2/height), polygon=item["polygon"],
            needs_review=item["confidence"] < REVIEW_THRESHOLD or item["near_internal_tile_edge"],
            source_tile=item["tile"], source_rotation_ccw=item["rotation_ccw"],
            near_internal_tile_edge=item["near_internal_tile_edge"], internal_tile_edges=item["internal_tile_edges"],
            source_candidate_id=item["candidate_id"], overlap_alternatives=item["alternatives"]))
    payload = dict(document_id=document_id, page=page, image_width=width, image_height=height,
                   metadata=dict(source_file=source_name, source_sha256=source_sha256,
                       ocr_engine="rapidocr-onnxruntime", ocr_version=version("rapidocr-onnxruntime"),
                       tile_size=tile_size, tile_overlap=overlap, rotations_ccw=list(rotations),
                       raw_candidate_count=len(candidates), suppressed_overlap_count=len(candidates)-len(kept),
                       ocr_elapsed_seconds=time.perf_counter()-started), detections=detections)
    return classify_payload(payload, layout or generic_layout())


def annotate(image, payload):
    output = image.copy()
    draw = ImageDraw.Draw(output)
    font = ImageFont.load_default(size=16)
    for d in payload["detections"]:
        b = d["bounding_box"]
        color = "#777777" if not d["searchable"] else ("#dc6500" if d["needs_review"] else "#00865a")
        draw.rectangle((b["x_min"], b["y_min"], b["x_max"], b["y_max"]), outline=color, width=2)
        draw.text((b["x_min"], max(0, b["y_min"]-20)), d["id"].removeprefix("text-"), fill=color, font=font)
    return output
