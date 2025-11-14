import socket
import json
import threading
import time
import random
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class PetController:
    """controls desktop pet emotions via socket communication"""
    
    def __init__(self, port: int = 8765):
        self.port = port
        self.socket = None
        self.connected = False
        
        # emotion mappings for different contexts
        self.emotion_mappings = {
            'thinking': 'determined',
            'finished': 'excited', 
            'error': 'confused',
            'greeting': 'happy',
            'idle': 'default',
            'indexing': 'determined',
            'surprised': 'shocked',
            'mischievous': 'mischevious',
            'nervous': 'nervous',
            'annoyed': 'annoyed',
            'evil': 'evil',
            'dead': 'dead',
            'blank': 'blank-face'
        }
    
    def connect(self):
        """try to connect to desktop pet"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(1.0)
            self.socket.connect(('localhost', self.port))
            self.connected = True
            logger.info("connected to desktop pet")
            return True
        except Exception as e:
            logger.debug(f"could not connect to pet: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """disconnect from desktop pet"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        self.connected = False
    
    def send_emotion(self, emotion: str, duration: float = 3.0):
        """send emotion command to desktop pet"""
        if not self.connected:
            if not self.connect():
                return False
        
        try:
            command = {
                'action': 'set_emotion',
                'emotion': emotion,
                'duration': duration
            }
            message = json.dumps(command) + '\n'
            self.socket.send(message.encode('utf-8'))
            return True
        except Exception as e:
            logger.debug(f"error sending emotion: {e}")
            self.connected = False
            return False
    
    def set_emotion_for_context(self, context: str, duration: float = 3.0):
        """set emotion based on context"""
        emotion = self.emotion_mappings.get(context, 'default')
        return self.send_emotion(emotion, duration)
    
    def random_idle_emotion(self):
        """trigger random idle emotions occasionally"""
        idle_emotions = ['default', 'happy', 'mischevious', 'nervous']
        emotion = random.choice(idle_emotions)
        return self.send_emotion(emotion, duration=5.0)
    
    def notify_user_input(self):
        """user started typing/sent message"""
        self.set_emotion_for_context('thinking', duration=1.0)
    
    def notify_response_ready(self):
        """response is ready"""
        self.set_emotion_for_context('finished', duration=2.0)
    
    def notify_error(self):
        """an error occurred"""
        self.set_emotion_for_context('error', duration=3.0)
    
    def notify_indexing(self):
        """file indexing in progress"""
        self.set_emotion_for_context('indexing', duration=5.0)
    
    def notify_greeting(self):
        """show greeting emotion"""
        self.set_emotion_for_context('greeting', duration=3.0)


class IdleEmotionManager:
    """manages random idle emotions"""
    
    def __init__(self, pet_controller: PetController):
        self.pet_controller = pet_controller
        self.running = False
        self.thread = None
    
    def start(self):
        """start idle emotion thread"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._idle_loop)
            self.thread.daemon = True
            self.thread.start()
    
    def stop(self):
        """stop idle emotion thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
    
    def _idle_loop(self):
        """main idle emotion loop"""
        while self.running:
            # wait random time between 30-120 seconds
            wait_time = random.randint(30, 120)
            
            for _ in range(wait_time):
                if not self.running:
                    return
                time.sleep(1)
            
            # trigger random emotion if still connected
            if self.pet_controller.connected:
                self.pet_controller.random_idle_emotion()