"""Streamlit entry point: uv run streamlit run app.py."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import zipfile
import uuid
import time

import requests

import pandas as pd
from PIL import Image
import streamlit as st

from pid_pipeline import (REFERENCE_LAYOUT, annotate, classify_payload, generic_layout,
                          render_bytes, run_ocr)
from pid_search import retrieve_tag, save_search_results
from pid_instruments import build_instrument_inventory
from app.config import EMBEDDING_MODEL, settings

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "data/p&ids/reference_pid.svg"
st.set_page_config(page_title="Industrial Engineering Knowledge Assistant", page_icon="⚙", layout="wide")
st.markdown("""<style>
.block-container {max-width: 1450px; padding-top: 4rem;}
.eyebrow {color: #164a70 !important; font-weight: 800; letter-spacing: .04em; font-size: 1.15rem; line-height: 1.5; margin: 0 0 .45rem 0; display: block;}
.flow {padding: 1rem 1.2rem; background: #edf4fa; border-left: 4px solid #2675b8;
       border-radius: 4px; margin-bottom: 1.5rem; color: #294057;}
[data-testid="stMetric"] {background: #f4f7fb; padding: 1rem; border-radius: 8px;}
</style>""", unsafe_allow_html=True)


def png_bytes(image):
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def text_table(payload):
    rows = []
    for d in payload["detections"]:
        rows.append({"id": d["id"], "text": d["text_raw"], "text_normalized": d["text_normalized"],
                     "region_type": d["region_type"], "confidence": d["confidence"],
                     "searchable": d["searchable"], "needs_review": d["needs_review"],
                     "exclusion_reason": d.get("exclusion_reason"),
                     "document_id": payload["document_id"], "page": payload["page"],
                     "image_width": payload["image_width"], "image_height": payload["image_height"],
                     **d["bounding_box"],
                     **{f"{k}_normalized": v for k,v in d["bounding_box_normalized"].items()}})
    return pd.DataFrame(rows, columns=["id", "text", "text_normalized", "region_type", "confidence",
                        "searchable", "needs_review", "exclusion_reason", "document_id", "page",
                        "image_width", "image_height", "x_min", "y_min", "x_max", "y_max",
                        "x_min_normalized", "y_min_normalized", "x_max_normalized", "y_max_normalized"])


def bundle_search(payload, image, query, layout, match_mode="contains"):
    result = retrieve_tag(payload, query, layout["REGION_INSTANCES"], match_mode=match_mode)
    with tempfile.TemporaryDirectory(prefix="pid-search-") as directory:
        folder = Path(directory)
        save_search_results(result, image, folder)
        crops = {p.name: p.read_bytes() for p in folder.glob("*.png")}
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(folder.iterdir()):
                z.writestr(p.name, p.read_bytes())
    return {"report": result, "crops": crops, "zip": archive.getvalue()}


def render_rag_chat(api_url: str) -> None:
    """Render the agentic RAG chat against the FastAPI /query endpoint."""
    if "chat_thread_id" not in st.session_state:
        st.session_state.chat_thread_id = str(uuid.uuid4())
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    st.markdown('<div class="eyebrow">INDUSTRIAL ENGINEERING KNOWLEDGE ASSISTANT</div>', unsafe_allow_html=True)
    st.title("Ask the plant documents")
    st.write("Ask about equipment tags, P&IDs, maintenance, abnormal conditions, or company policies.")
    st.caption("Sample corpus is synthetic training material. It is not an approved operating or maintenance procedure.")
    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"], avatar="🤖" if message["role"] == "assistant" else "👤"):
            st.markdown(message["content"])
            if message.get("steps"):
                with st.expander("Agent steps"):
                    for step in message["steps"]:
                        st.write(f"⚙️ {step}")
            if message.get("sources"):
                with st.expander(f"Retrieved context ({len(message['sources'])} chunks)"):
                    for index, source in enumerate(message["sources"], start=1):
                        if isinstance(source, dict):
                            source_text = source.get("content") or source.get("text") or str(source)
                            source_name = source.get("source")
                        else:
                            source_text, source_name = str(source), None
                        st.caption(f"Chunk {index}" + (f" · {source_name}" if source_name else ""))
                        st.info(source_text)

    prompt = st.chat_input("Ask about your plant documents…")
    if not prompt:
        return

    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🤖"):
        with st.status("🔍 Searching the plant knowledge base…", expanded=True) as status:
            started_at = time.perf_counter()
            try:
                response = requests.post(
                    f"{api_url.rstrip('/')}/query",
                    json={"q": prompt, "thread_id": st.session_state.chat_thread_id},
                    timeout=180,
                )
                response.raise_for_status()
                data = response.json()
                steps = data.get("thought_process") or []
                sources = data.get("sources") or []
                answer = data.get("answer") or "The assistant returned no answer."
                elapsed_seconds = time.perf_counter() - started_at
                for step in steps:
                    st.write(f"⚙️ {step}")
                if data.get("status") == "error":
                    status.update(label="⚠️ The backend reported an error", state="error", expanded=True)
                else:
                    status.update(
                        label=f"✅ Answer ready · {elapsed_seconds:.2f}s",
                        state="complete",
                        expanded=False,
                    )
            except requests.RequestException as exc:
                answer = f"Could not reach the RAG backend at `{api_url}`. Check that FastAPI is running.\n\nDetails: {exc}"
                steps, sources = [], []
                status.update(label="❌ Backend connection failed", state="error", expanded=True)
            except (ValueError, KeyError) as exc:
                answer = f"The backend returned an invalid response: {exc}"
                steps, sources = [], []
                status.update(label="❌ Invalid backend response", state="error", expanded=True)

        st.markdown(answer)
        if sources:
            with st.expander(f"Retrieved context ({len(sources)} chunks)"):
                for index, source in enumerate(sources, start=1):
                    if isinstance(source, dict):
                        source_text = source.get("content") or source.get("text") or str(source)
                        source_name = source.get("source")
                    else:
                        source_text, source_name = str(source), None
                    st.caption(f"Chunk {index}" + (f" · {source_name}" if source_name else ""))
                    st.info(source_text)

    st.session_state.chat_messages.append({
        "role": "assistant", "content": answer, "steps": steps, "sources": sources,
    })

with st.sidebar:
    workspace = st.radio("Workspace", ["P&ID OCR", "Agentic RAG chat"], key="workspace")
    if workspace == "Agentic RAG chat":
        st.markdown("### Industrial RAG chat")
        api_url = st.text_input("FastAPI URL", value="http://127.0.0.1:8000", key="rag_api_url")
        with st.expander("Models in use", expanded=True):
            st.text_input("NeMo guardrails model (Groq)", value=settings.GROQ_MODEL, disabled=True)
            st.text_input("Planner and answer model (Groq)", value=settings.GROQ_MODEL, disabled=True)
            st.text_input("Embedding model (FastEmbed)", value=EMBEDDING_MODEL, disabled=True)
        if "chat_thread_id" not in st.session_state:
            st.session_state.chat_thread_id = str(uuid.uuid4())
        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = []
        st.caption(f"Thread memory: {st.session_state.chat_thread_id[:8]}")
        if st.button("Clear chat and start new thread", width="stretch", type="primary"):
            st.session_state.chat_messages = []
            st.session_state.chat_thread_id = str(uuid.uuid4())
            st.rerun()
        st.caption("Start FastAPI separately. The chat posts to its /query endpoint.")
    else:
        st.markdown("### Drawing workspace")
        source = st.radio("Drawing source", ["Reference drawing", "Upload a drawing"], key="source")
        uploaded = st.file_uploader("P&ID file", type=["svg", "pdf", "png"], key="drawing_upload") if source == "Upload a drawing" else None
        if source == "Reference drawing":
            data, filename = REFERENCE.read_bytes(), REFERENCE.name
        elif uploaded is not None:
            data, filename = uploaded.getvalue(), Path(uploaded.name).name
        else:
            data, filename = None, ""
        page = int(st.number_input("PDF page", min_value=1, value=1, step=1)) if filename.lower().endswith(".pdf") else 1
        width = st.select_slider("Render width (pixels)", [2000, 3000, 4000, 5000, 6000], value=5000)
        rotations = st.checkbox("Include vertical-text passes", value=True,
                                help="Adds 90° and 270° OCR passes. Processing takes longer.")
        options = ["Reference layout", "Generic / custom layout"] if source == "Reference drawing" else ["Generic / custom layout", "Reference layout"]
        layout_choice = st.selectbox("Region layout", options, key=f"layout_{source}")
        layout_error = None
        if layout_choice == "Reference layout":
            layout = deepcopy(REFERENCE_LAYOUT)
            st.caption("Five equipment tables, title block and border configured for the supplied reference drawing.")
        else:
            st.caption("Text defaults to process_drawing. Define other regions below; they are not detected automatically.")
            border = st.number_input("Outer border strip (%)", min_value=0.0, max_value=5.0, value=0.0, step=0.5)
            with st.expander("Define tables and title block"):
                st.caption("Coordinates are fractions of the page (0–1), measured from the top-left. Add one row per table.")
                custom = st.data_editor(pd.DataFrame(columns=["region_type", "x_min", "y_min", "x_max", "y_max"]),
                    num_rows="dynamic", hide_index=True, key="region_editor",
                    column_config={"region_type": st.column_config.SelectboxColumn(options=["equipment_data_table", "title_block"], required=True),
                                   **{k: st.column_config.NumberColumn(min_value=0.0, max_value=1.0, step=0.01, required=True)
                                      for k in ("x_min", "y_min", "x_max", "y_max")}})
            try:
                layout = generic_layout(border, custom.to_dict("records"))
            except (ValueError, TypeError, KeyError) as exc:
                layout, layout_error = generic_layout(), str(exc)
                st.error(f"Check the region rectangles: {exc}")
        run_pressed = st.button("Run OCR", type="primary", width="stretch",
                                disabled=data is None or layout_error is not None, key="run_ocr")
        prepared_available = (ROOT / "outputs/reference_pid_ocr.json").exists() and (ROOT / "outputs/reference_pid.png").exists()
        use_prepared = False
        if source == "Reference drawing" and prepared_available and width == 5000 and rotations and layout_choice == "Reference layout":
            use_prepared = st.button("Open prepared example", width="stretch", key="prepared")
            st.caption("Loads the saved reference OCR result instantly.")
        st.divider()
        st.caption("Local OCR · No API key needed\n\nSearches use OCR text and geometry. Engineering relationships are not inferred.")

if workspace == "Agentic RAG chat":
    render_rag_chat(api_url)
    st.stop()

st.markdown('<div class="eyebrow">INDUSTRIAL ENGINEERING KNOWLEDGE ASSISTANT</div>', unsafe_allow_html=True)
st.title("Find it on the drawing.")
st.write("Turn a P&ID into searchable text, locate every tag occurrence, and inspect the surrounding evidence.")
st.markdown('<div class="flow">Upload a drawing → Run OCR → Review regions → Search a tag → Inspect context</div>', unsafe_allow_html=True)

fingerprint = hashlib.sha256((data or b"") + json.dumps([filename, page, width, rotations, layout, layout_error], sort_keys=True).encode()).hexdigest()
if st.session_state.get("source_fingerprint") != fingerprint:
    for key in ("processed", "search_bundle"):
        st.session_state.pop(key, None)
    st.session_state.source_fingerprint = fingerprint

if run_pressed or use_prepared:
    st.session_state.pop("processed", None)
    st.session_state.pop("search_bundle", None)
    try:
        with st.status("Processing drawing…", expanded=True) as status:
            source_hash = hashlib.sha256(data).hexdigest()
            if use_prepared:
                payload = json.loads((ROOT / "outputs/reference_pid_ocr.json").read_text())
                if payload["metadata"]["source_sha256"] != source_hash:
                    raise ValueError("The prepared result does not match this source. Use Run OCR.")
                with Image.open(ROOT / "outputs/reference_pid.png") as loaded:
                    image = loaded.convert("RGB")
                if image.size != (payload["image_width"], payload["image_height"]):
                    raise ValueError("The prepared image and OCR dimensions differ. Use Run OCR.")
                payload = classify_payload(payload, layout)
            else:
                st.write("Rendering the selected page…")
                image = render_bytes(data, Path(filename).suffix, width, page)
                bar = st.progress(0, text="Initializing local OCR models…")
                payload = run_ocr(image, document_id=f"{Path(filename).stem}-{source_hash[:8]}",
                    source_name=filename, source_sha256=source_hash, page=page, layout=layout,
                    rotations=(0,90,270) if rotations else (0,),
                    progress=lambda value, text: bar.progress(value, text=text))
            st.session_state.processed = {"payload": payload, "image": image,
                                           "annotated": png_bytes(annotate(image, payload)), "filename": filename}
            status.update(label="Drawing ready", state="complete", expanded=False)
    except Exception as exc:
        st.error(f"Could not process this drawing: {exc}")
        st.info("Check the file, page number and layout settings, then try again.")

processed = st.session_state.get("processed")
if processed is None:
    left, right = st.columns([1, 1.3], gap="large")
    with left:
        st.subheader("Start with a P&ID")
        st.write("Choose a file in the sidebar, select a layout, and run OCR. SVG, PNG and individual PDF pages are supported.")
        st.write("For a quick walkthrough, open the prepared reference example and search for **P4711**, **P4712** or **H1007**.")
        st.caption("OCR can miss or misread labels. Results include confidence, region type and the original drawing context.")
    with right:
        preview = ROOT / "outputs/reference_pid.png"
        if source == "Reference drawing" and preview.exists():
            st.image(str(preview), caption="Reference P&ID · select Run OCR or Open prepared example", width="stretch")
    st.stop()

payload, image = processed["payload"], processed["image"]
inventory = build_instrument_inventory(payload)
# Derived inventory is separate from raw OCR and also added for full JSON download.
payload["instrument_inventory"] = inventory
table = text_table(payload)
searchable = table.loc[table.searchable.astype(bool)]
st.caption(f"{processed['filename']} · Page {payload['page']} · {image.width:,} × {image.height:,} pixels")
cols = st.columns(4)
cols[0].metric("Detected regions", len(table))
cols[1].metric("Searchable regions", len(searchable))
cols[2].metric("Border exclusions", len(table)-len(searchable))
cols[3].metric("Review flags", int(table.needs_review.sum()))
if table.empty:
    st.warning("No text was detected. Inspect the page or try a higher resolution and vertical-text passes.")

search_tab, instrument_tab, text_tab, drawing_tab = st.tabs(["Search a tag", "Instrument list", "Detected text", "Drawing & downloads"])
with search_tab:
    with st.form("tag_search"):
        query = st.text_input("Equipment or instrument tag", value="P4711" if source == "Reference drawing" else "", placeholder="e.g. PI4712 or PT133035", key="tag_query")
        search_mode = st.radio("Match mode", ["Contains", "Exact tag"], horizontal=True, key="match_mode")
        st.caption("Contains also finds longer tags: PI4712 finds PI4712.01, including grouped OCR boxes. Use Exact tag to exclude partial matches.")
        submitted = st.form_submit_button("Find all occurrences", type="primary")
    if submitted:
        st.session_state.pop("search_bundle", None)
        try:
            st.session_state.search_bundle = bundle_search(payload, image, query, layout,
                                                          "contains" if search_mode == "Contains" else "exact")
        except (ValueError, OSError) as exc:
            st.error(str(exc))
    bundle = st.session_state.get("search_bundle")
    if bundle:
        report = bundle["report"]
        st.subheader(f"{report['occurrence_count']} occurrences for {report['query_normalized']}")
        st.caption(f"Results from {report.get('search_mode', 'exact')} search.")
        if not report["groups"]:
            st.info("No match in this search mode. Try a shorter query in Contains mode or check Detected text for a misread label. This does not establish that the equipment is absent.")
        else:
            st.caption("Red: matched OCR region · Blue: nearby text. Nearby text is spatial context, not verified equipment ownership.")
        st.download_button("Download search report & crops", bundle["zip"], file_name="pid_search_results.zip", mime="application/zip")
        for region_type, occurrences in report["groups"].items():
            st.markdown(f"### {region_type.replace('_', ' ').title()} · {len(occurrences)}")
            for occurrence in occurrences:
                with st.container(border=True):
                    st.markdown(f"**{occurrence['source_detection_id']} · {occurrence['matched_text']}**")
                    st.caption(f"{occurrence['region_id']} · OCR confidence {occurrence['ocr_confidence']:.1%}")
                    if occurrence.get('match_quality') in {'partial', 'mixed'}:
                        st.caption("Partial text match — check the full tag above to select the intended instrument.")
                    if occurrence['match_method'] == 'spatially_grouped':
                        st.info("Matched across separate OCR boxes: " + " + ".join(occurrence['grouping_evidence']['source_texts']))
                        if occurrence['ambiguous']:
                            st.warning("Ambiguous grouping: nearby fragments have competing pairings. Verify this candidate on the drawing.")
                        with st.expander("Grouping evidence"):
                            st.json(occurrence['grouping_evidence'])
                    st.image(bundle["crops"][occurrence["crop_file"]], width="stretch")
                    with st.expander(f"Nearby OCR text ({len(occurrence['nearby_ocr'])})"):
                        st.dataframe(pd.DataFrame(occurrence["nearby_ocr"]), hide_index=True, width="stretch")
                    with st.expander("Why this region?"):
                        method = occurrence["region_selection_method"]
                        st.write("The tag is inside a configured table or title block." if method == "configured_region_instance"
                                 else "A local window around the tag selected intersecting OCR text. The crop expanded once to include those text boxes in full.")
                        st.json({"region_type": region_type, "initial_region": occurrence["region_bounds"], "crop_bounds": occurrence["crop_bounds"]})
    else:
        st.info("Enter a tag to retrieve every matching location, grouped by drawing region.")

with instrument_tab:
    st.subheader("Candidate instrument inventory")
    st.caption("One row per canonical tag, linked to every occurrence. Includes complete OCR tags and aligned prefix/number pairs. Naming rules and grouping are provisional.")
    instrument_rows = pd.DataFrame(inventory['instruments'], columns=['canonical_tag','prefix','category','occurrence_count','occurrence_ids','region_types','has_grouped_occurrences','ambiguous','needs_review'])
    st.dataframe(instrument_rows, hide_index=True, width="stretch")
    st.caption(f"{len(inventory['instruments'])} candidate instruments · {len(inventory['occurrences'])} occurrences · {len(inventory['unpaired_prefix_detection_ids'])} unpaired prefix boxes")
    if inventory['occurrences']:
        selected = st.selectbox("Inspect instrument occurrences", [r['canonical_tag'] for r in inventory['instruments']], key="inspect_instrument")
        for occurrence in inventory['occurrences']:
            if occurrence['canonical_tag'] == selected:
                st.json(occurrence, expanded=False)
    st.download_button("Instrument inventory (JSON)", json.dumps(inventory,indent=2,ensure_ascii=False).encode(), "instrument_inventory.json", "application/json")
    st.download_button("Instrument list (CSV)", instrument_rows.to_csv(index=False).encode(), "instrument_list.csv", "text/csv")

with text_tab:
    c1, c2 = st.columns([1, 2])
    show_border = c1.checkbox("Include excluded border text", value=False)
    region_filter = c2.multiselect("Region types", ["process_drawing", "equipment_data_table", "title_block", "drawing_border"])
    fragment = st.text_input("Filter detected text", placeholder="A word, number or tag fragment")
    view = table if show_border else searchable
    if region_filter:
        view = view[view.region_type.isin(region_filter)]
    if fragment:
        view = view[view.text.str.contains(fragment, case=False, regex=False)]
    st.caption(f"Showing {len(view)} of {len(table)} detections")
    st.dataframe(view, hide_index=True, width="stretch",
                 column_config={"confidence": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f")})
    st.download_button("Download displayed rows (CSV)", view.to_csv(index=False).encode(), "detected_text.csv", "text/csv")

with drawing_tab:
    st.image(processed["annotated"], width="stretch")
    st.caption("Green: detected text · Orange: low confidence or a tile-edge fragment · Gray: excluded drawing border. IDs correspond to the text table.")
    downloads = st.columns(3)
    downloads[0].download_button("Full OCR JSON", json.dumps(payload, indent=2, ensure_ascii=False).encode(), "pid_ocr.json", "application/json")
    filtered = {**payload, "detections": [d for d in payload["detections"] if d["searchable"]]}
    downloads[1].download_button("Searchable JSON", json.dumps(filtered, indent=2, ensure_ascii=False).encode(), "pid_searchable.json", "application/json")
    downloads[2].download_button("Annotated PNG", processed["annotated"], "pid_annotated.png", "image/png")
    st.download_button("All detections (CSV)", table.to_csv(index=False).encode(), "pid_ocr.csv", "text/csv")
