"""Build a provisional instrument inventory without changing raw OCR detections."""
from collections import Counter, defaultdict
import re
import unicodedata

INSTRUMENT_PREFIXES = frozenset({
    "PT", "PI", "PIT", "PIC", "PICSA", "PS", "PSH", "PSL", "PDI", "PDT", "PDIC",
    "TT", "TI", "TIT", "TIC", "TICSA", "TS", "TSH", "TSL",
    "FT", "FI", "FIT", "FIC", "FS", "FSL", "FSH",
    "LT", "LI", "LIT", "LIC", "LS", "LSH", "LSL",
    "AT", "AI", "AIT", "AIC", "HS", "HZ", "MS", "ZS", "ZT", "ZI", "XV", "PV", "TV", "SV",
})
IDENTIFIER = r"\d{3,8}[A-Z]?(?:\.\d{1,3}[A-Z]?)?"
NUMBER_PATTERN = re.compile(IDENTIFIER)
GROUPING_VERSION = 1


def normalized(text):
    text = unicodedata.normalize("NFKC", text).upper().strip()
    return re.sub(r"\s+", " ", text.translate(str.maketrans({c: "-" for c in "‐‑‒–—−"})))


def union_boxes(boxes):
    return {"x_min": min(b["x_min"] for b in boxes), "y_min": min(b["y_min"] for b in boxes),
            "x_max": max(b["x_max"] for b in boxes), "y_max": max(b["y_max"] for b in boxes)}


def pairing_geometry(prefix, number):
    """Use local text size, not a fixed pixel radius; no symbol/circle inference."""
    p, n = prefix["bounding_box"], number["bounding_box"]
    ph, nh = p["y_max"]-p["y_min"], n["y_max"]-n["y_min"]
    if min(ph, nh) <= 0 or max(ph, nh) / min(ph, nh) > 2.5:
        return None
    scale = max(ph, nh)
    px, py = (p["x_min"]+p["x_max"])/2, (p["y_min"]+p["y_max"])/2
    nx, ny = (n["x_min"]+n["x_max"])/2, (n["y_min"]+n["y_max"])/2
    gap = n["y_min"] - p["y_max"]
    horizontal_overlap = min(p["x_max"], n["x_max"]) - max(p["x_min"], n["x_min"])
    if ny > py and -0.2*scale <= gap <= 1.25*scale and abs(px-nx) <= 0.8*scale and horizontal_overlap > 0:
        return {"arrangement": "number_below_prefix", "gap_in_text_heights": round(gap/scale, 4),
                "alignment_offset_in_text_heights": round(abs(px-nx)/scale, 4)}
    gap = n["x_min"]-p["x_max"]
    if nx > px and 0 <= gap <= 1.25*scale and abs(py-ny) <= 0.4*scale:
        return {"arrangement": "number_right_of_prefix", "gap_in_text_heights": round(gap/scale, 4),
                "alignment_offset_in_text_heights": round(abs(py-ny)/scale, 4)}
    return None


def build_instrument_inventory(payload, prefixes=INSTRUMENT_PREFIXES):
    prefixes = frozenset(normalized(p) for p in prefixes)
    alternatives = "|".join(re.escape(p) for p in sorted(prefixes, key=lambda s: (-len(s), s)))
    full_pattern = re.compile(r"(?<![\w./-])(?P<prefix>"+alternatives+r")(?:\s*-\s*|\s*)(?P<number>"+IDENTIFIER+r")(?![\w./-])")
    eligible = [d for d in payload["detections"] if d.get("searchable", True) and d["region_type"] != "drawing_border"]
    occurrences, prefix_boxes, number_boxes = [], [], []

    def occurrence(parts, prefix, number, method, evidence=None, span=None):
        return {"id": "instrument-occurrence-"+str(len(occurrences)+1).zfill(4),
                "canonical_tag": prefix+number, "prefix": prefix, "identifier": number,
                "category": "instrument", "region_type": parts[0]["region_type"],
                "document_id": payload.get("document_id"), "page": payload.get("page", 1),
                "source_detection_ids": [d["id"] for d in parts],
                "source_texts": [d["text_raw"] for d in parts],
                "source_boxes": [dict(d["bounding_box"]) for d in parts],
                "bounding_box": union_boxes([d["bounding_box"] for d in parts]),
                "ocr_confidence": min(d["confidence"] for d in parts),
                "source_confidences": [d["confidence"] for d in parts],
                "match_method": method, "geometry_evidence": evidence,
                "match_span_normalized_text": span,
                "classification_status": "provisional", "ambiguous": False, "needs_review": True}

    for d in eligible:
        text = normalized(d["text_raw"])
        for match in full_pattern.finditer(text):
            occurrences.append(occurrence([d], match['prefix'], match['number'], 'complete_ocr_tag', span=list(match.span())))
        # Reconstruct only process labels. Tables/title blocks have different layouts.
        if d["region_type"] != "process_drawing":
            continue
        if text in prefixes:
            prefix_boxes.append(d)
        elif NUMBER_PATTERN.fullmatch(text):
            number_boxes.append(d)

    pairs = []
    for p in prefix_boxes:
        for n in number_boxes:
            if p.get("page", payload.get("page", 1)) != n.get("page", payload.get("page", 1)):
                continue
            evidence = pairing_geometry(p, n)
            if evidence:
                pairs.append((p, n, evidence))
    prefix_counts = Counter(p['id'] for p, _, _ in pairs)
    number_counts = Counter(n['id'] for _, n, _ in pairs)
    for p, n, evidence in pairs:
        item = occurrence([p, n], normalized(p['text_raw']), normalized(n['text_raw']), 'spatially_grouped', evidence)
        item['ambiguous'] = prefix_counts[p['id']] > 1 or number_counts[n['id']] > 1
        item['competing_pair_count'] = max(prefix_counts[p['id']], number_counts[n['id']]) - 1
        occurrences.append(item)
    grouped = defaultdict(list)
    for item in occurrences:
        grouped[item['canonical_tag']].append(item)
    instruments = [{"canonical_tag": tag, "prefix": items[0]['prefix'], "category": "instrument",
                    "occurrence_count": len(items), "occurrence_ids": [i['id'] for i in items],
                    "region_types": sorted({i['region_type'] for i in items}),
                    "has_grouped_occurrences": any(i['match_method']=='spatially_grouped' for i in items),
                    "ambiguous": any(i['ambiguous'] for i in items), "needs_review": True}
                   for tag, items in sorted(grouped.items())]
    return {"grouping_version": GROUPING_VERSION, "document_id": payload.get('document_id'),
            "page": payload.get('page', 1), "prefixes": sorted(prefixes),
            "method": "complete tags plus local aligned prefix/identifier pairs in process_drawing",
            "confidence_note": "OCR confidence is the minimum source score, not grouping probability.",
            "instruments": instruments, "occurrences": occurrences,
            "unpaired_prefix_detection_ids": [p['id'] for p in prefix_boxes if not prefix_counts[p['id']]],
            "limitations": ["Prefix conventions and grouping are provisional; no symbol boundary detection.",
                            "Competing geometric pairs remain visible and flagged ambiguous.",
                            "Unknown prefixes, misread text, reversed or distant layouts may be missed."]}
