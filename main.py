#!/usr/bin/env python3
"""
tulio - your personal ai assistant with privacy-aware RAG
"""

import os
import logging
# fix tokenizers parallelism warning
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# suppress http logging
logging.getLogger("httpx").setLevel(logging.WARNING)

import click
import asyncio
import threading
import time
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
import os
import sys
from pathlib import Path

# add tulio package to path
sys.path.insert(0, str(Path(__file__).parent))

from tulio.claude_client import TulioClaudeClient
from tulio.indexer import FileIndexer, FileWatcher
from tulio.pet_controller import PetController, IdleEmotionManager
from watchdog.observers import Observer

console = Console()


class TulioTerminal:
    """terminal interface for tulio"""
    
    def __init__(self):
        self.client = None
        self.watcher = None
        self.observer = None
        self.desktop_pet_process = None
        self.pet_controller = PetController()
        self.idle_emotion_manager = None
        
    def _check_api_key(self):
        """check if anthropic api key is set"""
        if not os.getenv('ANTHROPIC_API_KEY'):
            console.print("❌ ANTHROPIC_API_KEY not found in environment", style="red")
            console.print("please create a .env file with your api key:", style="yellow")
            console.print("ANTHROPIC_API_KEY=your_api_key_here", style="dim")
            return False
        return True
    
    def _initialize_client(self):
        """initialize claude client and file watching"""
        try:
            self.client = TulioClaudeClient()
            
            # set up file watching for live indexing
            from tulio.indexer import FileIndexer
            indexer = FileIndexer()
            self.watcher = FileWatcher(indexer, self.client.rag_engine.vector_store)
            
            self.observer = Observer()
            # watch directories from config
            for directory in self.client.config['indexing']['watch_dirs']:
                expanded_dir = Path(directory).expanduser()
                if expanded_dir.exists():
                    self.observer.schedule(self.watcher, str(expanded_dir), recursive=True)
                    console.print(f"watching {directory}", style="dim green")
            
            self.observer.start()
            
            console.print("tulio initialized successfully", style="green")
            return True
            
        except Exception as e:
            console.print(f"error initializing tulio: {e}", style="red")
            return False
    
    def _start_desktop_pet(self):
        """start the desktop pet in a separate process"""
        try:
            import subprocess
            pet_script = Path(__file__).parent / "desktoptulio" / "main.py"
            
            if pet_script.exists():
                self.desktop_pet_process = subprocess.Popen([
                    sys.executable, str(pet_script)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                console.print("tulio initiated", style="cyan")
                
                # start emotion control
                time.sleep(1)  # wait for pet to start
                if self.pet_controller.connect():
                    self.pet_controller.notify_greeting()
                    self.idle_emotion_manager = IdleEmotionManager(self.pet_controller)
                    self.idle_emotion_manager.start()
                    console.print("emotes connected", style="cyan")
            else:
                console.print("⚠️  desktop pet script not found", style="yellow")
                
        except Exception as e:
            console.print(f"⚠️  could not start desktop pet: {e}", style="yellow")
    
    def _stop_desktop_pet(self):
        """stop the desktop pet process"""
        if self.idle_emotion_manager:
            self.idle_emotion_manager.stop()
        
        self.pet_controller.disconnect()
        
        if self.desktop_pet_process:
            self.desktop_pet_process.terminate()
            self.desktop_pet_process = None
            console.print("tulio stopped", style="dim")
    
    def _show_welcome(self):
        """show welcome message and tulio's greeting"""
        welcome_text = Text()
        welcome_text.append("tulio", style="bold cyan")
        welcome_text.append(" - your personal ai assistant", style="dim")
        
        panel = Panel(
            welcome_text,
            border_style="cyan",
            padding=(1, 2)
        )
        console.print(panel)
        
        # show tulio's greeting
        if self.client:
            greeting = self.client.get_greeting()
            console.print(f"{greeting}", style="green")
    
    def _handle_command(self, user_input: str) -> bool:
        """handle special commands, return True if command was handled"""
        if user_input.startswith('/'):
            command = user_input[1:].strip().lower()
            
            if command == 'help':
                self._show_help()
            elif command == 'stats':
                self._show_stats()
            elif command == 'index':
                self._run_indexing()
            elif command == 'clear':
                self._clear_history()
            elif command == 'pet':
                self._toggle_pet()
            elif command == 'db':
                self._show_database_contents()
            elif command == 'cleanup':
                self._cleanup_excluded_files()
            elif command == 'exit' or command == 'quit':
                return False
            else:
                console.print(f"unknown command: {command}", style="red")
                console.print("type /help for available commands", style="dim")
            
            return True
        
        return False
    
    def _show_help(self):
        """show help message"""
        help_text = """
available commands:
  /help    - show this help message
  /stats   - show document indexing statistics
  /index   - manually trigger file indexing
  /clear   - clear conversation history
  /pet     - toggle desktop pet
  /db      - show database contents
  /cleanup - remove excluded files from database
  /exit    - quit tulio
        """
        console.print(help_text.strip(), style="dim")
    
    def _show_stats(self):
        """show indexing statistics"""
        if self.client:
            stats = self.client.get_stats()
            console.print(f"📊 indexing stats:\n{stats}", style="cyan")
    
    def _run_indexing(self):
        """manually trigger file indexing"""
        if self.client:
            self.pet_controller.notify_indexing()
            with console.status("[bold green]indexing files..."):
                result = self.client.index_files()
            console.print(f"{result}", style="green")
            self.pet_controller.set_emotion_for_context('finished', duration=2.0)
    
    def _clear_history(self):
        """clear conversation history"""
        if self.client:
            self.client.clear_history()
            console.print("conversation history cleared", style="dim")
    
    def _toggle_pet(self):
        """toggle desktop pet on/off"""
        if self.desktop_pet_process:
            self._stop_desktop_pet()
        else:
            self._start_desktop_pet()
    
    def _show_database_contents(self):
        """show current database contents"""
        if self.client:
            try:
                from pathlib import Path
                import json
                
                # show file hashes
                hash_file = Path("tulio_db/file_hashes.json")
                if hash_file.exists():
                    with open(hash_file, 'r') as f:
                        hashes = json.load(f)
                    
                    console.print(f"📁 indexed files ({len(hashes)}):", style="cyan")
                    for file_path in sorted(hashes.keys()):
                        file_name = Path(file_path).name
                        console.print(f"  {file_name}", style="dim")
                else:
                    console.print("no hash file found - database might be empty", style="yellow")
                
                # show vector store stats
                stats = self.client.get_stats()
                console.print(f"\n{stats}", style="cyan")
                
            except Exception as e:
                console.print(f"error reading database: {e}", style="red")
    
    def _cleanup_excluded_files(self):
        """remove files that should be excluded from database"""
        if self.client:
            try:
                from pathlib import Path
                import json
                from tulio.privacy import PrivacyManager
                
                privacy_manager = PrivacyManager()
                
                # get current hash file to see what files are indexed
                hash_file = Path("tulio_db/file_hashes.json")
                if hash_file.exists():
                    with open(hash_file, 'r') as f:
                        hashes = json.load(f)
                    
                    removed_files = []
                    files_to_keep = {}
                    
                    for file_path in hashes.keys():
                        if privacy_manager.should_index(file_path):
                            files_to_keep[file_path] = hashes[file_path]
                        else:
                            # remove from vector database
                            self.client.rag_engine.vector_store.delete_file_documents(file_path)
                            removed_files.append(Path(file_path).name)
                    
                    # update hash file
                    with open(hash_file, 'w') as f:
                        json.dump(files_to_keep, f)
                    
                    if removed_files:
                        console.print(f"🧹 removed {len(removed_files)} excluded files from database", style="green")
                        for file_name in removed_files[:10]:  # show first 10
                            console.print(f"  removed: {file_name}", style="dim")
                        if len(removed_files) > 10:
                            console.print(f"  ... and {len(removed_files) - 10} more", style="dim")
                    else:
                        console.print("no excluded files found in database", style="dim")
                else:
                    console.print("no hash file found", style="yellow")
            except Exception as e:
                console.print(f"error cleaning database: {e}", style="red")
    
    def run(self, with_pet: bool = False):
        """run the main terminal interface"""
        try:
            # check prerequisites
            if not self._check_api_key():
                return
            
            # initialize
            if not self._initialize_client():
                return
            
            # start desktop pet if requested
            if with_pet:
                self._start_desktop_pet()
            
            # show welcome
            self._show_welcome()
            
            # initial indexing
            console.print("running initial file indexing...", style="dim")
            self.pet_controller.notify_indexing()
            with console.status("[bold green]indexing files..."):
                result = self.client.index_files()
            console.print(f"{result}", style="dim green")
            self.pet_controller.set_emotion_for_context('finished', duration=2.0)
            
            # main chat loop
            while True:
                try:
                    # get user input
                    user_input = Prompt.ask("\n[bold blue]you[/bold blue]").strip()
                    
                    if not user_input:
                        continue
                    
                    # handle commands
                    if self._handle_command(user_input):
                        continue
                    
                    # check for exit
                    if user_input.lower() in ['exit', 'quit', 'bye!']:
                        break
                    
                    # notify pet of user input
                    self.pet_controller.notify_user_input()
                    
                    # chat with tulio
                    with console.status("[cyan]let me think..."):
                        response = self.client.chat(user_input)
                    
                    # notify pet response is ready
                    self.pet_controller.notify_response_ready()
                    
                    # display response
                    console.print(f"[bold cyan]tulio:[/bold cyan] {response}")
                    
                except KeyboardInterrupt:
                    console.print("\nsee ya :3", style="cyan")
                    break
                except Exception as e:
                    self.pet_controller.notify_error()
                    console.print(f"error: {e}", style="red")
        
        finally:
            # cleanup
            if self.observer:
                self.observer.stop()
                self.observer.join()
            
            self._stop_desktop_pet()
            console.print("tulio stopped", style="dim")


@click.command()
@click.option('--pet', is_flag=True, help='start with desktop pet')
@click.option('--index-only', is_flag=True, help='run indexing only and exit')
def main(pet, index_only):
    """tulio - your personal ai assistant"""
    
    if index_only:
        # just run indexing and exit
        if not os.getenv('ANTHROPIC_API_KEY'):
            console.print("ANTHROPIC_API_KEY required", style="red")
            return
        
        try:
            client = TulioClaudeClient()
            console.print("indexing files...", style="cyan")
            result = client.index_files()
            console.print(f"{result}", style="green")
        except Exception as e:
            console.print(f"indexing failed: {e}", style="red")
        return
    
    # run terminal interface
    terminal = TulioTerminal()
    terminal.run(with_pet=pet)


if __name__ == "__main__":
    main()