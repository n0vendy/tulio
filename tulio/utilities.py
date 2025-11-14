import os
import requests
import json
from pathlib import Path
from typing import Dict, Any, Optional
from rich.console import Console
from rich.prompt import Confirm
import logging

logger = logging.getLogger(__name__)
console = Console()


class TulioUtilities:
    """utility functions for tulio's enhanced capabilities"""
    
    def __init__(self):
        self.weather_api_key = os.getenv('WEATHER_API_KEY')
    
    def get_weather(self, city: str = "San Francisco") -> Dict[str, Any]:
        """fetch current weather data"""
        if not self.weather_api_key:
            # try free weather service
            try:
                url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid=demo&units=metric"
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "city": data.get("name", city),
                        "temperature": data["main"]["temp"],
                        "description": data["weather"][0]["description"],
                        "humidity": data["main"]["humidity"]
                    }
            except:
                pass
            
            # fallback to wttr.in service
            try:
                url = f"https://wttr.in/{city}?format=j1"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    current = data["current_condition"][0]
                    return {
                        "success": True,
                        "city": city,
                        "temperature": f"{current['temp_C']}°C",
                        "description": current["weatherDesc"][0]["value"].lower(),
                        "humidity": f"{current['humidity']}%"
                    }
            except Exception as e:
                logger.error(f"weather fetch error: {e}")
                return {
                    "success": False,
                    "error": "couldn't fetch weather data. you might need to set WEATHER_API_KEY"
                }
    
    def create_directory(self, dir_path: str) -> Dict[str, Any]:
        """create a directory with user confirmation"""
        try:
            path = Path(dir_path).expanduser()
            
            if path.exists():
                return {
                    "success": False,
                    "error": f"directory already exists: {path}"
                }
            
            # ask for confirmation
            console.print(f"🗂️  create directory: {path}", style="yellow")
            if Confirm.ask("proceed?"):
                path.mkdir(parents=True, exist_ok=True)
                return {
                    "success": True,
                    "message": f"created directory: {path}"
                }
            else:
                return {
                    "success": False,
                    "error": "directory creation cancelled by user"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"failed to create directory: {e}"
            }
    
    def write_file(self, file_path: str, content: str, overwrite: bool = False) -> Dict[str, Any]:
        """write content to a file with user approval"""
        try:
            path = Path(file_path).expanduser()
            
            # check if file exists
            if path.exists() and not overwrite:
                console.print(f"📄 file exists: {path}", style="yellow")
                console.print(f"current size: {path.stat().st_size} bytes", style="dim")
                if not Confirm.ask("overwrite existing file?"):
                    return {
                        "success": False,
                        "error": "file write cancelled by user"
                    }
            
            # show preview of content
            preview = content[:200] + "..." if len(content) > 200 else content
            console.print(f"📝 write to: {path}", style="yellow")
            console.print(f"content preview:\n{preview}", style="dim")
            console.print(f"total length: {len(content)} characters", style="dim")
            
            if Confirm.ask("write this content?"):
                # create parent directory if needed
                path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                return {
                    "success": True,
                    "message": f"wrote {len(content)} characters to {path}"
                }
            else:
                return {
                    "success": False,
                    "error": "file write cancelled by user"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"failed to write file: {e}"
            }
    
    def move_file(self, source_path: str, dest_path: str) -> Dict[str, Any]:
        """move a file with user confirmation"""
        try:
            source = Path(source_path).expanduser()
            dest = Path(dest_path).expanduser()
            
            if not source.exists():
                return {
                    "success": False,
                    "error": f"source file not found: {source}"
                }
            
            if dest.exists():
                console.print(f"📄 destination exists: {dest}", style="yellow")
                if not Confirm.ask("overwrite destination?"):
                    return {
                        "success": False,
                        "error": "file move cancelled by user"
                    }
            
            console.print(f"📦 move: {source} -> {dest}", style="yellow")
            if Confirm.ask("proceed with move?"):
                # create destination directory if needed
                dest.parent.mkdir(parents=True, exist_ok=True)
                
                source.rename(dest)
                return {
                    "success": True,
                    "message": f"moved {source.name} to {dest}"
                }
            else:
                return {
                    "success": False,
                    "error": "file move cancelled by user"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"failed to move file: {e}"
            }