# Industrial Engineering Knowledge Assistant

A notebook and Streamlit foundation for an assistant connecting P&ID drawings, equipment manuals, procedures, a tag register and maintenance history. The notebook also identifies and provisionally classifies tag candidates using regex and editable prefix rules.

**Current milestone:** upload a P&ID, run local OCR, normalize and classify text regions, search exact tags, and inspect all matching contextual crops. RAG, embeddings, databases and LLMs are deferred to later milestones.

## Run the Streamlit app

```bash
uv sync --locked
uv run streamlit run app.py
```

Open the local URL printed in the terminal (usually `http://localhost:8501`). Select **Reference drawing → Open prepared example** for an instant walkthrough using saved outputs, or **Run OCR** to process it again. Search for `P4711` to see both the process drawing and its equipment table. The app reports every matching OCR occurrence and preserves complete selected surrounding text in the crops.

For your own file, choose **Upload a drawing** and supply an SVG, PNG or PDF up to 25 MB. For PDFs, select one page. Set render width and optional vertical-text passes, then run OCR. Processing progress is displayed per tile/pass. The detected-text tab provides text and region filters, confidence, review flags and CSV download. The drawing tab provides full/searchable JSON, CSV and the annotated PNG. Each search can download a ZIP containing its JSON report and highlighted crops.

The reference layout is a preset for this specific P&ID. Other uploads default to **Generic / custom layout**: text is initially `process_drawing`, with no border exclusion. Configure the border strip and add normalized rectangles for individual equipment tables/title blocks when applicable. Layout classification is explicit geometry, not automatic table detection. You can process the drawing once to inspect its layout, then adjust the settings and rerun.

OCR results and search bundles live in the current Streamlit session. Searches, filters and downloads do not rerun OCR. Changing the file, PDF page or processing settings clears previous results so stale matches are not displayed. Uploaded sources are rendered using temporary files; the app does not overwrite notebook output files. Download results before ending a session if you want to keep them. SVGs must be self-contained; external file/network references are rejected.

Implementation: `app.py` provides the interface, `pid_pipeline.py` contains the notebook-derived rendering/OCR/geometry functions, `reference_layout.json` holds the reference layout, and `pid_search.py` provides exact retrieval and crop generation. The original notebook remains available for learning and experimentation.

Run `uv run python tests/check_streamlit_flow.py` for actual reference OCR through the UI test runner, a real SVG upload/search, result ZIPs, no-match and invalid-query behavior, stale-state clearing, invalid files, and PDF/PNG rendering checks. This test performs real CPU OCR and takes longer than the geometry tests.

## Run the notebook

Requirements: Python 3.11 or 3.12, [uv](https://docs.astral.sh/uv/), and the Cairo system library used by CairoSVG. On Debian/Ubuntu, Cairo is provided by `libcairo2`. The source drawing uses Calibri; if unavailable, Cairo uses a substitute font.

```bash
uv sync --locked
uv run jupyter lab notebooks/01_reference_pid_ocr.ipynb
```

Select the project's `.venv` Python interpreter if opening the notebook in VS Code, then **Run All**. The notebook finds the project from either the root directory or `notebooks/`.

To execute without opening the notebook UI:

```bash
uv run jupyter nbconvert --to notebook --execute --inplace \
  notebooks/01_reference_pid_ocr.ipynb --ExecutePreprocessor.timeout=600
```

Dependencies and OCR models are installed by `uv sync`; OCR then runs locally on CPU without API keys or a separate Tesseract installation. `uv.lock` pins the environment.

## Input and outputs

Default source: `data/p&ids/reference_pid.svg`. The first configuration cell exposes the input, document ID, one-based PDF page number, image width, tile size, overlap and review threshold. SVG, PDF and PNG input branches are included; the supplied SVG is the end-to-end demonstration.

```text
notebooks/
└── 01_reference_pid_ocr.ipynb
outputs/
├── reference_pid.png                  # Clean high-resolution rendering
├── reference_pid_ocr.json             # Text, geometry, confidence, provenance
├── reference_pid_ocr_candidates.json  # Accepted readings before overlap suppression
├── reference_pid_ocr_annotated.png    # Full-resolution boxes and detection IDs
├── reference_pid_ocr_summary.csv      # One row per retained text region
├── reference_pid_searchable.json      # OCR detections excluding drawing_border
├── reference_pid_searchable.csv       # Filtered table used by contains search
├── reference_pid_svg_text.json        # Text extracted directly from SVG XML
├── reference_pid_svg_ocr_comparison.csv
├── reference_pid_svg_ocr_comparison_summary.json
├── reference_pid_tags.json             # Candidate tags, rules and OCR provenance
└── reference_pid_tags.csv              # Classified occurrences for inspection
```

The notebook preserves the source aspect ratio at a configurable rendering width. The current width is a starting quality/runtime tradeoff, not a standard or an optimized setting. OCR runs over overlapping tiles at 0°, 90° and 270° counterclockwise. Rotated passes contribute vertical regions, with their coordinates mapped back to the original page. Rerunning replaces the generated files for the selected input type.

Overlap selection prioritizes regions away from internal tile boundaries, then readings above the review threshold, then longer text-line extent, then confidence. Compatible overlapping readings from different tiles or passes are suppressed with their alternatives retained for audit. This prevents a confident clipped fragment from replacing a complete interior reading. The ranking remains heuristic and can prefer an erroneous longer reading; inspect the saved candidates and alternatives when results disagree. True outer page boundaries are not treated as tile seams.

Long text strings remain intact, and the existing literal `contains` search is unchanged. Rotated OCR does not split regions into words or tags. Detection IDs are assigned after selection and may change between runs.

JSON retains the requested `document_id`, `page`, `image_width`, `image_height` and `detections` fields. Each detection includes `id`, `text_raw`, `text_normalized`, `confidence`, `bounding_box` and `center`. Additional fields retain the OCR polygon, normalized box and center, review flag, source tile and suppressed overlap alternatives.

- Pixel coordinates use the rendered image's top-left origin, with x right and y down.
- Normalized coordinates divide x by image width and y by image height, giving values in `[0, 1]`.
- Text normalization standardizes Unicode, dash variants and whitespace; it does not guess equipment tags or fix ambiguous characters.
- Confidence is RapidOCR's recognition score in `[0, 1]`, not a guarantee of correctness. Results below `0.80`, or touching internal tile boundaries, are orange in the annotation and flagged in the CSV; they remain in the export.
- Numeric annotation labels correspond to the suffix of `text-####` IDs.

## Verify the result

Run `uv run python tests/check_ocr_geometry.py` for regression checks on rotation mapping (including non-square tiles), internal versus page edges, complete-versus-clipped selection, rotation-pass duplicates and separate text locations.

Run `uv run python tests/check_region_classification.py` to verify all four border edges, preservation of title/table text, scale independence and classification of the same tag at different locations.

## Region types and search filtering

Every retained OCR detection and exported tag occurrence has `region_type`, one of `process_drawing`, `equipment_data_table`, `title_block`, or `drawing_border`. Assignment uses editable, normalized layout zones configured for this reference drawing. This is a manual layout configuration, not an automatic detector for arbitrary drawings.

Boxes entirely outside the configured inner frame are `drawing_border`. For remaining boxes, the center determines membership in the title block or equipment tables; anything else is `process_drawing`. Border classification takes priority, then title block, then tables. Boxes crossing a non-border zone boundary are assigned by center rather than split.

Full OCR JSON/CSV exports retain all detections, adding `region_type`, `searchable` and `exclusion_reason`. The dedicated searchable exports, notebook `contains` search, and tag identification exclude `drawing_border` only. Process drawing, equipment-table and title-block text remain searchable. The annotation shows excluded border readings in gray. SVG comparison still uses the full OCR inventory, so filtering is not counted as an OCR improvement.

The notebook validates IDs, confidence ranges, bounding boxes, coordinate normalization, JSON round-trip, CSV row count and annotated image dimensions. Open the annotation at 100% and compare against the clean render. Review low-confidence regions and sample high-confidence regions. The last section searches OCR text and displays drawing crops for matching labels; it defaults to `P4711`, a pump tag present in this source. The requested example `P-101` is not an assumed label in this drawing.

The supplied SVG is executed end to end, including coordinate validation and tag exports. Read the notebook's run summary for current region counts, review flags and runtime. These are observed OCR results, not measured recall or accuracy against a manually labeled reference. The initial single-orientation baseline had 246 regions, with 11 below the confidence threshold; rotated passes and revised overlap selection change these counts.

OCR regions may contain individual words or whole lines. Tiny labels, rotated text, line intersections and engineering symbols can cause missed or incorrect text. Overlap suppression is heuristic and retains discarded readings for audit. The outputs contain all retained detected regions, not a guarantee that every source text element was found. No symbol recognition or verified equipment linking is performed; tag classification is a provisional prefix-based interpretation.

Rendering follows [CairoSVG's documented options](https://cairosvg.org/documentation/); recognition uses [RapidOCR](https://github.com/RapidAI/RapidOCR), pinned to the `rapidocr-onnxruntime` package with bundled models.

## SVG text versus OCR

The final notebook sections independently extract embedded `<text>` content, including nested text spans, using a safe XML parser. The JSON records raw and normalized text, XML paths, element attributes and ancestor attributes. These source layout attributes are not rendered pixel bounding boxes. SVG extraction does not modify or supply answers to OCR.

The comparison pairs identical normalized strings one-to-one, counting repeated labels separately. Unmatched SVG text receives up to three character-similarity suggestions, explicitly excluded from the exact-match count. The comparison CSV contains every exact pair, unmatched SVG occurrence and unmatched OCR region.

The earlier single-orientation comparison found **245 SVG text elements, 246 OCR regions, 172 exact normalized matches (70.2% SVG text occurrence coverage), 73 unmatched SVG occurrences and 74 unmatched OCR regions**. These historical numbers do not evaluate the revised rotated pipeline. A text inventory comparison is not a spatial evaluation or a character accuracy score. OCR can merge or split source elements; repeated strings can match without establishing that their positions agree.

The extraction flags explicitly hidden text and text inside definitions, but does not expand `<use>` instances or evaluate stylesheets. The supplied drawing's 245 text elements are eligible under these rules. Other SVGs may require a renderer-aware inventory. PDF and PNG inputs skip these comparison sections; SVG comparison files from a previous run are not regenerated or deleted when those input types are selected.

## Regex tag identification and classification

Section 9 searches the OCR text for tag-shaped substrings and classifies their prefixes using an editable table. Initial examples include `P4711` as equipment/pump, `H1007` as equipment/heat exchanger, `T4750` as equipment/tank or vessel, and `PV4712.02` as instrument/pressure valve. These are demonstration assumptions requiring verification against the project's legend or tag register; valves are grouped under instruments by this initial scheme.

The pattern accepts 1–5 letters, an optional separator, a 3–6 digit identifier, an optional letter suffix and an optional one- or two-digit dotted suffix. It accepts `P-101`, `P4711` and `SV 104.01`. Known pipe-service prefixes, nozzle labels and size labels are excluded; boundary checks reject partial matches within longer identifiers. These constraints are editable and are not universal tag conventions.

Standalone instrument function labels such as `PI` and `TICSA` are exported as incomplete labels, with no invented loop number. Unrecognized prefixes remain `unknown`, including possible OCR/prose false positives. For example, merged table text `Wheel600` matches the shape but is not established as an engineering tag.

Every occurrence retains its OCR detection ID, recognition confidence and parent-region box. Duplicate tags at different locations remain separate. Classification is marked provisional and needs review; OCR confidence is not classification confidence. Canonical tag values remove prefix/number separators and uppercase letters while retaining suffixes. The original recognized text is preserved. No SVG text is used to repair missed or misread OCR tags.

Inline checks cover positive examples, unknown prefixes, repeated occurrences, incomplete labels, and exclusions such as `N1`, `DN 800`, `P3.1415` and pipe codes. The notebook displays the classified table, exports JSON/CSV, and provides category filtering with drawing crops.

## Tag search and relevant-region retrieval

**Contains is now the default**, in both the app and `retrieve_tag`. Incomplete queries search OCR text and grouped instrument tags: `PI4712` finds `PI4712.01` even when it comes from separate `PI` and `4712.01` boxes. Prefix-only and numeric-fragment queries are also accepted. Queries are literal, not user-supplied regex. Search is case-insensitive and normalizes separators between letters and numbers.

Results label partial versus whole matches and display the full recognized tag. Whole matches lead each region group; partial matches are not dropped when a whole match exists. A shorter query can refer to multiple different instruments. Select **Exact tag** in the app or pass `match_mode="exact"` to require whole-tag boundaries. Reports record `search_mode`, `match_quality`, and exact/partial match counts; grouping provenance remains separate.

Section 10 implements `exact tag → all occurrences grouped by region_type → highlighted crops → nearby OCR`. Its two code cells can run independently using the existing searchable JSON and clean PNG; OCR need not be rerun for each query. Search logic is in `pid_search.py`, ready for reuse by Streamlit. Section 6's earlier substring search is retained separately.

In exact mode, `P4711` matches an occurrence inside a longer string, but not `P47110`, `P4711A` or `P4711.02`. In contains mode, all of those longer identifiers can match. Neither mode repairs OCR errors.

Region type alone cannot distinguish adjacent equipment tables. Section 10 therefore configures five individual table rectangles and a title-block rectangle, each with a `region_id`. The matching box's center selects its containing region. The table rectangles are specified by layout, not by hardcoded tag identity. A process-drawing match starts with a seed window padded by 5% of page width/height around the matching OCR box. It selects same-region OCR boxes that intersect that window, then expands the crop to include their complete bounds with an 8-pixel margin. This prevents the original window from clipping selected surrounding labels. An unconfigured table location explicitly falls back to this local-window method.

Expansion happens once; newly visible labels do not recursively expand the crop. The JSON records the initial `region_bounds`, final `crop_bounds`, selection method and expansion method. Undetected text or incidental labels entering the expanded image can still be cut. Configured tables retain center-based context selection to avoid pulling in neighboring tables, while their selected boxes are also included in full.

Each result includes the selection method, region ID and bounds, match coordinates, confidence, and nearby OCR from the same region type. Table context is restricted to the selected table. Geometric proximity is not proof of equipment ownership, pipe connectivity or semantic relevance. Region bounds must be reviewed for another drawing; this is not automatic table detection.

For `P4711`, results include the pump location and the lower-left specification table. Crops outline the matched OCR region in red and nearby text in blue. If a long OCR string includes several tags, the whole OCR region is highlighted because substring pixel coordinates are unavailable; text remains intact.

```text
outputs/search/P4711/
├── search_results.json
├── process_drawing_text-....png
└── equipment_data_table_text-....png
```

The JSON is the authoritative manifest of crops for that query run. Repeated searches replace that report and its current crop files; old unreferenced crop files can remain if detection IDs change. No-match searches write an empty grouped result and do not imply the equipment is absent from the source.

Run `uv run python tests/check_exact_search.py` to check exact-match boundaries, region grouping, separation of neighboring tables, fallback windows, repeated matches, excluded borders and crop geometry.

Run `uv run python tests/check_partial_search.py` for the `PI4712` → `PI4712.01` regression, grouped-tag partial matching, exact-first ordering and app mode switching without rerunning OCR. In the notebook, use `TAG_QUERY` and `SEARCH_MODE` in section 10.

## Grouped instrument tags

`pid_instruments.py` builds a provisional inventory before search. It collects complete instrument tags and groups standalone prefix/identifier OCR boxes that are close and aligned. Supported arrangements are a number directly below the prefix or immediately to its right on the same line. Geometry scales with text height; suffix letters and dotted identifiers are retained, for example `PT` + `133035` → `PT133035`, `HZ` + `133065C` → `HZ133065C`, and `PI` + `4712.01` → `PI4712.01`.

The editable `INSTRUMENT_PREFIXES` set defines eligible instrument prefixes. Grouping is limited to process-drawing regions on the same page. Complete tags from other searchable region types remain eligible for the inventory. Unknown or misread prefixes and reversed/distant layouts may be missed; symbol circles are not detected.

Every occurrence retains original OCR IDs, texts, individual boxes, combined bounds, source confidences and grouping geometry. Original OCR detections are not merged or overwritten. The minimum source OCR confidence is reported, not a fabricated grouping confidence. All candidates need review. Competing partners remain visible with `ambiguous=True`, including cases where different prefixes share a nearby number.

The Streamlit **Instrument list** tab shows one row per canonical tag, with all drawing occurrences and downloadable JSON/CSV. Exact search searches both original text and grouped tags, even when a complete occurrence already exists elsewhere. Grouped results explain the match and highlight both contributing boxes. Nearby context excludes the matched fragments themselves.

Notebook section 11 generates `outputs/reference_pid_instrument_inventory.json` and `outputs/reference_pid_instrument_list.csv`. The full app OCR download includes the derived `instrument_inventory` alongside unchanged detection text.

Tests: `uv run python tests/check_instrument_grouping.py` covers complete/split tags, suffixes, proximity and alignment, scale invariance, ambiguity, cross-region/page exclusions and highlights. `uv run python tests/check_grouping_app.py` verifies the app's list and split-tag search using synthetic OCR boxes. The uploaded example in the conversation is not a ground-truth evaluation dataset; grouping must still be reviewed on actual drawings.

## FastAPI ingestion and retrieval backend

The local backend ingests the `DATA/true_data` and `DATA/noisy_data` corpus, saves chunk JSON under `processed_data/`, embeds each chunk with FastEmbed, and indexes vectors plus source metadata in Qdrant. By default it uses Qdrant local mode persisted under `outputs/qdrant/`; setting `QDRANT_CLUSTER_ENDPOINT` and `QDRANT_API_KEY` connects it to a remote Qdrant cluster.

Start the API from the project root:

```bash
uv sync --locked
uv run uvicorn backend.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive API. Main routes:

- `POST /ingest` — ingest the corpus; JSON body `{"include_noisy": true}` controls whether evaluation distractors are included.
- `POST /ingest/file?relative_path=true_data/area_47_reference_pid.svg` — process one file under `DATA/`.
- `GET /documents` and `GET /health` — inspect indexed documents and counts.
- `POST /search` — semantic vector retrieval; body includes `query`, optional `source_type` (`true_data` or `noisy_data`) and `limit`.
- `POST /query` — return matching source excerpts with filenames and chunk numbers.

Text, Markdown, HTML, CSV/TSV, JSON, SVG, PDF, common raster images, DOCX and PPTX are supported. SVG and raster P&IDs run through the existing tiled RapidOCR pipeline; PDFs use embedded text extraction and OCR for scanned pages and drawing pages. Image-only PDFs and raster images use the project's local OCR pipeline. The default embedding model is `BAAI/bge-small-en-v1.5` (downloads model weights on first use). Configure `EMBEDDING_MODEL`, `QDRANT_COLLECTION`, and optionally `QDRANT_CLUSTER_ENDPOINT` / `QDRANT_API_KEY`; set `QDRANT_PATH`, `INDUSTRIAL_RAG_DATA_DIR`, or `INDUSTRIAL_RAG_PROCESSED_DIR` to override local storage paths.

This is an ingestion and vector-retrieval foundation, not yet an LLM agent: `/query` returns retrieved evidence excerpts and does not generate an answer with an LLM or keep chat memory. Treat all sample corpus content as training data and consult current approved plant procedures for operational decisions.

## Agentic RAG chat workspace

The existing Streamlit app now has a **Workspace** selector in the sidebar. Choose **Agentic RAG chat** to chat with the FastAPI agent; choose **P&ID OCR** to return to drawing tools. The chat displays agent steps and retrieved context, includes sample industrial questions, and can start a fresh thread.

Start the API in one terminal from the project root:

```bash
uv run uvicorn app.main:app --reload
```

Start the Streamlit app in a second terminal:

```bash
uv run streamlit run app.py
```

Before asking questions, ingest the sample corpus if it is not already indexed:

```bash
uv run python -m app.ingestion.processor DATA/true_data
```

Open the Streamlit URL printed in the terminal, usually `http://localhost:8501`. In the chat workspace, the FastAPI URL defaults to `http://127.0.0.1:8000`. The sample documents are synthetic training data, not approved plant operating or maintenance procedures.
