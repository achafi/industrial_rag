from app.config import DATA_DIR
from app.ingestion.processor import process_file,run_universal_ingestion
class IngestionService:
    def ingest_corpus(self,include_noisy=True):return run_universal_ingestion(str(DATA_DIR),include_noisy=include_noisy)
    def ingest_file(self,path):
        from pathlib import Path
        path=Path(path)
        relative=path.relative_to(DATA_DIR)
        source_type=relative.parts[0] if len(relative.parts)>1 else 'general'
        return process_file(str(path),path.name,source_type)
