import os
import sys
import uuid
import json
import logfire

# Do not require a Logfire cloud token for local ingestion. If LOGFIRE_TOKEN is
# present, Logfire sends telemetry; otherwise instrumentation stays local.
logfire.configure(
    token=os.getenv("LOGFIRE_TOKEN") or None,
    service_name="enterprise-ingestion-service",
    send_to_logfire="if-token-present",
)
from qdrant_client.http import models
from app.config import DATA_DIR,PROCESSED_DIR,QDRANT_COLLECTION,settings
from app.services.retrieval.embedding import embed_texts
from app.services.retrieval.qdrant_service import client as qdrant_client,ensure_collection
from app.ingestion.loaders.pdf import parse_pdf
from app.ingestion.loaders.html import parse_html
from app.ingestion.loaders.text import parse_text
from app.ingestion.chunking.splitter import chunk_text
from app.ingestion.loaders.ocr import parse_image,parse_pdf_scans,is_pid_document

PROCESSED_DATA_DIR=str(PROCESSED_DIR)
IMAGE_EXTENSIONS={'.svg','.png','.jpg','.jpeg','.tif','.tiff','.bmp'}

def save_processed_locally(data: dict,source_type: str,filename: str) -> str:
    folder=os.path.join(PROCESSED_DATA_DIR,source_type); os.makedirs(folder,exist_ok=True)
    dest=os.path.join(folder,f'{filename}.json')
    with open(dest,'w',encoding='utf-8') as output:json.dump(data,output,ensure_ascii=False,indent=2)
    return dest

def _extract(file_path: str,filename: str):
    ext=os.path.splitext(filename)[1].lower(); ocr_result={'ocr_pages':[],'extraction_mode':'text'}
    if ext=='.pdf':
        full_text=parse_pdf(file_path)
        force_drawing_ocr=is_pid_document(filename,full_text)
        ocr_result=parse_pdf_scans(file_path,force_all_pages=force_drawing_ocr)
        if ocr_result['text']:full_text=(full_text+'\n\n'+ocr_result['text']).strip()
        return full_text,ocr_result
    if ext in IMAGE_EXTENSIONS:
        ocr_result=parse_image(file_path)
        return ocr_result['text'],ocr_result
    if ext in {'.html','.htm'}:return parse_html(file_path),ocr_result
    if ext in {'.txt','.md','.rst','.log','.csv','.tsv','.json'}:return parse_text(file_path),ocr_result
    if ext in {'.docx','.pptx'}:
        from app.ingestion.loaders.office import parse_office
        return parse_office(file_path),ocr_result
    return '',ocr_result

def process_file(file_path: str,filename: str,source_type: str):
    with logfire.span('Processing File',file=filename,source=source_type):
        try:
            full_text,ocr_result=_extract(file_path,filename)
            if not full_text or not full_text.strip():
                logfire.warning(f'No text extracted from {filename} — skipping.'); return
            chunks=chunk_text(full_text)
            if not chunks:return
            processed_data={'filename':filename,'source_type':source_type,'chunks':chunks,
                            'extraction_mode':ocr_result.get('extraction_mode'),
                            'ocr_pages':ocr_result.get('ocr_pages',[])}
            local_path=save_processed_locally(processed_data,source_type,filename)
            logfire.info(f'Saved processed data → {local_path}')
            ensure_collection()
            embeddings=embed_texts(chunks)
            ocr_pages=ocr_result.get('ocr_pages',[])
            points=[models.PointStruct(id=str(uuid.uuid4()),vector=vector,payload={
                'text':chunk,'source':filename,'source_type':source_type,
                'content_type':'document_with_ocr' if ocr_pages else 'document_text',
                'has_ocr':bool(ocr_pages),'ocr_page_numbers':[p.get('page') for p in ocr_pages]})
                for chunk,vector in zip(chunks,embeddings)]
            qdrant_client.upsert(collection_name=settings.QDRANT_COLLECTION,points=points,wait=True)
            logfire.info(f'Indexed {len(points)} points to Qdrant from {filename}.')
            return {'filename':filename,'source_type':source_type,'chunks':len(chunks),'ocr_pages':len(ocr_pages),'processed_path':local_path}
        except Exception as exc:
            logfire.error(f'Failed to process {filename}: {exc}')
            return {'filename':filename,'source_type':source_type,'error':str(exc)}

def process_directory(dir_path: str,source_type: str):
    with logfire.span('Scanning Directory',path=dir_path,source=source_type):
        files=[name for name in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path,name))]
        return [process_file(os.path.join(dir_path,name),name,source_type) for name in files]

def _source_type(folder: str,explicit: str|None=None):
    if explicit:return explicit
    low=folder.lower()
    if 'true' in low:return 'true_data'
    if 'noisy' in low:return 'noisy_data'
    return folder

def run_universal_ingestion(base_dir: str|None=None,explicit_source_type: str|None=None,wipe: bool=False,include_noisy: bool=True):
    base_dir=base_dir or str(DATA_DIR)
    if wipe and qdrant_client.collection_exists(settings.QDRANT_COLLECTION):qdrant_client.delete_collection(settings.QDRANT_COLLECTION)
    ensure_collection()
    subdirs=[name for name in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir,name))]
    results=[]
    if subdirs:
        for subdir in subdirs:
            kind=_source_type(subdir,explicit_source_type)
            if not include_noisy and kind=='noisy_data':continue
            results.extend(process_directory(os.path.join(base_dir,subdir),kind))
    else:
        folder=os.path.basename(os.path.normpath(base_dir)); results.extend(process_directory(base_dir,_source_type(folder,explicit_source_type)))
    return {'processed':sum(bool(r and 'error' not in r) for r in results),
            'failed':sum(bool(r and 'error' in r) for r in results),'files':results}

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingest documents into the configured Qdrant collection.")
    parser.add_argument("directory", nargs="?", default=str(DATA_DIR), help="Directory to ingest")
    parser.add_argument("--wipe", action="store_true", help="Delete the configured collection before ingesting")
    cli_args = parser.parse_args()
    if not os.path.isdir(cli_args.directory):
        parser.error(f"directory does not exist: {cli_args.directory}")
    report = run_universal_ingestion(cli_args.directory, wipe=cli_args.wipe)
    print(json.dumps(report, ensure_ascii=False, indent=2))
