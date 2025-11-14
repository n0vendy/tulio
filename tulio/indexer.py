import os
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
import yaml
from sentence_transformers import SentenceTransformer
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time
import logging
from .privacy import PrivacyManager, PrivacyLevel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FileIndexer:
    def __init__(self, config_path: str = "config.yaml", db_path: str = "tulio_db"):
        self.config = self._load_config(config_path)
        self.privacy_manager = PrivacyManager(config_path)
        self.db_path = db_path
        self.embedding_model = SentenceTransformer(self.config['rag']['embedding_model'])
        self.file_hashes = self._load_file_hashes()
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def _load_file_hashes(self) -> Dict[str, str]:
        """load previously computed file hashes to detect changes"""
        hash_file = Path(self.db_path) / "file_hashes.json"
        if hash_file.exists():
            import json
            with open(hash_file, 'r') as f:
                return json.load(f)
        return {}
    
    def _save_file_hashes(self):
        """save file hashes to disk"""
        hash_file = Path(self.db_path) / "file_hashes.json"
        hash_file.parent.mkdir(exist_ok=True)
        import json
        with open(hash_file, 'w') as f:
            json.dump(self.file_hashes, f)
    
    def _get_file_hash(self, file_path: str) -> str:
        """compute md5 hash of file content"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            logger.error(f"error hashing file {file_path}: {e}")
            return ""
    
    def _should_reindex(self, file_path: str) -> bool:
        """check if file needs reindexing based on hash"""
        current_hash = self._get_file_hash(file_path)
        stored_hash = self.file_hashes.get(file_path, "")
        
        if current_hash != stored_hash:
            self.file_hashes[file_path] = current_hash
            return True
        return False
    
    def _extract_text_from_file(self, file_path: str) -> Optional[str]:
        """extract text content from various file types"""
        path = Path(file_path)
        
        try:
            if path.suffix.lower() in ['.txt', '.md', '.py', '.js', '.yaml', '.yml', '.json']:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            
            elif path.suffix.lower() == '.pdf':
                # would need PyPDF2 or similar
                # return self._extract_pdf_text(file_path)
                logger.warning(f"pdf extraction not implemented for {file_path}")
                return None
            
            elif path.suffix.lower() in ['.docx', '.doc']:
                # would need python-docx
                # return self._extract_docx_text(file_path)
                logger.warning(f"docx extraction not implemented for {file_path}")
                return None
            
            else:
                logger.debug(f"unsupported file type: {file_path}")
                return None
                
        except Exception as e:
            logger.error(f"error extracting text from {file_path}: {e}")
            return None
    
    def _chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """split text into overlapping chunks"""
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            
            # try to break at word boundary
            if end < len(text):
                # look for last space within reasonable distance
                for i in range(min(100, end - start)):
                    if text[end - i] == ' ':
                        end = end - i
                        break
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            start = end - overlap
            if start >= len(text):
                break
                
        return chunks
    
    def index_file(self, file_path: str) -> List[Dict[str, Any]]:
        """index a single file and return document chunks with metadata"""
        if not self.privacy_manager.should_index(file_path):
            return []
        
        if not self._should_reindex(file_path):
            logger.debug(f"file unchanged, skipping: {file_path}")
            return []
        
        text = self._extract_text_from_file(file_path)
        if not text:
            return []
        
        privacy_level = self.privacy_manager.classify_file(file_path)
        chunks = self._chunk_text(
            text, 
            self.config['rag']['chunk_size'],
            self.config['rag']['chunk_overlap']
        )
        
        documents = []
        for i, chunk in enumerate(chunks):
            doc = {
                'content': chunk,
                'metadata': {
                    'file_path': file_path,
                    'file_name': Path(file_path).name,
                    'privacy_level': privacy_level.value,
                    'chunk_index': i,
                    'total_chunks': len(chunks),
                    'file_modified': os.path.getmtime(file_path)
                }
            }
            documents.append(doc)
        
        logger.info(f"indexed {len(documents)} chunks from {file_path} (privacy: {privacy_level.value})")
        return documents
    
    def index_directory(self, directory: str) -> List[Dict[str, Any]]:
        """index all supported files in a directory"""
        path = Path(directory).expanduser()
        if not path.exists():
            logger.warning(f"directory does not exist: {directory}")
            return []
        
        documents = []
        supported_extensions = set(self.config['indexing']['file_types'])
        
        for file_path in path.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
                docs = self.index_file(str(file_path))
                documents.extend(docs)
        
        self._save_file_hashes()
        return documents
    
    def index_all_watched_directories(self) -> List[Dict[str, Any]]:
        """index all directories specified in config"""
        all_documents = []
        
        for directory in self.config['indexing']['watch_dirs']:
            logger.info(f"indexing directory: {directory}")
            docs = self.index_directory(directory)
            all_documents.extend(docs)
        
        logger.info(f"indexed {len(all_documents)} total documents")
        return all_documents


class FileWatcher(FileSystemEventHandler):
    """watch for file changes and trigger reindexing"""
    
    def __init__(self, indexer: FileIndexer, vector_store):
        self.indexer = indexer
        self.vector_store = vector_store
        self.debounce_time = 2.0  # seconds
        self.pending_files = {}
    
    def on_modified(self, event):
        if event.is_directory:
            return
        
        file_path = event.src_path
        current_time = time.time()
        
        # debounce rapid file changes
        if file_path in self.pending_files:
            if current_time - self.pending_files[file_path] < self.debounce_time:
                return
        
        self.pending_files[file_path] = current_time
        
        # schedule reindexing
        logger.info(f"file changed: {file_path}")
        self._reindex_file(file_path)
    
    def _reindex_file(self, file_path: str):
        """reindex a single file"""
        try:
            documents = self.indexer.index_file(file_path)
            if documents:
                # remove old documents for this file
                self.vector_store.delete_file_documents(file_path)
                # add new documents
                self.vector_store.add_documents(documents)
                logger.info(f"reindexed {file_path}")
        except Exception as e:
            logger.error(f"error reindexing {file_path}: {e}")