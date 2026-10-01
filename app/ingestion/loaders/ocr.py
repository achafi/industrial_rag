"""OCR adapter for image files and image-only / P&ID PDF pages.

The input loaders remain responsible for ordinary text extraction. This module
only renders pages/drawings and returns searchable OCR text plus the complete
RapidOCR payload (boxes, confidence, region and review metadata).
"""
from pathlib import Path
import hashlib
import re

from PIL import Image, ImageOps
from pypdfium2 import PdfDocument
from pid_pipeline import REFERENCE_LAYOUT, render_input, run_ocr

RASTER_SUFFIXES={'.png','.jpg','.jpeg','.tif','.tiff','.bmp'}

def _render_image(path: Path, page: int=1):
    if path.suffix.lower() in {'.pdf','.svg'}:
        return render_input(path,target_width=4000,page=page)
    with Image.open(path) as source:
        oriented=ImageOps.exif_transpose(source).convert('RGBA')
        background=Image.new('RGBA',oriented.size,'white')
        background.alpha_composite(oriented)
        image=background.convert('RGB')
        if image.width!=4000:
            height=round(image.height*4000/image.width)
            image=image.resize((4000,height),Image.Resampling.LANCZOS)
        return image

def _ocr(path: Path, page: int=1):
    image=_render_image(path,page)
    is_reference=path.name=='area_47_reference_pid.svg'
    return run_ocr(image,document_id=path.stem,source_name=path.name,
        source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),page=page,
        layout=REFERENCE_LAYOUT if is_reference else None)

def _payload_text(payload: dict) -> str:
    detections=[d for d in payload.get('detections',[]) if d.get('searchable',True) and d.get('text_raw','').strip()]
    detections.sort(key=lambda d:(d.get('center',{}).get('y',0),d.get('center',{}).get('x',0)))
    return '\n'.join(d['text_raw'] for d in detections)

def parse_image(file_path: str | Path) -> dict:
    """OCR one SVG or raster drawing; returns text and its structured OCR result."""
    path=Path(file_path)
    if path.suffix.lower() not in RASTER_SUFFIXES|{'.svg'}:
        raise ValueError(f'Not a supported image drawing: {path.suffix}')
    payload=_ocr(path)
    return {'text':_payload_text(payload),'ocr_pages':[payload],'extraction_mode':'drawing_ocr'}

def parse_pdf_scans(file_path: str | Path, *, force_all_pages: bool=False) -> dict:
    """OCR blank/scanned PDF pages; set force_all_pages for vector P&ID drawings."""
    path=Path(file_path); pdf=PdfDocument(str(path)); payloads=[]
    try:
        for page_number in range(1,len(pdf)+1):
            page=pdf[page_number-1]
            try:
                textpage=page.get_textpage()
                try: embedded=(textpage.get_text_range() or '').strip()
                finally: textpage.close()
            finally: page.close()
            if force_all_pages or len(embedded)<80:
                result=_ocr(path,page_number)
                if result.get('detections'): payloads.append(result)
    finally:
        pdf.close()
    return {'text':'\n\n'.join(f"[Page {item['page']}]\n{_payload_text(item)}" for item in payloads),
            'ocr_pages':payloads,'extraction_mode':'pid_pdf_ocr' if force_all_pages else 'scanned_pdf_ocr'}

def is_pid_document(filename: str, extracted_text: str='') -> bool:
    marker=re.search(r'(p\s*&\s*id|\bpid\b|_pid\b|\bpid_|piping.{0,30}instrumentation|instrumentation.{0,30}diagram|process.{0,20}flow.{0,20}diagram|\b(?:P|PV|PI|H|T)\s*-?\s*\d{3,6}(?:\.\d{1,2})?\b)',filename+' '+extracted_text,re.I)
    return bool(marker)
