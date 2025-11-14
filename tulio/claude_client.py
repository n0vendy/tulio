import os
import yaml
from typing import List, Dict, Any, Optional
import anthropic
from dotenv import load_dotenv
from .vector_store import RAGSearchEngine
from .utilities import TulioUtilities
import logging
import re

logger = logging.getLogger(__name__)

load_dotenv()


class TulioClaudeClient:
    """claude api client with RAG integration for tulio"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        self.rag_engine = RAGSearchEngine(config_path)
        self.utilities = TulioUtilities()
        
        # load personality and greeting from config
        self.personality = self.config['tulio']['personality']
        self.greeting = self.config['tulio']['greeting']
        
        # conversation history
        self.conversation_history = []
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def _load_about_me(self) -> str:
        """load personal information from aboutme.txt"""
        try:
            with open('aboutme.txt', 'r') as f:
                return f.read().strip()
        except FileNotFoundError:
            logger.warning("aboutme.txt not found")
            return ""
    
    def _build_system_prompt(self, rag_context: str = "") -> str:
        """build system prompt with personality and context"""
        about_me = self._load_about_me()
        
        system_prompt = f"{self.personality}\n\n"
        
        if about_me:
            system_prompt += f"here's what you know about mira:\n{about_me}\n\n"
        
        if rag_context:
            system_prompt += f"relevant information from mira's files:\n{rag_context}\n\n"
            system_prompt += "use this information to provide more personalized and helpful responses. reference specific details when relevant.\n\n"
        
        system_prompt += "keep responses conversational and friendly. use lowercase and casual language. don't use emojis, instead use text-based expressions like ':D', ':3' ':P', etc.\n\n"
        
        system_prompt += "you have several useful capabilities:\n"
        system_prompt += "1. GET_WEATHER: city_name - fetch current weather\n"
        system_prompt += "2. CREATE_DIR: directory_path - create directories (with user approval)\n"  
        system_prompt += "3. WRITE_FILE: file_path | content - write files (with user approval)\n"
        system_prompt += "4. MOVE_FILE: source_path -> destination_path - move files (with user approval)\n\n"
        
        system_prompt += "when you want to use these capabilities, include the command in your response. examples:\n"
        system_prompt += "GET_WEATHER: San Francisco\n"
        system_prompt += "CREATE_DIR: ~/Downloads/new_folder\n"
        system_prompt += "WRITE_FILE: ~/Downloads/notes.txt | these are my notes about the meeting\n"
        system_prompt += "MOVE_FILE: ~/Downloads/document.pdf -> ~/Downloads/documents/document.pdf\n\n"
        
        return system_prompt
    
    def _should_use_rag(self, message: str) -> bool:
        """determine if RAG search would be helpful for this message"""
        # keywords that suggest user wants info from their files
        rag_triggers = [
            'find', 'search', 'look for', 'remember', 'recall', 'what did i',
            'show me', 'my', 'project', 'file', 'document', 'note', 'wrote',
            'work on', 'working on', 'code', 'script'
        ]
        
        message_lower = message.lower()
        return any(trigger in message_lower for trigger in rag_triggers)
    
    def chat(self, message: str, use_rag: bool = None) -> str:
        """send message to claude with optional RAG context"""
        # determine if RAG should be used
        if use_rag is None:
            use_rag = self._should_use_rag(message)
        
        # get RAG context if needed
        rag_context = ""
        if use_rag:
            try:
                rag_context = self.rag_engine.get_context_for_query(message, message)
                if rag_context:
                    logger.info(f"retrieved RAG context: {len(rag_context)} characters")
            except Exception as e:
                logger.error(f"error retrieving RAG context: {e}")
        
        # build system prompt
        system_prompt = self._build_system_prompt(rag_context)
        
        # prepare messages for claude
        messages = []
        
        # add conversation history
        for entry in self.conversation_history[-10:]:  # keep last 10 exchanges
            messages.append({"role": entry["role"], "content": entry["content"]})
        
        # add current message
        messages.append({"role": "user", "content": message})
        
        try:
            # call claude api
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1000,
                system=system_prompt,
                messages=messages
            )
            
            assistant_response = response.content[0].text
            
            # process any commands in the response
            processed_response = self._process_commands(assistant_response)
            
            # update conversation history
            self.conversation_history.append({"role": "user", "content": message})
            self.conversation_history.append({"role": "assistant", "content": processed_response})
            
            return processed_response
            
        except Exception as e:
            logger.error(f"error calling claude api: {e}")
            return f"sorry, i had trouble processing that. error: {str(e)}"
    
    def _process_commands(self, response: str) -> str:
        """process and execute commands in response"""
        processed_response = response
        
        # extract commands using regex
        weather_pattern = r'GET_WEATHER:\s*(.+?)(?:\n|$)'
        dir_pattern = r'CREATE_DIR:\s*(.+?)(?:\n|$)'
        file_pattern = r'WRITE_FILE:\s*(.+?)\s*\|\s*(.+?)(?:\n\n|$)'
        move_pattern = r'MOVE_FILE:\s*(.+?)\s*->\s*(.+?)(?:\n|$)'
        
        # process weather commands
        for match in re.finditer(weather_pattern, response):
            city = match.group(1).strip()
            weather_result = self.utilities.get_weather(city)
            
            if weather_result["success"]:
                weather_text = f"weather in {weather_result['city']}: {weather_result['temperature']}, {weather_result['description']}, humidity {weather_result['humidity']}"
            else:
                weather_text = f"couldn't get weather: {weather_result['error']}"
            
            processed_response = processed_response.replace(match.group(0), weather_text)
        
        # process directory creation
        for match in re.finditer(dir_pattern, response):
            dir_path = match.group(1).strip()
            dir_result = self.utilities.create_directory(dir_path)
            
            if dir_result["success"]:
                dir_text = dir_result["message"]
            else:
                dir_text = f"couldn't create directory: {dir_result['error']}"
            
            processed_response = processed_response.replace(match.group(0), dir_text)
        
        # process file writing
        for match in re.finditer(file_pattern, response, re.DOTALL):
            file_path = match.group(1).strip()
            content = match.group(2).strip()
            file_result = self.utilities.write_file(file_path, content)
            
            if file_result["success"]:
                file_text = file_result["message"]
            else:
                file_text = f"couldn't write file: {file_result['error']}"
            
            processed_response = processed_response.replace(match.group(0), file_text)
        
        # process file moving
        for match in re.finditer(move_pattern, response):
            source = match.group(1).strip()
            dest = match.group(2).strip()
            move_result = self.utilities.move_file(source, dest)
            
            if move_result["success"]:
                move_text = move_result["message"]
            else:
                move_text = f"couldn't move file: {move_result['error']}"
            
            processed_response = processed_response.replace(match.group(0), move_text)
        
        return processed_response
    
    def get_greeting(self) -> str:
        """get tulio's greeting message"""
        return self.greeting
    
    def clear_history(self):
        """clear conversation history"""
        self.conversation_history = []
        logger.info("conversation history cleared")
    
    def index_files(self):
        """trigger full reindexing of files"""
        try:
            from .indexer import FileIndexer
            indexer = FileIndexer()
            documents = indexer.index_all_watched_directories()
            
            if documents:
                self.rag_engine.add_documents(documents)
                stats = self.rag_engine.get_stats()
                total_docs = sum(stats.values())
                return f"indexed {len(documents)} new documents. total: {total_docs} documents across privacy levels."
            else:
                return "no new documents to index."
                
        except Exception as e:
            logger.error(f"error indexing files: {e}")
            return f"error indexing files: {str(e)}"
    
    def get_stats(self) -> str:
        """get statistics about indexed documents"""
        try:
            stats = self.rag_engine.get_stats()
            total = sum(stats.values())
            
            stats_str = f"total documents: {total}\n"
            for level, count in stats.items():
                stats_str += f"  {level}: {count} documents\n"
            
            return stats_str.strip()
            
        except Exception as e:
            logger.error(f"error getting stats: {e}")
            return f"error getting stats: {str(e)}"