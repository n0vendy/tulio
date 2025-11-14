import chromadb
from chromadb.config import Settings
import uuid
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging
from sentence_transformers import SentenceTransformer
from .privacy import PrivacyLevel, PrivacyManager

logger = logging.getLogger(__name__)


class PrivacyPartitionedVectorStore:
    """vector store with privacy-based partitioning using ChromaDB"""
    
    def __init__(self, db_path: str = "tulio_db", embedding_model: str = "all-MiniLM-L6-v2"):
        self.db_path = Path(db_path)
        self.db_path.mkdir(exist_ok=True)
        
        # initialize chromadb client
        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # initialize embedding model
        self.embedding_model = SentenceTransformer(embedding_model)
        
        # create collections for each privacy level
        self.collections = {}
        self._initialize_collections()
    
    def _initialize_collections(self):
        """create or get collections for each privacy level"""
        for level in PrivacyLevel:
            collection_name = f"documents_{level.value}"
            try:
                self.collections[level] = self.client.get_collection(
                    name=collection_name,
                    embedding_function=self._embedding_function
                )
                logger.info(f"loaded existing collection: {collection_name}")
            except:
                self.collections[level] = self.client.create_collection(
                    name=collection_name,
                    embedding_function=self._embedding_function,
                    metadata={"privacy_level": level.value}
                )
                logger.info(f"created new collection: {collection_name}")
    
    def _embedding_function(self, texts: List[str]) -> List[List[float]]:
        """generate embeddings for texts"""
        return self.embedding_model.encode(texts).tolist()
    
    def add_documents(self, documents: List[Dict[str, Any]]):
        """add documents to appropriate privacy-partitioned collections"""
        # group documents by privacy level
        docs_by_level = {}
        for doc in documents:
            privacy_level = PrivacyLevel(doc['metadata']['privacy_level'])
            if privacy_level not in docs_by_level:
                docs_by_level[privacy_level] = []
            docs_by_level[privacy_level].append(doc)
        
        # add to each collection
        for privacy_level, level_docs in docs_by_level.items():
            collection = self.collections[privacy_level]
            
            ids = [str(uuid.uuid4()) for _ in level_docs]
            documents = [doc['content'] for doc in level_docs]
            metadatas = [doc['metadata'] for doc in level_docs]
            
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
            
            logger.info(f"added {len(level_docs)} documents to {privacy_level.value} collection")
    
    def search(self, query: str, privacy_levels: List[PrivacyLevel], 
               max_results: int = 5) -> List[Dict[str, Any]]:
        """search across specified privacy levels"""
        all_results = []
        
        for privacy_level in privacy_levels:
            if privacy_level not in self.collections:
                continue
                
            collection = self.collections[privacy_level]
            
            try:
                results = collection.query(
                    query_texts=[query],
                    n_results=max_results,
                    include=['documents', 'metadatas', 'distances']
                )
                
                # format results
                for i in range(len(results['documents'][0])):
                    result = {
                        'content': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i],
                        'distance': results['distances'][0][i],
                        'privacy_level': privacy_level.value
                    }
                    all_results.append(result)
                    
            except Exception as e:
                logger.error(f"error searching {privacy_level.value} collection: {e}")
        
        # sort by relevance (distance) and limit results
        all_results.sort(key=lambda x: x['distance'])
        return all_results[:max_results]
    
    def delete_file_documents(self, file_path: str):
        """delete all documents from a specific file across all collections"""
        for privacy_level, collection in self.collections.items():
            try:
                # query for documents from this file
                results = collection.get(
                    where={"file_path": file_path},
                    include=['ids']
                )
                
                if results['ids']:
                    collection.delete(ids=results['ids'])
                    logger.info(f"deleted {len(results['ids'])} documents from {file_path} in {privacy_level.value} collection")
                    
            except Exception as e:
                logger.error(f"error deleting documents from {file_path} in {privacy_level.value}: {e}")
    
    def get_collection_stats(self) -> Dict[str, int]:
        """get document counts for each privacy level"""
        stats = {}
        for privacy_level, collection in self.collections.items():
            try:
                count = collection.count()
                stats[privacy_level.value] = count
            except Exception as e:
                logger.error(f"error getting stats for {privacy_level.value}: {e}")
                stats[privacy_level.value] = 0
        return stats
    
    def reset_all_collections(self):
        """delete all data (use with caution)"""
        for privacy_level in PrivacyLevel:
            collection_name = f"documents_{privacy_level.value}"
            try:
                self.client.delete_collection(name=collection_name)
                logger.info(f"deleted collection: {collection_name}")
            except:
                pass
        
        # recreate collections
        self._initialize_collections()


class RAGSearchEngine:
    """high-level interface for RAG search with privacy"""
    
    def __init__(self, config_path: str = "config.yaml", db_path: str = "tulio_db"):
        import yaml
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.vector_store = PrivacyPartitionedVectorStore(
            db_path=db_path,
            embedding_model=self.config['rag']['embedding_model']
        )
        self.privacy_manager = PrivacyManager(config_path)
        self.max_results = self.config['rag']['max_results']
    
    def search(self, query: str, query_context: str = "") -> List[Dict[str, Any]]:
        """search for relevant documents respecting privacy boundaries"""
        # determine accessible privacy levels
        accessible_levels = list(self.privacy_manager.get_accessible_levels(query_context))
        
        # perform search
        results = self.vector_store.search(
            query=query,
            privacy_levels=accessible_levels,
            max_results=self.max_results
        )
        
        # additional privacy filtering if needed
        filtered_results = self.privacy_manager.filter_results_by_privacy(results, query_context)
        
        return filtered_results
    
    def get_context_for_query(self, query: str, query_context: str = "") -> str:
        """get formatted context string for claude api"""
        results = self.search(query, query_context)
        
        if not results:
            return ""
        
        context_parts = []
        for result in results:
            file_name = result['metadata'].get('file_name', 'unknown')
            content = result['content']
            
            context_parts.append(f"from {file_name}:\n{content}")
        
        return "\n\n---\n\n".join(context_parts)
    
    def add_documents(self, documents: List[Dict[str, Any]]):
        """add documents to vector store"""
        self.vector_store.add_documents(documents)
    
    def get_stats(self) -> Dict[str, int]:
        """get statistics about indexed documents"""
        return self.vector_store.get_collection_stats()