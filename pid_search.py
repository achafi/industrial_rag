"""Deterministic tag-to-region retrieval; no embeddings or LLM required."""
from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw
from pid_instruments import IDENTIFIER, build_instrument_inventory


def normalize_query(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip().upper()
    value = value.translate(str.maketrans({c: "-" for c in "‐‑‒–—−"}))
    return re.sub(r"\s*-\s*", "-", re.sub(r"\s+", " ", value))


def exact_tag_pattern(query: str) -> re.Pattern:
    """Match a whole identifier inside an OCR region, never a partial tag."""
    query = normalize_query(query)
    if not query or not re.fullmatch(r"[A-Z0-9][A-Z0-9 ./-]*", query) or not re.search(r"\d", query):
        raise ValueError("Enter a complete tag containing a number, for example P4711 or PV4712.02.")
    parts = re.fullmatch(r"([A-Z]{1,5})[- ]?(" + IDENTIFIER + r")", query)
    if parts:
        body = re.escape(parts[1]) + r"(?:\s*-\s*|\s*)" + re.escape(parts[2])
    else:
        body = re.escape(query)
    return re.compile(r"(?<![\w./-])" + body + r"(?![\w./-])", re.IGNORECASE)


def contains_tag_pattern(query: str) -> re.Pattern:
    """Literal partial search, including shorter prefixes and numeric fragments."""
    query = normalize_query(query)
    if not query or not re.fullmatch(r"[A-Z0-9][A-Z0-9 ./-]*", query):
        raise ValueError("Enter a tag or text fragment, for example PI4712, PT or 133035.")
    parts = re.fullmatch(r"([A-Z]{1,5})[- ]?(\d{1,8}[A-Z]?(?:\.\d{0,3}[A-Z]?)?)", query)
    body = (re.escape(parts[1]) + r"(?:\s*-\s*|\s*)" + re.escape(parts[2])) if parts else re.escape(query)
    return re.compile(body, re.IGNORECASE)


def pixel_box(zone: dict, width: int, height: int) -> dict:
    return {
        "x_min": max(0, math.floor(zone["x_min"] * width)),
        "y_min": max(0, math.floor(zone["y_min"] * height)),
        "x_max": min(width, math.ceil(zone["x_max"] * width)),
        "y_max": min(height, math.ceil(zone["y_max"] * height)),
    }


def center_inside(detection: dict, box: dict) -> bool:
    b = detection["bounding_box"]
    x, y = (b["x_min"] + b["x_max"]) / 2, (b["y_min"] + b["y_max"]) / 2
    return box["x_min"] <= x <= box["x_max"] and box["y_min"] <= y <= box["y_max"]


def boxes_intersect(a: dict, b: dict) -> bool:
    """Positive-area intersection; mere edge contact does not select text."""
    return (max(a["x_min"], b["x_min"]) < min(a["x_max"], b["x_max"])
            and max(a["y_min"], b["y_min"]) < min(a["y_max"], b["y_max"]))


def retrieve_tag(payload: dict, query: str, region_instances: list[dict],
                 padding_x: float = 0.05, padding_y: float = 0.05, *, match_mode: str = "contains") -> dict:
    """Return every matching OCR occurrence grouped by region_type.

    Tables/title blocks use configured region instances. Process locations and
    unconfigured table locations use local seed windows. Crops expand once to
    contain the full boxes of selected text; context selection never cascades.
    Nearby text is geometric context, not confirmed equipment attribution.
    """
    if not 0 < padding_x <= 1 or not 0 < padding_y <= 1:
        raise ValueError("Context padding must be in (0, 1].")
    if match_mode not in {"contains", "exact"}:
        raise ValueError("match_mode must be contains or exact.")
    pattern = contains_tag_pattern(query) if match_mode == "contains" else exact_tag_pattern(query)
    boundary_pattern = re.compile(r"(?<![\w./-])(?:" + pattern.pattern + r")(?![\w./-])", re.IGNORECASE)
    width, height = payload["image_width"], payload["image_height"]
    regions = []
    for region in region_instances:
        z = region["bounds_normalized"]
        if not (0 <= z["x_min"] < z["x_max"] <= 1 and 0 <= z["y_min"] < z["y_max"] <= 1):
            raise ValueError(f"Invalid region bounds: {region['region_id']}")
        regions.append({**region, "box": pixel_box(z, width, height)})
    eligible = [d for d in payload["detections"]
                if d.get("searchable", True) and d["region_type"] != "drawing_border"]
    inventory = build_instrument_inventory(payload)
    reconstructed = [dict(id=o['id'], text_raw=o['canonical_tag'], confidence=o['ocr_confidence'],
                           bounding_box=o['bounding_box'], region_type=o['region_type'], instrument_group=o)
                     for o in inventory['occurrences'] if o['match_method'] == 'spatially_grouped']
    grouped: dict[str, list] = {}
    for detection in [*eligible, *reconstructed]:
        text = normalize_query(detection["text_raw"])
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        exact_spans = {m.span() for m in boundary_pattern.finditer(text)}
        exact_count = sum(m.span() in exact_spans for m in matches)
        instrument_group = detection.get('instrument_group')
        source_ids = instrument_group['source_detection_ids'] if instrument_group else [detection['id']]
        source_boxes = instrument_group['source_boxes'] if instrument_group else [detection['bounding_box']]
        region_type = detection["region_type"]
        containing = [r for r in regions if r["region_type"] == region_type
                      and center_inside(detection, r["box"])]
        # If configured boxes overlap, prefer the most specific (smallest) one.
        region = min(containing, key=lambda r: (r["box"]["x_max"] - r["box"]["x_min"])
                     * (r["box"]["y_max"] - r["box"]["y_min"]), default=None)
        b = detection["bounding_box"]
        if region is not None:
            box = dict(region["box"])
            region_id = region["region_id"]
            method = "configured_region_instance"
        else:
            box = {"x_min": max(0, math.floor(b["x_min"] - padding_x * width)),
                   "y_min": max(0, math.floor(b["y_min"] - padding_y * height)),
                   "x_max": min(width, math.ceil(b["x_max"] + padding_x * width)),
                   "y_max": min(height, math.ceil(b["y_max"] + padding_y * height))}
            region_id = f"local-{detection['id']}"
            method = "local_spatial_window"
        nearby = [d for d in eligible if d["id"] not in source_ids
                  and d["region_type"] == region_type
                  and (center_inside(d, box) if region is not None
                       else boxes_intersect(d["bounding_box"], box))]
        # Select from the original window only, then expand once. Otherwise one
        # long pipe label could pull in another, eventually selecting the page.
        selected_boxes = [box, b, *(d["bounding_box"] for d in nearby)]
        crop = {
            "x_min": max(0, min(q["x_min"] for q in selected_boxes) - 8),
            "y_min": max(0, min(q["y_min"] for q in selected_boxes) - 8),
            "x_max": min(width, max(q["x_max"] for q in selected_boxes) + 8),
            "y_max": min(height, max(q["y_max"] for q in selected_boxes) + 8),
        }
        nearby.sort(key=lambda d: (d["bounding_box"]["y_min"], d["bounding_box"]["x_min"]))
        grouped.setdefault(region_type, []).append({
            "source_detection_id": source_ids[0], "match_id": detection["id"], "region_type": region_type,
            "source_detection_ids": source_ids, "source_boxes": source_boxes,
            "match_method": "spatially_grouped" if instrument_group else "complete_ocr_tag",
            "grouping_evidence": instrument_group,
            "ambiguous": bool(instrument_group and instrument_group['ambiguous']),
            "region_id": region_id, "region_selection_method": method,
            "region_bounds": box, "crop_bounds": crop,
            "context_selection_method": "center_in_configured_region" if region is not None else "intersection_with_initial_window",
            "crop_expansion_method": "single_pass_union_of_selected_ocr_boxes_with_8px_margin",
            "matched_text": detection["text_raw"],
            "match_quality": "exact" if exact_count == len(matches) else ("partial" if exact_count == 0 else "mixed"),
            "exact_match_count": exact_count, "partial_match_count": len(matches) - exact_count,
            "match_spans_normalized_text": [list(m.span()) for m in matches],
            "matches_in_region": len(matches), "ocr_confidence": detection["confidence"],
            "bounding_box": b, "highlight_scope": "source_ocr_boxes" if instrument_group else "parent_ocr_region",
            "nearby_ocr": [{"id": d["id"], "text_raw": d["text_raw"],
                            "confidence": d["confidence"], "bounding_box": d["bounding_box"],
                            "region_type": d["region_type"]} for d in nearby],
            "context_text": "\n".join(d["text_raw"] for d in nearby),
        })
    # Whole-tag matches lead each region group, without dropping partial matches.
    for items in grouped.values():
        items.sort(key=lambda item: (item["match_quality"] != "exact", item["bounding_box"]["y_min"], item["bounding_box"]["x_min"]))
    return {
        "query": query, "query_normalized": normalize_query(query),
        "document_id": payload["document_id"], "page": payload["page"],
        "source_sha256": payload.get("metadata", {}).get("source_sha256"),
        "image_width": width, "image_height": height,
        "search_mode": match_mode,
        "match_method": f"{match_mode} search over OCR and spatially grouped tags; case-insensitive, optional prefix-number separator",
        "occurrence_count": sum(len(items) for items in grouped.values()),
        "tag_match_count": sum(item["matches_in_region"] for items in grouped.values() for item in items),
        "region_instances": region_instances,
        "context_padding_normalized": {"x": padding_x, "y": padding_y},
        "groups": grouped,
        "limitations": ["No match means no OCR/grouped-tag match in the selected mode, not confirmed equipment absence.",
                        "Partial matches can refer to different instruments; inspect the full matched text.",
                        "Nearby OCR is spatial context, not verified equipment ownership or connectivity.",
                        "Highlights cover OCR regions; substring pixel bounds are unavailable.",
                        "Crop expansion preserves selected OCR boxes, not undetected text or every incidental label entering the expanded image.",
                        "Configured table/title regions are specific to this drawing."],
    }


def save_search_results(result: dict, image: Image.Image, output_dir: Path) -> Path:
    if image.size != (result["image_width"], result["image_height"]):
        raise ValueError("Image dimensions differ from the OCR coordinate system.")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for items in result["groups"].values():
        for item in items:
            b = item["crop_bounds"]
            crop = image.crop((b["x_min"], b["y_min"], b["x_max"], b["y_max"])).convert("RGB")
            draw = ImageDraw.Draw(crop)
            # Blue: nearby OCR; red: the matched OCR region.
            for nearby in item["nearby_ocr"]:
                q = nearby["bounding_box"]
                draw.rectangle((q["x_min"] - b["x_min"], q["y_min"] - b["y_min"],
                                q["x_max"] - b["x_min"], q["y_max"] - b["y_min"]), outline="#2675b8", width=2)
            for q in item.get("source_boxes", [item["bounding_box"]]):
                draw.rectangle((q["x_min"] - b["x_min"], q["y_min"] - b["y_min"],
                                q["x_max"] - b["x_min"], q["y_max"] - b["y_min"]), outline="#d62828", width=4)
            filename = re.sub(r"[^A-Za-z0-9_-]", "_", f"{item['region_type']}_{item.get('match_id', item['source_detection_id'])}") + ".png"
            crop.save(output_dir / filename)
            item["crop_file"] = filename
    path = output_dir / "search_results.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return path
