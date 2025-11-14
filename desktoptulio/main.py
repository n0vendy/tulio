#!/usr/bin/env python3
"""
tulio desktop pet - animated companion with emotions
"""

import sys
import os
import json
import socket
import threading
import random
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QLabel, QWidget
from PyQt5.QtCore import QTimer, Qt, QPropertyAnimation, QRect, QEasingCurve, QThread, pyqtSignal
from PyQt5.QtGui import QMovie, QPainter


class EmotionSocketServer(QThread):
    """socket server to receive emotion commands"""
    emotion_received = pyqtSignal(str, float)
    
    def __init__(self, port=8765):
        super().__init__()
        self.port = port
        self.running = False
        self.server_socket = None
    
    def run(self):
        """main server loop"""
        self.running = True
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('localhost', self.port))
            self.server_socket.listen(1)
            self.server_socket.settimeout(1.0)
            
            print(f"pet server listening on port {self.port}")
            
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    self.handle_client(client_socket)
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"server error: {e}")
                    break
        
        except Exception as e:
            print(f"failed to start server: {e}")
        
        finally:
            if self.server_socket:
                self.server_socket.close()
    
    def handle_client(self, client_socket):
        """handle client connection"""
        try:
            while self.running:
                data = client_socket.recv(1024)
                if not data:
                    break
                
                try:
                    message = data.decode('utf-8').strip()
                    command = json.loads(message)
                    
                    if command.get('action') == 'set_emotion':
                        emotion = command.get('emotion', 'default')
                        duration = command.get('duration', 3.0)
                        self.emotion_received.emit(emotion, duration)
                
                except json.JSONDecodeError:
                    print(f"invalid json: {message}")
        
        except Exception as e:
            print(f"client error: {e}")
        
        finally:
            client_socket.close()
    
    def stop(self):
        """stop the server"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()


class TulioDesktopPet(QWidget):
    """animated desktop pet with emotions"""
    
    def __init__(self):
        super().__init__()
        
        # emotion state
        self.current_emotion = 'default'
        self.default_emotion = 'default'
        self.animations = {}
        self.current_movie = None
        
        # load animations
        self.load_animations()
        
        # initialize ui
        self.init_ui()
        
        # setup socket server for emotion control
        self.emotion_server = EmotionSocketServer()
        self.emotion_server.emotion_received.connect(self.set_emotion)
        self.emotion_server.start()
        
        # setup timers
        self.init_timers()
        
        # start with default emotion
        self.set_emotion('default')
    
    def load_animations(self):
        """load all animation files"""
        animations_dir = Path(__file__).parent.parent / "animations"
        
        if not animations_dir.exists():
            print("animations folder not found!")
            return
        
        for gif_file in animations_dir.glob("*.gif"):
            emotion_name = gif_file.stem
            self.animations[emotion_name] = str(gif_file)
            print(f"loaded animation: {emotion_name}")
    
    def init_ui(self):
        """initialize the ui"""
        # set window properties
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint | 
            Qt.WindowDoesNotAcceptFocus |
            Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # create label for animations
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        
        # set size
        self.resize(128, 128)
        self.label.resize(128, 128)
        
        # position on screen (bottom right corner)
        screen = QApplication.desktop().screenGeometry()
        self.move(screen.width() - 170, screen.height() - 200)
        
        # make clickable for interaction
        self.label.mousePressEvent = self.on_click
    
    def init_timers(self):
        """initialize timers for animations and idle behavior"""
        # timer to return to default emotion
        self.emotion_timer = QTimer()
        self.emotion_timer.setSingleShot(True)
        self.emotion_timer.timeout.connect(self.return_to_default)
        
        # timer for idle animations
        self.idle_timer = QTimer()
        self.idle_timer.timeout.connect(self.random_idle_emotion)
        self.idle_timer.start(random.randint(45000, 90000))  # 45-90 seconds
        
        # movement animation
        self.bounce_animation = QPropertyAnimation(self, b"geometry")
        self.bounce_animation.setDuration(2000)
        self.bounce_animation.setEasingCurve(QEasingCurve.InOutSine)
        
        # gentle movement timer (disabled)
        # self.move_timer = QTimer()
        # self.move_timer.timeout.connect(self.gentle_move)
        # self.move_timer.start(random.randint(8000, 15000))  # 8-15 seconds
    
    def set_emotion(self, emotion: str, duration: float = 3.0):
        """set current emotion animation"""
        if emotion not in self.animations:
            print(f"emotion '{emotion}' not found, using default")
            emotion = 'default'
        
        if emotion not in self.animations:
            print("no animations available!")
            return
        
        self.current_emotion = emotion
        
        # stop current animation
        if self.current_movie:
            self.current_movie.stop()
        
        # load and start new animation
        self.current_movie = QMovie(self.animations[emotion])
        # scale animation to 128x128
        self.current_movie.setScaledSize(self.label.size())
        self.label.setMovie(self.current_movie)
        self.current_movie.start()
        
        print(f"set emotion: {emotion} for {duration}s")
        
        # set timer to return to default (unless it's already default)
        if emotion != self.default_emotion and duration > 0:
            self.emotion_timer.stop()
            self.emotion_timer.start(int(duration * 1000))
    
    def return_to_default(self):
        """return to default emotion"""
        if self.current_emotion != self.default_emotion:
            self.set_emotion(self.default_emotion, duration=0)
    
    def random_idle_emotion(self):
        """show random idle emotion"""
        # only if currently showing default emotion
        if self.current_emotion == self.default_emotion:
            idle_emotions = ['happy', 'mischevious', 'nervous']
            available_emotions = [e for e in idle_emotions if e in self.animations]
            
            if available_emotions:
                emotion = random.choice(available_emotions)
                self.set_emotion(emotion, duration=random.uniform(2.0, 5.0))
        
        # reset idle timer
        self.idle_timer.start(random.randint(45000, 90000))
    
    def gentle_move(self):
        """perform gentle movement"""
        current_rect = self.geometry()
        
        # small random movement
        dx = random.randint(-15, 15)
        dy = random.randint(-8, 8)
        
        # keep on screen
        screen = QApplication.desktop().screenGeometry()
        new_x = max(10, min(screen.width() - self.width() - 10, current_rect.x() + dx))
        new_y = max(10, min(screen.height() - self.height() - 10, current_rect.y() + dy))
        
        new_rect = QRect(new_x, new_y, current_rect.width(), current_rect.height())
        
        self.bounce_animation.setStartValue(current_rect)
        self.bounce_animation.setEndValue(new_rect)
        self.bounce_animation.start()
        
        # reset movement timer
        self.move_timer.start(random.randint(8000, 15000))
    
    def on_click(self, event):
        """handle click events"""
        if event.button() == Qt.LeftButton:
            # show excited emotion on click
            if 'excited' in self.animations:
                self.set_emotion('excited', duration=2.0)
            # removed fallback attention animation
    
    def attention_animation(self):
        """quick scale animation for attention"""
        current_rect = self.geometry()
        bigger_rect = QRect(
            current_rect.x() - 5,
            current_rect.y() - 5,
            current_rect.width() + 10,
            current_rect.height() + 10
        )
        
        # animate bigger then back to normal
        self.bounce_animation.setDuration(300)
        self.bounce_animation.setStartValue(current_rect)
        self.bounce_animation.setEndValue(bigger_rect)
        
        self.bounce_animation.finished.connect(self.return_to_normal)
        self.bounce_animation.start()
    
    def return_to_normal(self):
        """return to normal size after attention animation"""
        current_rect = self.geometry()
        normal_rect = QRect(
            current_rect.x() + 5,
            current_rect.y() + 5,
            current_rect.width() - 10,
            current_rect.height() - 10
        )
        
        self.bounce_animation.finished.disconnect(self.return_to_normal)
        self.bounce_animation.setStartValue(current_rect)
        self.bounce_animation.setEndValue(normal_rect)
        self.bounce_animation.setDuration(200)
        self.bounce_animation.start()
        
        # reset duration for regular moves
        self.bounce_animation.setDuration(2000)
    
    def closeEvent(self, event):
        """handle close event"""
        self.emotion_timer.stop()
        self.idle_timer.stop()
        # self.move_timer.stop()  # disabled
        
        if self.current_movie:
            self.current_movie.stop()
        
        self.emotion_server.stop()
        self.emotion_server.wait()
        
        event.accept()


def main():
    """main entry point for desktop pet"""
    app = QApplication(sys.argv)
    
    # create and show the pet
    pet = TulioDesktopPet()
    pet.show()
    print("tulio desktop pet started! >")
    print("click on tulio for interaction")
    
    # run the application
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()