"""Desktop announcement + automation helpers.

Everything here is optional: pyttsx3, gTTS/pygame, pyautogui and winsound are
each imported defensively, and the classes fall back to doing nothing when a
backend is missing. That is deliberate - a headless VPS has none of them.
"""

import logging

import json
import os
import tempfile
import threading
import time
from datetime import datetime

from helpers import safe_print as print

logger = logging.getLogger(__name__)

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import winsound
except ImportError:
    winsound = None

try:
    import gtts
    from gtts import gTTS
except ImportError:
    gtts = None
    gTTS = None

try:
    import pygame  # type: ignore
except ImportError:
    pygame = None


# Laptop Speaker Configuration
class LaptopSpeaker:
    def __init__(self):
        self.engine = None  # pyttsx3 engine (fallback)
        self.enabled = True  # Enable/disable announcements
        self.voice_rate = 150  # Speech rate (for pyttsx3)
        self.voice_volume = 0.9  # Volume level (for pyttsx3)
        self.voice_model = None  # Voice model for Vietnamese
        self.use_gtts = True  # Use gTTS for Vietnamese by default
        self.tts_language = 'vi'  # Language for gTTS
        
        # Initialize pygame mixer for gTTS audio playback
        if pygame is not None:
            try:
                pygame.mixer.init()
                print("Pygame mixer initialized successfully")
            except Exception as e:
                logger.exception("Error initializing pygame mixer")
                self.use_gtts = False
        else:
            print("Pygame not installed, disabling gTTS audio playback")
            self.use_gtts = False
        
    def initialize_engine(self):
        """Initialize text-to-speech engine with fallback options"""
        try:
            if self.use_gtts:
                # For gTTS, we don't need to initialize engine
                print("Using gTTS for Vietnamese text-to-speech")
                return True
            else:
                # Fallback to pyttsx3
                if pyttsx3 is None:
                    print("pyttsx3 is not installed, cannot use fallback")
                    return False
                self.engine = pyttsx3.init()
                
                # Lấy danh sách các voice có sẵn
                voices = self.engine.getProperty('voices')
                
                # Tìm voice tiếng Việt (Microsoft An, Microsoft HoaiMy, hoặc các voice khác)
                vietnamese_voice = None
                for voice in voices:
                    voice_id_lower = voice.id.lower() if voice.id else ''
                    voice_name_lower = voice.name.lower() if voice.name else ''
                    # Tìm chính xác hơn: ưu tiên Microsoft An và Microsoft HoaiMy
                    if ('microsoft an' in voice_name_lower or 'microsoft hoaimy' in voice_name_lower or
                        'vi_' in voice_id_lower or 'vietnamese' in voice_name_lower or 
                        'vietnam' in voice_name_lower or voice_name_lower.startswith('vi ')):
                        vietnamese_voice = voice
                        break
                
                # Nếu không tìm thấy voice tiếng Việt, sử dụng voice đầu tiên
                if vietnamese_voice:
                    self.engine.setProperty('voice', vietnamese_voice.id)
                    print(f"Using Vietnamese voice: {vietnamese_voice.name}")
                else:
                    # Sử dụng voice mặc định và hiển thị thông báo
                    default_voice = voices[0] if voices else None
                    if default_voice:
                        self.engine.setProperty('voice', default_voice.id)
                        print(f"Using default voice: {default_voice.name}")
                    print("Warning: No Vietnamese voice found. Using default voice.")
                    print("Available voices:")
                    for i, voice in enumerate(voices):
                        print(f"  {i+1}. {voice.name} (ID: {voice.id})")
                
                # Áp dụng cài đặt
                self.engine.setProperty('rate', self.voice_rate)
                self.engine.setProperty('volume', self.voice_volume)
                
                return True
        except Exception as e:
            logger.exception("Error initializing TTS engine")
            return False
    
    def speak_with_gtts(self, text, lang='vi'):
        """Speak text using Google Text-to-Speech (gTTS)"""
        if gTTS is None or pygame is None:
            print("gTTS or pygame is not installed. Trying pyttsx3 fallback if available.")
            if self.engine:
                try:
                    self.engine.say(text)
                    self.engine.runAndWait()
                except Exception as fallback_error:
                    logger.exception(f"Fallback TTS also failed: {fallback_error}")
            return
        try:
            print(f"Generating speech with gTTS: {text}")
            
            # Create gTTS object
            tts = gTTS(text=text, lang=lang, slow=False)
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
                temp_filename = temp_file.name
                tts.save(temp_filename)
            
            # Play the audio file
            try:
                pygame.mixer.music.load(temp_filename)
                pygame.mixer.music.play()
                
                # Wait for the audio to finish playing
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
                
                print("gTTS speech completed successfully")
            except Exception as e:
                logger.exception("Error playing gTTS audio")
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_filename)
                except OSError:
                    pass  # already gone, or still held open - nothing to do
                    
        except Exception as e:
            logger.exception("Error with gTTS")
            # Fallback to pyttsx3 if available
            if self.engine:
                try:
                    self.engine.say(text)
                    self.engine.runAndWait()
                except Exception as fallback_error:
                    logger.exception(f"Fallback TTS also failed: {fallback_error}")
    
    def play_notification_sound(self):
        """Play a simple notification sound"""
        if winsound is not None:
            try:
                # Play Windows notification sound
                winsound.MessageBeep(winsound.MB_OK)
            except Exception as e:
                logger.exception("Error playing notification sound")
        else:
            print("winsound is not available")
    
    def announce_order(self, order_items, customer_name="Khách", notes=None):
        """Announce order details through laptop speakers"""
        if not self.enabled:
            print("Speaker is disabled, skipping announcement")
            return
        
        # Prepare product details before starting thread (to avoid database context issues)
        product_details = []
        for item in order_items:
            try:
                product = Product.query.get(item['product_id'])
                if product:
                    product_details.append(f"{product.name}, số lượng {item['quantity']}")
                else:
                    product_details.append(f"Sản phẩm {item['product_id']}, số lượng {item['quantity']}")
            except Exception as e:
                logger.exception(f"Error getting product {item['product_id']}")
                product_details.append(f"Sản phẩm {item['product_id']}, số lượng {item['quantity']}")
        
        def speak_order():
            try:
                print("Starting order announcement...")
                # Play notification sound first
                self.play_notification_sound()
                
                # Prepare announcement message in Vietnamese
                message = f"Đơn hàng mới! {customer_name} đã đặt hàng: "
                message += ". ".join(product_details)
                message += ". Xin vui lòng chuẩn bị đơn hàng!"

                if notes:
                    message += f". Ghi chú: {notes}"
                
                print(f"Announcing: {message}")
                
                # Use gTTS for Vietnamese (better quality)
                if self.use_gtts:
                    self.speak_with_gtts(message, lang='vi')
                else:
                    # Fallback to pyttsx3
                    if not self.ensure_engine_ready():
                        print("Cannot initialize TTS engine for order announcement")
                        return
                    print(f"Engine status before speaking: {'ready' if self.engine else 'None'}")
                    self.engine.say(message)
                    self.engine.runAndWait()
                
                print("Order announcement completed successfully")
                
            except Exception as e:
                logger.exception("Error in speech announcement")
                # Thử khởi tạo lại engine cho lần sau
                self.engine = None
        
        # Run speech in separate thread to avoid blocking
        speech_thread = threading.Thread(target=speak_order)
        speech_thread.daemon = True
        speech_thread.start()
    
    def test_speaker(self):
        """Test the laptop speaker"""
        def speak_test():
            try:
                # Play test sound
                self.play_notification_sound()
                
                message = "Kiểm tra loa laptop. Hệ thống đã sẵn sàng."
                
                # Use gTTS if enabled, otherwise fallback to pyttsx3
                if self.use_gtts:
                    print("Testing with gTTS...")
                    self.speak_with_gtts(message, lang='vi')
                    return True
                else:
                    print("Testing with pyttsx3...")
                    # Đảm bảo engine sẵn sàng
                    if not self.ensure_engine_ready():
                        print("Cannot initialize TTS engine for test")
                        return False
                    
                    try:
                        self.engine.say(message)
                        self.engine.runAndWait()
                        return True
                    except Exception as engine_error:
                        logger.exception(f"pyttsx3 engine error: {engine_error}")
                        # Try to reinitialize engine
                        self.engine = None
                        if self.initialize_engine():
                            self.engine.say(message)
                            self.engine.runAndWait()
                            return True
                        return False
                    
            except Exception as e:
                logger.exception("Error testing speaker")
                # Thử khởi tạo lại engine cho lần sau
                self.engine = None
                return False
        
        test_thread = threading.Thread(target=speak_test)
        test_thread.daemon = True
        test_thread.start()
        return True
    
    def set_voice_settings(self, rate=None, volume=None):
        """Adjust voice settings"""
        print(f"Setting voice settings - rate: {rate}, volume: {volume}")
        print(f"Current engine status: {'exists' if self.engine else 'None'}")
        
        # Cập nhật giá trị nội bộ trước
        if rate is not None:
            self.voice_rate = rate
        if volume is not None:
            self.voice_volume = volume
        
        # Dừng engine hiện tại nếu có
        if self.engine:
            try:
                self.engine.stop()
            except Exception as e:
                logger.exception("Could not stop the TTS engine")
        
        # Khởi tạo lại engine với cài đặt mới
        print("Re-initializing engine with new settings...")
        self.engine = None
        
        if self.initialize_engine():
            print("Engine re-initialized successfully")
            # Áp dụng cài đặt cho engine mới
            try:
                if rate is not None:
                    self.engine.setProperty('rate', rate)
                    print(f"Rate set to: {rate}")
                if volume is not None:
                    self.engine.setProperty('volume', volume)
                    print(f"Volume set to: {volume}")
                print(f"Voice settings updated successfully: rate={rate}, volume={volume}")
            except Exception as e:
                logger.exception("Error applying settings to engine")
                # Thử lại một lần nữa
                self.engine = None
                if self.initialize_engine():
                    if rate is not None:
                        self.engine.setProperty('rate', rate)
                    if volume is not None:
                        self.engine.setProperty('volume', volume)
                    logger.exception("Settings applied after retry")
        else:
            print("Failed to re-initialize engine")
    
    def get_available_voices(self):
        """Get list of available voices"""
        try:
            if not self.engine:
                self.initialize_engine()
            
            voices = self.engine.getProperty('voices')
            voice_list = []
            
            for i, voice in enumerate(voices):
                voice_info = {
                    'id': voice.id,
                    'name': voice.name,
                    'languages': voice.languages,
                    'gender': voice.gender,
                    'index': i
                }
                voice_list.append(voice_info)
            
            return voice_list
        except Exception as e:
            logger.exception("Error getting voices")
            return []
    
    def set_voice_model(self, voice_id):
        """Set voice model by ID"""
        try:
            if not self.engine:
                if not self.initialize_engine():
                    return False
            
            voices = self.engine.getProperty('voices')
            for voice in voices:
                if voice.id == voice_id:
                    self.engine.setProperty('voice', voice.id)
                    self.voice_model = voice_id
                    print(f"Voice model set to: {voice.name}")
                    return True
            
            print(f"Voice ID {voice_id} not found")
            return False
        except Exception as e:
            logger.exception("Error setting voice model")
            return False
    
    def ensure_engine_ready(self):
        """Đảm bảo engine sẵn sàng để sử dụng"""
        if not self.engine:
            return self.initialize_engine()
        return True
    
    def toggle_enabled(self):
        """Enable/disable announcements"""
        self.enabled = not self.enabled
        return self.enabled

# Initialize Laptop Speaker
laptop_speaker = LaptopSpeaker()

# PyAutoGUI Automation Class
class AutomationController:
    def __init__(self):
        self.enabled = True
        self.auto_screenshot = True
        self.auto_minimize = False
        self.notification_position = "top-right"
        
        # Set pyautogui settings
        if pyautogui is not None:
            pyautogui.FAILSAFE = True  # Move mouse to corner to stop
            pyautogui.PAUSE = 0.5      # Pause between actions
        else:
            self.enabled = False
    
    def take_order_screenshot(self, order_id):
        """Take screenshot when order is placed"""
        if not self.auto_screenshot or pyautogui is None:
            return
            
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"order_{order_id}_{timestamp}.png"
            
            # Create screenshots directory if it doesn't exist
            screenshot_dir = "screenshots"
            if not os.path.exists(screenshot_dir):
                os.makedirs(screenshot_dir)
            
            filepath = os.path.join(screenshot_dir, filename)
            screenshot = pyautogui.screenshot()
            screenshot.save(filepath)
            
            print(f"Screenshot saved: {filepath}")
            return filepath
        except Exception as e:
            logger.exception("Error taking screenshot")
            return None
    
    def show_order_notification(self, order_id, customer_name, total_amount):
        """Show desktop notification for new order"""
        if not self.enabled:
            return
            
        def show_notification():
            try:
                # In ra console
                print(f"THONG BAO DON HANG MOI!")
                print(f"Ma don: #{order_id}")
                safe_customer_name = customer_name.encode('ascii', 'ignore').decode('ascii') if customer_name else 'Khách'
                print(f"Khách hàng: {safe_customer_name}")
                print(f"Tổng tiền: {total_amount:,.0f} VND")
                print("Vui long kiem tra he thong de xu ly don hang.")
                
                # Phát âm thanh thông báo
                if winsound is not None:
                    try:
                        winsound.MessageBeep(winsound.MB_OK)  # Phát âm thanh thông báo
                        time.sleep(0.5)
                        winsound.MessageBeep(winsound.MB_OK)  # Phát lần thứ hai để nhấn mạnh
                    except Exception as e:
                        logger.exception("Khong the phat am thanh thong bao")
                else:
                    print("winsound is not available")
                
                # Thêm desktop notification thực sự
                try:
                    # Thử mở cửa sổ thông báo đơn giản với webbrowser
                    import webbrowser

                    # Tạo HTML notification tạm thời
                    html_content = f'''
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>Đơn hàng mới!</title>
                        <meta charset="UTF-8">
                        <style>
                            body {{
                                font-family: Arial, sans-serif;
                                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                color: white;
                                text-align: center;
                                padding: 20px;
                                margin: 0;
                            }}
                            .container {{
                                max-width: 400px;
                                margin: 50px auto;
                                background: rgba(255,255,255,0.1);
                                padding: 30px;
                                border-radius: 15px;
                                backdrop-filter: blur(10px);
                                box-shadow: 0 8px 32px rgba(0,0,0,0.3);
                            }}
                            h1 {{
                                color: #FFD700;
                                margin-bottom: 20px;
                                font-size: 28px;
                            }}
                            .info {{
                                background: rgba(255,255,255,0.2);
                                padding: 15px;
                                border-radius: 10px;
                                margin: 10px 0;
                                font-size: 16px;
                            }}
                            .close-btn {{
                                background: #FF6B6B;
                                color: white;
                                border: none;
                                padding: 10px 20px;
                                border-radius: 5px;
                                cursor: pointer;
                                font-size: 16px;
                                margin-top: 20px;
                            }}
                            .close-btn:hover {{
                                background: #FF5252;
                            }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h1>🔔 ĐƠN HÀNG MỚI!</h1>
                            <div class="info">
                                <strong>Mã đơn:</strong> #{order_id}<br>
                                <strong>Khách hàng:</strong> {safe_customer_name}<br>
                                <strong>Tổng tiền:</strong> {total_amount:,.0f} VNĐ
                            </div>
                            <p style="margin: 20px 0;">
                                Vui lòng kiểm tra hệ thống để xử lý đơn hàng!
                            </p>
                            <button class="close-btn" onclick="window.close()">Đóng</button>
                        </div>
                        <script>
                            // Tự động đóng sau 30 giây
                            setTimeout(function(){{
                                window.close();
                            }}, 30000);
                            
                            // Phát âm thanh nếu có thể
                            try {{
                                const audio = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBSuBzvLZiTYIG2m98OScTgwOUarm7blmGgU7k9n1unEiBC13yO/eizEIHWq+8+OWT');
                                audio.play();
                            }} catch(e) {{}}
                        </script>
                    </body>
                    </html>
                    '''
                    
                    # Lưu file HTML tạm
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                        f.write(html_content)
                        temp_file = f.name
                    
                    # Mở trình duyệt với file HTML
                    webbrowser.open(f'file://{temp_file}')
                    print("HTML notification opened in browser")
                    
                    # Xóa file sau 30 giây
                    def cleanup_temp_file():
                        time.sleep(30)
                        try:
                            os.unlink(temp_file)
                        except OSError:
                            pass  # already gone - nothing to do
                    
                    cleanup_thread = threading.Thread(target=cleanup_temp_file)
                    cleanup_thread.daemon = True
                    cleanup_thread.start()
                    
                except Exception as e:
                    logger.exception("HTML notification error")
                    
                    # Fallback: Thử messagebox đơn giản
                    try:
                        import tkinter as tk
                        from tkinter import messagebox

                        def show_messagebox():
                            root = tk.Tk()
                            root.withdraw()
                            result = messagebox.showinfo(
                                "Đơn hàng mới!",
                                f"Mã đơn: #{order_id}\nKhách hàng: {safe_customer_name}\nTổng tiền: {total_amount:,.0f} VNĐ"
                            )
                            root.destroy()
                        
                        msg_thread = threading.Thread(target=show_messagebox)
                        msg_thread.daemon = True
                        msg_thread.start()
                        logger.exception("Messagebox notification sent")
                        
                    except Exception as e2:
                        logger.exception(f"Messagebox also failed: {e2}")
                        logger.exception("Only sound notification available")
                
            except Exception as e:
                logger.exception("Error showing notification")
        
        # Run in separate thread
        notification_thread = threading.Thread(target=show_notification)
        notification_thread.daemon = True
        notification_thread.start()
    
    def auto_open_admin_panel(self):
        """Automatically open admin panel when new order arrives"""
        if not self.enabled:
            return
            
        def open_admin():
            try:
                # Mở trình duyệt với admin panel
                import webbrowser
                admin_url = 'http://localhost:5000/admin'
                webbrowser.open(admin_url)
                print(f"Admin panel opened: {admin_url}")
                
                # Thử phương pháp pyautogui nếu cần
                if self.auto_minimize:
                    time.sleep(1)
                    pyautogui.hotkey('ctrl', 't')
                    time.sleep(0.5)
                    pyautogui.write(admin_url)
                    pyautogui.press('enter')
                    
            except Exception as e:
                logger.exception("Error opening admin panel")
        
        admin_thread = threading.Thread(target=open_admin)
        admin_thread.daemon = True
        admin_thread.start()
    
    def quick_order_print(self, order_id):
        """Quick print order details"""
        if pyautogui is None:
            print("pyautogui is not installed, cannot use quick print feature")
            return
        try:
            # Open order confirmation page
            pyautogui.hotkey('ctrl', 't')
            time.sleep(0.5)
            # Use localhost instead of hardcoded IP
            pyautogui.write(f'http://localhost:5000/order_confirmation/{order_id}')
            pyautogui.press('enter')
            time.sleep(2)
            
            # Print dialog
            pyautogui.hotkey('ctrl', 'p')
            time.sleep(0.5)
            pyautogui.press('enter')
            
        except Exception as e:
            logger.exception("Error printing order")
    
    def emergency_stop(self):
        """Emergency stop all automation"""
        self.enabled = False
        if pyautogui is not None:
            pyautogui.moveTo(0, 0)  # Trigger failsafe
        
    def get_screen_info(self):
        """Get screen information"""
        if pyautogui is None:
            return None
        try:
            return {
                'width': pyautogui.size().width,
                'height': pyautogui.size().height,
                'position': pyautogui.position()
            }
        except Exception as e:
            logger.exception("Could not read screen info")
            return None

# Initialize Automation Controller
automation_controller = AutomationController()

