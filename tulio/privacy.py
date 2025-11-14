from enum import Enum
from pathlib import Path
from typing import Set, Dict, Any
import yaml
from pydantic import BaseModel


class PrivacyLevel(Enum):
    PUBLIC = "public"
    PERSONAL = "personal"
    PRIVATE = "private"
    WORK = "work"


class PrivacyConfig(BaseModel):
    extension_rules: Dict[str, str] = {}
    path_rules: Dict[str, str] = {}
    watch_dirs: Set[str] = set()
    exclude_dirs: Set[str] = set()


class PrivacyManager:
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
    
    def _load_config(self, config_path: str) -> PrivacyConfig:
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        privacy_config = config_data['privacy']
        indexing_config = config_data['indexing']
        
        return PrivacyConfig(
            extension_rules=privacy_config['rules']['extensions'],
            path_rules=privacy_config['rules']['paths'],
            watch_dirs=set(indexing_config['watch_dirs']),
            exclude_dirs=set(indexing_config['exclude_dirs'])
        )
    
    def classify_file(self, file_path: str) -> PrivacyLevel:
        """determine privacy level of a file based on path and extension"""
        path = Path(file_path)
        
        # check path rules first (they override extension rules)
        for pattern, level in self.config.path_rules.items():
            if self._matches_pattern(str(path), pattern):
                return PrivacyLevel(level)
        
        # check extension rules
        suffix = path.suffix.lower()
        if suffix in self.config.extension_rules:
            return PrivacyLevel(self.config.extension_rules[suffix])
        
        # default to personal for unknown files
        return PrivacyLevel.PERSONAL
    
    def _matches_pattern(self, path: str, pattern: str) -> bool:
        """simple glob-like pattern matching"""
        import fnmatch
        return fnmatch.fnmatch(path, pattern)
    
    def should_index(self, file_path: str) -> bool:
        """check if file should be indexed based on exclusion rules"""
        path = Path(file_path)
        
        # check if in excluded directory
        for exclude_dir in self.config.exclude_dirs:
            # check each part of the path against the exclude pattern
            for part in path.parts:
                if self._matches_pattern(part, exclude_dir):
                    return False
        
        return True
    
    def get_accessible_levels(self, query_context: str = "") -> Set[PrivacyLevel]:
        """determine which privacy levels are accessible for a query"""
        # for now, allow access to all levels except private
        # could be enhanced with user authentication, context analysis, etc.
        
        # if query mentions work/professional context
        if any(word in query_context.lower() for word in ['work', 'job', 'project', 'code']):
            return {PrivacyLevel.PUBLIC, PrivacyLevel.PERSONAL, PrivacyLevel.WORK}
        
        # default: public and personal only
        return {PrivacyLevel.PUBLIC, PrivacyLevel.PERSONAL}
    
    def filter_results_by_privacy(self, results, query_context: str = ""):
        """filter search results based on privacy levels"""
        accessible_levels = self.get_accessible_levels(query_context)
        
        filtered_results = []
        for result in results:
            if hasattr(result, 'metadata') and 'privacy_level' in result.metadata:
                level = PrivacyLevel(result.metadata['privacy_level'])
                if level in accessible_levels:
                    filtered_results.append(result)
            else:
                # if no privacy level set, default to allowing
                filtered_results.append(result)
        
        return filtered_results