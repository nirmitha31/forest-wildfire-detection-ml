from flask import Flask, render_template, Response, jsonify
import cv2
import numpy as np
from datetime import datetime
import threading
from collections import deque
import requests
import time
import pandas as pd
from io import StringIO

app = Flask(__name__)

# ==================== CONFIGURATION ====================
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = ''  # Replace with your bot token
TELEGRAM_CHAT_ID = [']     # Replace with your chat ID

# Google Sheets Configuration (Public sharing link)
# Format: https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/export?format=csv&gid=0
GOOGLE_SHEET_CSV_URL = 'https://docs.google.com/spreadsheets/d/1BiTp2Ha8MnJdPwMjsAIB4pDQwFwwA-U0BMnD2b04xc0/export?format=csv&gid=0'

# ==================== GLOBAL VARIABLES ====================
camera = None
fire_detected = False
last_detection_time = None
detection_count = 0
sensor_status = {
    'fire_sensor': False,
    'smoke_detector': False,
    'temperature_sensor': False,
    'all_sensors_active': False,
    'last_update': None
}
alert_sent = False
last_alert_time = None
ALERT_COOLDOWN = 300  # 5 minutes cooldown between alerts

# Current location (fetched live)
current_location = {
    'latitude': None,
    'longitude': None,
    'address': 'Fetching location...',
    'city': None,
    'country': None,
    'last_update': None,
    'method': None,
    'accuracy': None
}

# ==================== LOCATION SERVICES ====================
class LocationService:
    def __init__(self):
        self.latitude = None
        self.longitude = None
        self.address = None
        self.city = None
        self.country = None
        self.method = None
        
    def get_address_from_coords(self, lat, lon):
        """Get human-readable address from coordinates using reverse geocoding"""
        try:
            # Using Nominatim (OpenStreetMap) - Free, no API key needed
            url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
            headers = {'User-Agent': 'FireDetectionSystem/1.0'}
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                address_parts = data.get('address', {})
                
                # Build readable address
                address_components = []
                
                # Add specific location details
                if 'road' in address_parts:
                    address_components.append(address_parts['road'])
                if 'suburb' in address_parts:
                    address_components.append(address_parts['suburb'])
                elif 'neighbourhood' in address_parts:
                    address_components.append(address_parts['neighbourhood'])
                
                # Add city
                city = (address_parts.get('city') or 
                       address_parts.get('town') or 
                       address_parts.get('village') or
                       address_parts.get('municipality'))
                if city:
                    address_components.append(city)
                    self.city = city
                
                # Add state/region
                if 'state' in address_parts:
                    address_components.append(address_parts['state'])
                
                # Add country
                if 'country' in address_parts:
                    self.country = address_parts['country']
                    address_components.append(self.country)
                
                self.address = ', '.join(address_components) if address_components else data.get('display_name', 'Unknown location')
                return True
                
        except Exception as e:
            print(f"Reverse geocoding failed: {e}")
            self.address = f"Location: {lat:.4f}, {lon:.4f}"
        
        return False
    
    def get_location_from_ip(self):
        """Get approximate location using IP geolocation"""
        try:
            # Using ipapi.co (free, no API key needed)
            response = requests.get('https://ipapi.co/json/', timeout=5)
            if response.status_code == 200:
                data = response.json()
                self.latitude = data.get('latitude')
                self.longitude = data.get('longitude')
                self.city = data.get('city')
                self.country = data.get('country_name')
                self.method = 'ip'
                
                if self.latitude and self.longitude:
                    # Build address from IP data
                    address_parts = []
                    if self.city:
                        address_parts.append(self.city)
                    if data.get('region'):
                        address_parts.append(data.get('region'))
                    if self.country:
                        address_parts.append(self.country)
                    
                    self.address = ', '.join(address_parts) if address_parts else f"{self.latitude:.4f}, {self.longitude:.4f}"
                    
                    print(f"✓ Location from IP: {self.address}")
                    return True
        except Exception as e:
            print(f"IP geolocation failed: {e}")
        
        # Fallback to another service
        try:
            response = requests.get('http://ip-api.com/json/', timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    self.latitude = data.get('lat')
                    self.longitude = data.get('lon')
                    self.city = data.get('city')
                    self.country = data.get('country')
                    self.method = 'ip'
                    
                    if self.latitude and self.longitude:
                        address_parts = []
                        if self.city:
                            address_parts.append(self.city)
                        if data.get('regionName'):
                            address_parts.append(data.get('regionName'))
                        if self.country:
                            address_parts.append(self.country)
                        
                        self.address = ', '.join(address_parts) if address_parts else f"{self.latitude:.4f}, {self.longitude:.4f}"
                        
                        print(f"✓ Location from IP (fallback): {self.address}")
                        return True
        except Exception as e:
            print(f"Fallback IP geolocation failed: {e}")
        
        return False
    
    def get_current_location(self):
        """Get current location"""
        global current_location
        
        # Try IP-based geolocation
        if self.get_location_from_ip():
            current_location['latitude'] = self.latitude
            current_location['longitude'] = self.longitude
            current_location['address'] = self.address
            current_location['city'] = self.city
            current_location['country'] = self.country
            current_location['method'] = self.method
            current_location['last_update'] = datetime.now()
            return True
        
        return False

# ==================== GOOGLE SHEETS INTEGRATION ====================
class SensorDataReader:
    def __init__(self, csv_url):
        self.csv_url = csv_url
        self.connected = False
        
    def read_sensor_data(self):
        """Read sensor data from publicly shared Google Sheet"""
        global sensor_status
        
        try:
            # Fetch CSV data from Google Sheets
            response = requests.get(self.csv_url, timeout=10)
            response.raise_for_status()
            
            # Parse CSV data
            csv_data = StringIO(response.text)
            df = pd.read_csv(csv_data)
            
            # Get the latest row (most recent data)
            if len(df) > 0:
                latest_row = df.iloc[-1]  # Get last row
                
                # Read sensor values from the row
                # Try to get columns by index (more reliable than column names)
                try:
                    # Assuming columns: Date, Time, fire, smoke, temperature
                    # Get values starting from column index 2 (third column)
                    fire_value = latest_row.iloc[2] if len(latest_row) > 2 else 0
                    smoke_value = latest_row.iloc[3] if len(latest_row) > 3 else 0
                    temp_value = latest_row.iloc[4] if len(latest_row) > 4 else 0
                    
                    # Convert to boolean: 1 = True (detected), 0 = False (not detected)
                    # Handle various formats (int, float, string)
                    def to_bool(val):
                        try:
                            # Convert to string first, then strip whitespace
                            str_val = str(val).strip()
                            if str_val == '' or str_val.lower() == 'nan':
                                return False
                            # Try to convert to int
                            int_val = int(float(str_val))
                            return int_val == 1
                        except:
                            return False
                    
                    sensor_status['fire_sensor'] = to_bool(fire_value)
                    sensor_status['smoke_detector'] = to_bool(smoke_value)
                    sensor_status['temperature_sensor'] = to_bool(temp_value)
                    
                    # All sensors active only if ALL three are 1
                    sensor_status['all_sensors_active'] = (
                        sensor_status['fire_sensor'] and 
                        sensor_status['smoke_detector'] and 
                        sensor_status['temperature_sensor']
                    )
                    sensor_status['last_update'] = datetime.now()
                    
                    self.connected = True
                    
                    # Debug print
                    print(f"Sensor Update - Fire: {sensor_status['fire_sensor']}, "
                          f"Smoke: {sensor_status['smoke_detector']}, "
                          f"Temp: {sensor_status['temperature_sensor']}")
                    
                    return True
                    
                except Exception as e:
                    print(f"Error parsing sensor values: {e}")
                    self.connected = False
                    return False
            
        except Exception as e:
            print(f"Error reading sensor data: {e}")
            self.connected = False
            return False

# ==================== TELEGRAM INTEGRATION ====================
class TelegramAlert:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
    
    def send_message(self, message):
        """Send text message to Telegram"""
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            response = requests.post(url, data=data, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"Error sending Telegram message: {e}")
            return False
    
    def send_location(self, latitude, longitude, message=""):
        """Send location to Telegram"""
        try:
            url = f"{self.base_url}/sendLocation"
            data = {
                'chat_id': self.chat_id,
                'latitude': latitude,
                'longitude': longitude
            }
            response = requests.post(url, data=data, timeout=10)
            
            if message and response.status_code == 200:
                self.send_message(message)
            
            return response.status_code == 200
        except Exception as e:
            print(f"Error sending Telegram location: {e}")
            return False
    
    def send_fire_alert(self, latitude, longitude, address, sensor_data, location_method):
        """Send comprehensive fire alert with location"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        location_info = f"📍 Location Method: {location_method.upper()}"
        if location_method == 'browser':
            location_info += " (High Accuracy GPS)"
        elif location_method == 'ip':
            location_info += " (IP-based, Approximate)"
        
        message = f"""
🚨🚨🚨 <b>FIRE ALERT!</b> 🚨🚨🚨

⏰ <b>Time:</b> {timestamp}

🔥 <b>VERIFIED BY BOTH SYSTEMS:</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ <b>Computer Vision:</b> FIRE DETECTED
✅ <b>Fire Sensor:</b> DETECTED (Hardware)
✅ <b>Smoke Detector:</b> DETECTED (Hardware)
✅ <b>Temperature Sensor:</b> DETECTED (Hardware)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📍 <b>LOCATION INFORMATION:</b>
{location_info}
📌 <b>Address:</b> {address}
🌐 <b>Coordinates:</b> {latitude}, {longitude}

⚠️ <b>STATUS:</b> CRITICAL - IMMEDIATE ACTION REQUIRED!

🔗 <b>View on Google Maps:</b>
https://www.google.com/maps?q={latitude},{longitude}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This alert was triggered because BOTH computer vision AND all hardware sensors detected fire simultaneously.
"""
        
        # Send message first
        msg_success = self.send_message(message)
        
        # Then send location pin
        loc_success = self.send_location(latitude, longitude)
        
        return msg_success and loc_success

# ==================== ULTRA STRICT FIRE DETECTION ====================
class FireDetector:
    def __init__(self):
        self.prev_gray = None
        self.detection_history = deque(maxlen=10)
        self.region_tracker = {}
        self.frame_count = 0
        
    def detect_fire_color_strict(self, frame):
        """VERY strict multi-colorspace fire detection"""
        
        # Convert to color spaces
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
        b, g, r = cv2.split(frame)
        h, s, v = cv2.split(hsv)
        y, cr, cb = cv2.split(ycrcb)
        
        # STRICT Rule 1: RGB - R > G > B (fire is red-orange-yellow)
        mask_rgb = cv2.bitwise_and(
            cv2.compare(r, g, cv2.CMP_GT),
            cv2.compare(g, b, cv2.CMP_GT)
        )
        
        # STRICT Rule 2: R must be significantly higher
        mask_r_high = cv2.threshold(r, 130, 255, cv2.THRESH_BINARY)[1]
        
        # STRICT Rule 2: HSV - NARROW range for real fire
        mask_h = cv2.inRange(h, 0, 30)  # Slightly wider: 0-30 (was 0-25)
        mask_s = cv2.threshold(s, 70, 255, cv2.THRESH_BINARY)[1]  # Lowered from 80
        mask_v = cv2.threshold(v, 120, 255, cv2.THRESH_BINARY)[1]  # Lowered from 130
        mask_hsv = cv2.bitwise_and(mask_h, cv2.bitwise_and(mask_s, mask_v))
        
        # STRICT Rule 4: YCrCb - Fire has specific YCrCb signature
        mask_y = cv2.threshold(y, 120, 255, cv2.THRESH_BINARY)[1]
        mask_cr = cv2.threshold(cr, 150, 255, cv2.THRESH_BINARY)[1]
        mask_cb = cv2.threshold(cb, 120, 255, cv2.THRESH_BINARY_INV)[1]
        mask_ycrcb = cv2.bitwise_and(mask_y, cv2.bitwise_and(mask_cr, mask_cb))
        
        # Combine ALL masks - ALL must pass
        fire_mask = cv2.bitwise_and(mask_rgb, mask_r_high)
        fire_mask = cv2.bitwise_and(fire_mask, mask_hsv)
        fire_mask = cv2.bitwise_and(fire_mask, mask_ycrcb)
        
        # Aggressive morphological filtering
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        fire_mask = cv2.morphologyEx(fire_mask, cv2.MORPH_OPEN, kernel, iterations=3)
        fire_mask = cv2.morphologyEx(fire_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        fire_mask = cv2.erode(fire_mask, kernel, iterations=1)
        
        return fire_mask
    
    def calculate_optical_flow_strict(self, current_gray):
        """Calculate optical flow - fire MUST have significant motion"""
        if self.prev_gray is None:
            self.prev_gray = current_gray
            return None, 0
        
        try:
            # Calculate dense optical flow
            flow = cv2.calcOpticalFlowFarneback(
                self.prev_gray, current_gray, None,
                pyr_scale=0.5, levels=3, winsize=15,
                iterations=3, poly_n=5, poly_sigma=1.2, flags=0
            )
            
            # Calculate motion magnitude
            magnitude = np.sqrt(flow[..., 0]**2 + flow[..., 1]**2)
            
            self.prev_gray = current_gray
            
            return magnitude, np.mean(magnitude)
        except:
            self.prev_gray = current_gray
            return None, 0
    
    def validate_fire_region_ultra_strict(self, roi, contour, motion_magnitude, region_id):
        """ULTRA STRICT validation - very few things pass"""
        if roi.size == 0:
            return False, 0
        
        try:
            h, w = roi.shape[:2]
            area = cv2.contourArea(contour)
            
            # Get statistics
            hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            b, g, r = cv2.split(roi)
            
            avg_hue = np.mean(hsv_roi[:, :, 0])
            avg_sat = np.mean(hsv_roi[:, :, 1])
            avg_val = np.mean(hsv_roi[:, :, 2])
            
            avg_r = np.mean(r)
            avg_g = np.mean(g)
            avg_b = np.mean(b)
            
            # ========== ULTRA STRICT CHECKS ==========
            
            # Check 1: Hue MUST be in fire range (slightly wider)
            if not (0 <= avg_hue <= 30):  # Increased from 25
                return False, 0
            
            # Check 2: Saturation MUST be high (vivid color)
            if avg_sat < 70:  # Lowered from 80
                return False, 0
            
            # Check 3: Brightness MUST be high
            if avg_val < 120:  # Lowered from 130
                return False, 0
            
            # Check 4: R must STRONGLY dominate
            if not (avg_r > avg_g + 20 and avg_g > avg_b + 10):  # Lowered from +30 and +20
                return False, 0
            
            # Check 5: Red channel must be very high
            if avg_r < 120:  # Lowered from 130
                return False, 0
            
            # Check 6: Size must be appropriate
            if not (300 < area < 35000):  # Reduced min from 600 to 300
                return False, 0
            
            # Check 7: CRITICAL - Region MUST have significant motion
            if motion_magnitude is not None:
                x, y, bw, bh = cv2.boundingRect(contour)
                roi_motion = motion_magnitude[y:min(y+bh, motion_magnitude.shape[0]), 
                                             x:min(x+bw, motion_magnitude.shape[1])]
                if roi_motion.size > 0:
                    mean_motion = np.mean(roi_motion)
                    # MUST have motion (flickering)
                    if mean_motion < 0.7:  # Lowered from 1.0
                        return False, 0
                else:
                    return False, 0
            else:
                return False, 0
            
            # Check 8: Shape irregularity
            perimeter = cv2.arcLength(contour, True)
            if perimeter > 0:
                circularity = (4 * np.pi * area) / (perimeter ** 2)
                if circularity > 0.75:  # Too circular, likely not fire
                    return False, 0
            
            # Check 9: Brightness variation within region
            std_brightness = np.std(hsv_roi[:, :, 2])
            if std_brightness < 8:  # Lowered from 10
                return False, 0
            
            # Check 10: TEMPORAL TRACKING - Track region over multiple frames
            if region_id not in self.region_tracker:
                self.region_tracker[region_id] = {
                    'brightness_history': deque(maxlen=8),
                    'area_history': deque(maxlen=8),
                    'first_seen': self.frame_count
                }
            
            tracker = self.region_tracker[region_id]
            tracker['brightness_history'].append(avg_val)
            tracker['area_history'].append(area)
            
            # Must be tracked for at least 4 frames (lowered from 5)
            frames_tracked = self.frame_count - tracker['first_seen']
            if frames_tracked < 4:
                return False, 0
            
            # Check 11: Temporal variation (flickering over time)
            if len(tracker['brightness_history']) >= 4:  # Lowered from 5
                brightness_std = np.std(list(tracker['brightness_history']))
                area_std = np.std(list(tracker['area_history']))
                area_mean = np.mean(list(tracker['area_history']))
                
                # Must have significant temporal variation
                if brightness_std < 4:  # Lowered from 5
                    return False, 0
                
                if area_mean > 0:
                    area_variation = (area_std / area_mean) * 100
                    if area_variation < 6:  # Lowered from 8%
                        return False, 0
            else:
                return False, 0
            
            # If ALL checks pass, it's likely real fire
            confidence = 85
            
            return True, confidence
            
        except Exception as e:
            return False, 0
    
    def detect_fire(self, frame):
        """Ultra strict fire detection"""
        global fire_detected, last_detection_time, detection_count
        
        self.frame_count += 1
        
        # Get fire color mask with STRICT rules
        fire_mask = self.detect_fire_color_strict(frame)
        
        # Check if there's ANY fire-colored pixels
        fire_pixels = cv2.countNonZero(fire_mask)
        
        # If no fire colors, skip processing
        if fire_pixels < 100:  # Reduced from 200 to 100
            # Clean up old tracked regions
            if self.frame_count % 30 == 0:
                self.region_tracker.clear()
            
            self.draw_sensor_status(frame)
            self.draw_location_status(frame)
            
            status_text = "STATUS: Monitoring..."
            status_color = (0, 255, 0)
            
            cv2.rectangle(frame, (5, 5), (450, 45), (0, 0, 0), -1)
            cv2.rectangle(frame, (5, 5), (450, 45), status_color, 2)
            cv2.putText(frame, status_text, (15, 32),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cv2.rectangle(frame, (5, frame.shape[0] - 35), (300, frame.shape[0] - 5), (0, 0, 0), -1)
            cv2.putText(frame, timestamp, (15, frame.shape[0] - 15),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            return frame
        
        # Calculate optical flow for motion detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        motion_magnitude, mean_motion = self.calculate_optical_flow_strict(gray)
        
        # Find contours
        contours, _ = cv2.findContours(fire_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        fire_found = False
        valid_detections = []
        
        for idx, contour in enumerate(contours):
            area = cv2.contourArea(contour)
            
            if area < 400 or area > 30000:  # Reduced from 800 to 400
                continue
            
            x, y, w, h = cv2.boundingRect(contour)
            
            # Aspect ratio check
            aspect_ratio = float(w) / h if h > 0 else 0
            if aspect_ratio > 3.0 or aspect_ratio < 0.25:
                continue
            
            roi = frame[y:y+h, x:x+w]
            
            if roi.size == 0:
                continue
            
            # Create region ID for tracking
            region_id = f"{x//40}_{y//40}"
            
            # ULTRA STRICT validation
            is_fire, confidence = self.validate_fire_region_ultra_strict(
                roi, contour, motion_magnitude, region_id
            )
            
            if is_fire and confidence >= 60:  # Reduced from 80 to 60
                fire_found = True
                valid_detections.append((x, y, w, h, confidence))
        
        # Draw detections
        for x, y, w, h, conf in valid_detections:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 3)
            
            cv2.rectangle(frame, (x, y - 35), (x + 250, y), (0, 0, 255), -1)
            cv2.putText(frame, 'FIRE DETECTED!', (x + 5, y - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            cv2.putText(frame, f'Verified', (x + 5, y + h + 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
        
        # STRICT temporal verification - need 5 out of 10 frames (lowered from 7)
        self.detection_history.append(1 if fire_found else 0)
        persistent_fire = sum(self.detection_history) >= 2  # Reduced from 5 to 2 frames
        
        # Update global status with auto-reset logic

        if fire_found and persistent_fire:
            fire_detected = True
            last_detection_time = datetime.now()
            detection_count += 1
        elif not fire_found:
            # Reset immediately if no fire is detected in current checks
            fire_detected = False
            self.detection_history.clear()
        
        # Draw UI
        self.draw_sensor_status(frame)
        self.draw_location_status(frame)
        
        status_text = "STATUS: FIRE DETECTED!" if fire_detected else "STATUS: Monitoring..."
        status_color = (0, 0, 255) if fire_detected else (0, 255, 0)
        
        cv2.rectangle(frame, (5, 5), (450, 45), (0, 0, 0), -1)
        cv2.rectangle(frame, (5, 5), (450, 45), status_color, 2)
        cv2.putText(frame, status_text, (15, 32),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.rectangle(frame, (5, frame.shape[0] - 35), (300, frame.shape[0] - 5), (0, 0, 0), -1)
        cv2.putText(frame, timestamp, (15, frame.shape[0] - 15),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        return frame
    
    def draw_sensor_status(self, frame):
        """Draw hardware sensor status"""
        y_pos = 55
        cv2.rectangle(frame, (5, y_pos), (280, y_pos + 95), (0, 0, 0), -1)
        cv2.rectangle(frame, (5, y_pos), (280, y_pos + 95), (255, 255, 255), 2)
        
        cv2.putText(frame, "Hardware Sensors:", (15, y_pos + 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        sensors = [
            ('Fire Sensor', sensor_status['fire_sensor']),
            ('Smoke Detector', sensor_status['smoke_detector']),
            ('Temperature', sensor_status['temperature_sensor'])
        ]
        
        for i, (name, status) in enumerate(sensors):
            # Red if detected (True/1), Green if not detected (False/0)
            color = (0, 0, 255) if status else (0, 255, 0)
            status_text = "DETECTED" if status else "NOT DETECTED"
            cv2.putText(frame, f"{name}: {status_text}", (15, y_pos + 40 + i*20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
    
    def draw_location_status(self, frame):
        """Draw location status"""
        y_pos = 160
        max_width = min(frame.shape[1] - 10, 400)
        
        cv2.rectangle(frame, (5, y_pos), (5 + max_width, y_pos + 75), (0, 0, 0), -1)
        cv2.rectangle(frame, (5, y_pos), (5 + max_width, y_pos + 75), (255, 255, 255), 2)
        
        cv2.putText(frame, "Location:", (15, y_pos + 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        if current_location['latitude'] and current_location['longitude']:
            color = (0, 255, 0)
            address = current_location['address']
            
            max_chars = 45
            if len(address) > max_chars:
                address = address[:max_chars-3] + '...'
            
            if len(address) > 30:
                mid_point = address[:30].rfind(' ')
                if mid_point > 0:
                    line1 = address[:mid_point]
                    line2 = address[mid_point+1:]
                    cv2.putText(frame, line1, (15, y_pos + 40),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)
                    cv2.putText(frame, line2, (15, y_pos + 58),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)
                else:
                    cv2.putText(frame, address, (15, y_pos + 40),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)
            else:
                cv2.putText(frame, address, (15, y_pos + 40),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)
        else:
            cv2.putText(frame, "Fetching location...", (15, y_pos + 40),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

# ==================== INITIALIZE COMPONENTS ====================
detector = FireDetector()
sensor_reader = SensorDataReader(GOOGLE_SHEET_CSV_URL)
telegram_bot = TelegramAlert(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
location_service = LocationService()

# ==================== BACKGROUND MONITORING ====================
def monitor_sensors():
    """Background thread to continuously read sensor data"""
    while True:
        sensor_reader.read_sensor_data()
        time.sleep(5)  # Update every 5 seconds

def monitor_location():
    """Background thread to update location"""
    while True:
        location_service.get_current_location()
        time.sleep(30)  # Update every 30 seconds

def check_and_send_alert():
    """Check conditions and send Telegram alert if needed"""
    global alert_sent, last_alert_time
    
    # CRITICAL: Check if BOTH CV detection AND all hardware sensors detect fire
    if fire_detected and sensor_status['all_sensors_active']:
        current_time = time.time()
        
        # Check cooldown period
        if last_alert_time is None or (current_time - last_alert_time) > ALERT_COOLDOWN:
            
            # Make sure we have location
            if not current_location['latitude'] or not current_location['longitude']:
                location_service.get_current_location()
            
            if current_location['latitude'] and current_location['longitude']:
                print("="*70)
                print("🚨🚨🚨 FIRE ALERT TRIGGERED! 🚨🚨🚨")
                print("="*70)
                print("✅ Computer Vision: FIRE DETECTED")
                print("✅ Fire Sensor: DETECTED (1)")
                print("✅ Smoke Detector: DETECTED (1)")
                print("✅ Temperature Sensor: DETECTED (1)")
                print("✅ Location: Available")
                print(f"📍 Address: {current_location['address']}")
                print(f"🌐 Coordinates: {current_location['latitude']}, {current_location['longitude']}")
                print("\n📤 Sending Telegram alert...")
                print("="*70)
                
                success = telegram_bot.send_fire_alert(
                    current_location['latitude'],
                    current_location['longitude'],
                    current_location['address'],
                    sensor_status,
                    current_location.get('method', 'unknown')
                )
                
                if success:
                    alert_sent = True
                    last_alert_time = current_time
                    print("✅ ✅ ✅ TELEGRAM ALERT SENT SUCCESSFULLY! ✅ ✅ ✅")
                    print("="*70)
                else:
                    print("❌ Failed to send Telegram alert")
                    print("="*70)
            else:
                print("⚠️ Cannot send alert: Location not available")
    
    elif not fire_detected or not sensor_status['all_sensors_active']:
        # Reset alert status when conditions are no longer met
        if alert_sent and last_alert_time:
            time_since_alert = time.time() - last_alert_time
            if time_since_alert > 60:  # Reset after 1 minute
                alert_sent = False

def alert_monitor():
    """Background thread to monitor and send alerts"""
    while True:
        check_and_send_alert()
        time.sleep(2)  # Check every 2 seconds

# ==================== CAMERA FUNCTIONS ====================
def get_camera():
    """Initialize camera"""
    global camera
    if camera is None:
        camera = cv2.VideoCapture(0)  # Default camera
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        camera.set(cv2.CAP_PROP_FPS, 30)
    return camera

def generate_frames():
    """Generate frames for video stream"""
    cam = get_camera()
    
    while True:
        success, frame = cam.read()
        if not success:
            break
        
        frame = detector.detect_fire(frame)
        
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

# ==================== FLASK ROUTES ====================
@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    """Video streaming route"""
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def status():
    """Return current detection status"""
    return jsonify({
        'fire_detected': fire_detected,
        'detection_count': detection_count,
        'last_detection': last_detection_time.strftime("%Y-%m-%d %H:%M:%S") if last_detection_time else "None",
        'sensor_status': sensor_status,
        'alert_sent': alert_sent,
        'alert_cooldown_active': last_alert_time and (time.time() - last_alert_time) < ALERT_COOLDOWN,
        'location': current_location
    })

@app.route('/update_location', methods=['POST'])
def update_location():
    """Update location from browser (GPS)"""
    global current_location
    from flask import request
    
    data = request.get_json()
    if data and 'latitude' in data and 'longitude' in data:
        lat = data['latitude']
        lon = data['longitude']
        
        current_location['latitude'] = lat
        current_location['longitude'] = lon
        current_location['method'] = 'browser'
        current_location['accuracy'] = data.get('accuracy')
        current_location['last_update'] = datetime.now()
        
        # Get address from coordinates
        location_service.latitude = lat
        location_service.longitude = lon
        location_service.get_address_from_coords(lat, lon)
        current_location['address'] = location_service.address
        current_location['city'] = location_service.city
        current_location['country'] = location_service.country
        
        return jsonify({'success': True, 'message': 'Location updated', 'address': current_location['address']})
    
    return jsonify({'success': False,'message': 'Invalid data'})

@app.route('/test_alert')
def test_alert():
    """Test Telegram alert (for testing purposes)"""
    if not current_location['latitude'] or not current_location['longitude']:
        location_service.get_current_location()
    
    if current_location['latitude'] and current_location['longitude']:
        success = telegram_bot.send_fire_alert(
            current_location['latitude'],
            current_location['longitude'],
            current_location['address'],
            sensor_status,
            current_location.get('method', 'unknown')
        )
        return jsonify({'success': success, 'message': 'Test alert sent' if success else 'Failed to send alert'})
    else:
        return jsonify({'success': False, 'message': 'Location not available'})

# ==================== HTML TEMPLATE ====================
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fire Detection System</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        .header {
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .header p {
            font-size: 1.1em;
            opacity: 0.9;
        }
        
        .dashboard {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .video-container {
            background: white;
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.2);
        }
        
        .video-container h2 {
            margin-bottom: 15px;
            color: #333;
        }
        
        #video-stream {
            width: 100%;
            border-radius: 10px;
            border: 3px solid #ddd;
            background: #000;
        }
        
        .status-panel {
            display: flex;
            flex-direction: column;
            gap: 15px;
        }
        
        .status-card {
            background: white;
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.2);
        }
        
        .status-card h3 {
            color: #333;
            margin-bottom: 15px;
            font-size: 1.2em;
        }
        
        .status-indicator {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 15px;
            border-radius: 10px;
            font-weight: bold;
            font-size: 1.1em;
        }
        
        .status-normal {
            background: #d4edda;
            color: #155724;
        }
        
        .status-fire {
            background: #f8d7da;
            color: #721c24;
            animation: pulse 1s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
        
        .status-dot {
            width: 15px;
            height: 15px;
            border-radius: 50%;
        }
        
        .dot-normal {
            background: #28a745;
        }
        
        .dot-fire {
            background: #dc3545;
            animation: blink 0.5s infinite;
        }
        
        @keyframes blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        
        .stats {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        
        .stat-item {
            padding: 10px;
            background: #f8f9fa;
            border-radius: 8px;
            display: flex;
            justify-content: space-between;
        }
        
        .stat-label {
            color: #666;
            font-weight: 500;
        }
        
        .stat-value {
            color: #333;
            font-weight: bold;
        }
        
        .sensor-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-top: 10px;
        }
        
        .sensor-item {
            padding: 12px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.9em;
        }
        
        .sensor-active {
            background: #f8d7da;
            color: #721c24;
            border: 2px solid #dc3545;
        }
        
        .sensor-inactive {
            background: #d4edda;
            color: #155724;
            border: 2px solid #28a745;
        }
        
        .sensor-icon {
            width: 10px;
            height: 10px;
            border-radius: 50%;
        }
        
        .icon-active {
            background: #dc3545;
        }
        
        .icon-inactive {
            background: #28a745;
        }
        
        .location-display {
            background: #e7f3ff;
            border-left: 4px solid #2196F3;
            padding: 15px;
            border-radius: 8px;
            margin-top: 10px;
        }
        
        .location-display h4 {
            color: #004085;
            margin-bottom: 8px;
            font-size: 1em;
        }
        
        .location-display p {
            color: #004085;
            margin: 5px 0;
            font-size: 0.9em;
            line-height: 1.5;
        }
        
        .alert-box {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            border-radius: 8px;
            margin-top: 10px;
        }
        
        .alert-box p {
            color: #856404;
            margin: 5px 0;
            font-size: 0.9em;
            line-height: 1.5;
        }
        
        .detection-methods {
            background: #e7f3ff;
            border-left: 4px solid #2196F3;
            padding: 15px;
            border-radius: 8px;
            margin-top: 10px;
        }
        
        .detection-methods p {
            color: #004085;
            margin: 5px 0;
            font-size: 0.9em;
        }
        
        .detection-methods ul {
            margin: 10px 0 0 20px;
            color: #004085;
        }
        
        .detection-methods li {
            margin: 5px 0;
            font-size: 0.85em;
        }
        
        @media (max-width: 768px) {
            .dashboard {
                grid-template-columns: 1fr;
            }
            .sensor-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔥 Advanced Fire Detection System</h1>
            <p>Computer Vision + IoT Sensors + Live Location Tracking</p>
        </div>
        
        <div class="dashboard">
            <div class="video-container">
                <h2>📹 Live Camera Feed</h2>
                <img id="video-stream" src="{{ url_for('video_feed') }}" alt="Video Stream">
            </div>
            
            <div class="status-panel">
                <div class="status-card">
                    <h3>🚨 Detection Status</h3>
                    <div id="status-indicator" class="status-indicator status-normal">
                        <span class="status-dot dot-normal"></span>
                        <span>Monitoring - No Fire</span>
                    </div>
                </div>
                
                <div class="status-card">
                    <h3>🔌 Hardware Sensors</h3>
                    <div class="sensor-grid">
                        <div id="fire-sensor" class="sensor-item sensor-inactive">
                            <span class="sensor-icon icon-inactive"></span>
                            <span>Fire Sensor: NOT DETECTED</span>
                        </div>
                        <div id="smoke-sensor" class="sensor-item sensor-inactive">
                            <span class="sensor-icon icon-inactive"></span>
                            <span>Smoke: NOT DETECTED</span>
                        </div>
                        <div id="temp-sensor" class="sensor-item sensor-inactive">
                            <span class="sensor-icon icon-inactive"></span>
                            <span>Temp: NOT DETECTED</span>
                        </div>
                        <div id="all-sensors" class="sensor-item sensor-inactive">
                            <span class="sensor-icon icon-inactive"></span>
                            <span>All Sensors Status</span>
                        </div>
                    </div>
                    <div id="sensor-update" style="margin-top: 10px; font-size: 0.8em; color: #666; text-align: center;">
                        Last update: Never
                    </div>
                </div>
                
                <div class="status-card">
                    <h3>📍 Current Location</h3>
                    <div class="location-display">
                        <h4>📌 Address</h4>
                        <p id="location-address">Fetching location...</p>
                        <p style="font-size: 0.75em; margin-top: 8px; color: #666;">
                            <strong>Coordinates:</strong> <span id="location-coords">N/A</span>
                        </p>
                    </div>
                </div>
                
                <div class="status-card">
                    <h3>📊 Statistics</h3>
                    <div class="stats">
                        <div class="stat-item">
                            <span class="stat-label">Total Detections:</span>
                            <span class="stat-value" id="detection-count">0</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">Last Detection:</span>
                            <span class="stat-value" id="last-detection">None</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">System Status:</span>
                            <span class="stat-value" style="color: #28a745;">Active</span>
                        </div>
                    </div>
                </div>
                
                <div class="status-card">
                    <h3>🔍 Detection Methods</h3>
                    <div class="detection-methods">
                        <p><strong>Active Algorithms:</strong></p>
                        <ul>
                            <li>HSV + YCrCb Color Analysis</li>
                            <li>Motion Detection (Flicker)</li>
                            <li>Shape Analysis</li>
                            <li>Temporal Consistency</li>
                            <li>IoT Sensor Integration</li>
                            <li>GPS Location Tracking</li>
                        </ul>
                    </div>
                    <div class="alert-box">
                        <p><strong>⚠️ Alert Trigger Conditions:</strong></p>
                        <p><strong>Telegram alert sent ONLY when ALL conditions are met:</strong></p>
                        <p>1️⃣ Computer Vision detects fire in video</p>
                        <p>2️⃣ Fire Sensor = 1 (DETECTED)</p>
                        <p>3️⃣ Smoke Detector = 1 (DETECTED)</p>
                        <p>4️⃣ Temperature Sensor = 1 (DETECTED)</p>
                        <p>5️⃣ Location is available</p>
                        <p style="margin-top: 10px; font-weight: bold; color: #d9534f;">
                        🔥 Both Hardware AND Software must verify fire!
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        // Get location from browser (GPS)
        function getLocationFromBrowser() {
            if ("geolocation" in navigator) {
                navigator.geolocation.getCurrentPosition(
                    function(position) {
                        const latitude = position.coords.latitude;
                        const longitude = position.coords.longitude;
                        const accuracy = position.coords.accuracy;
                        
                        // Send to server
                        fetch('/update_location', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({
                                latitude: latitude,
                                longitude: longitude,
                                accuracy: accuracy
                            })
                        })
                        .then(response => response.json())
                        .then(data => {
                            console.log('Location updated:', data);
                        });
                    },
                    function(error) {
                        console.log('Geolocation error:', error.message);
                    },
                    {
                        enableHighAccuracy: true,
                        timeout: 10000,
                        maximumAge: 0
                    }
                );
            }
        }
        
        function updateStatus() {
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    // Update main detection status
                    const indicator = document.getElementById('status-indicator');
                    if (data.fire_detected) {
                        indicator.className = 'status-indicator status-fire';
                        indicator.innerHTML = '<span class="status-dot dot-fire"></span><span>FIRE DETECTED!</span>';
                    } else {
                        indicator.className = 'status-indicator status-normal';
                        indicator.innerHTML = '<span class="status-dot dot-normal"></span><span>Monitoring - No Fire</span>';
                    }
                    
                    // Update location display
                    const location = data.location;
                    if (location.address) {
                        document.getElementById('location-address').textContent = location.address;
                    } else {
                        document.getElementById('location-address').textContent = 'Fetching location...';
                    }
                    
                    if (location.latitude && location.longitude) {
                        document.getElementById('location-coords').textContent = 
                            `${location.latitude.toFixed(4)}, ${location.longitude.toFixed(4)}`;
                    } else {
                        document.getElementById('location-coords').textContent = 'N/A';
                    }
                    
                    // Update hardware sensors
                    updateSensor('fire-sensor', data.sensor_status.fire_sensor);
                    updateSensor('smoke-sensor', data.sensor_status.smoke_detector);
                    updateSensor('temp-sensor', data.sensor_status.temperature_sensor);
                    updateSensor('all-sensors', data.sensor_status.all_sensors_active);
                    
                    // Update sensor last update time
                    if (data.sensor_status.last_update) {
                        const updateTime = new Date(data.sensor_status.last_update);
                        document.getElementById('sensor-update').textContent = 
                            'Last update: ' + updateTime.toLocaleTimeString();
                    }
                    
                    // Update statistics
                    document.getElementById('detection-count').textContent = data.detection_count;
                    document.getElementById('last-detection').textContent = data.last_detection;
                });
        }
        
        function updateSensor(elementId, isActive) {
            const element = document.getElementById(elementId);
            const textElement = element.querySelector('span:last-child');
            
            if (isActive) {
                // RED for DETECTED (1/True)
                element.className = 'sensor-item sensor-active';
                element.querySelector('.sensor-icon').className = 'sensor-icon icon-active';
                
                if (elementId === 'fire-sensor') {
                    textElement.textContent = 'Fire Sensor: DETECTED';
                } else if (elementId === 'smoke-sensor') {
                    textElement.textContent = 'Smoke: DETECTED';
                } else if (elementId === 'temp-sensor') {
                    textElement.textContent = 'Temp: DETECTED';
                } else if (elementId === 'all-sensors') {
                    textElement.textContent = '🚨 ALL SENSORS DETECTED!';
                }
            } else {
                // GREEN for NOT DETECTED (0/False)
                element.className = 'sensor-item sensor-inactive';
                element.querySelector('.sensor-icon').className = 'sensor-icon icon-inactive';
                
                if (elementId === 'fire-sensor') {
                    textElement.textContent = 'Fire Sensor: NOT DETECTED';
                } else if (elementId === 'smoke-sensor') {
                    textElement.textContent = 'Smoke: NOT DETECTED';
                } else if (elementId === 'temp-sensor') {
                    textElement.textContent = 'Temp: NOT DETECTED';
                } else if (elementId === 'all-sensors') {
                    textElement.textContent = 'All Sensors Status';
                }
            }
        }
        
        // Get location on page load
        getLocationFromBrowser();
        
        // Update location every 30 seconds
        setInterval(getLocationFromBrowser, 30000);
        
        // Update status every second
        setInterval(updateStatus, 1000);
        updateStatus();
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    import os
    
    # Create templates directory
    os.makedirs('templates', exist_ok=True)
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(HTML_TEMPLATE)
    
    print("="*70)
    print("🔥 ADVANCED FIRE DETECTION SYSTEM WITH LIVE LOCATION")
    print("="*70)
    print("\n📋 SETUP INSTRUCTIONS:")
    print("\n1. GOOGLE SHEETS SETUP:")
    print("   - Create a Google Sheet with this structure:")
    print("     Column A: Date (e.g., 9/30/2025)")
    print("     Column B: Time (e.g., 5:03:40)")
    print("     Column C: fire (0 or 1)")
    print("     Column D: smoke (0 or 1)")
    print("     Column E: temperature (0 or 1)")
    print("   - Where 1 = DETECTED/Active and 0 = NOT DETECTED/Inactive")
    print("   - Share: File → Share → Publish to web → CSV")
    print("   - Copy the CSV URL and update GOOGLE_SHEET_CSV_URL")
    print("\n2. TELEGRAM BOT SETUP:")
    print("   - Message @BotFather on Telegram")
    print("   - Send /newbot and follow instructions")
    print("   - Copy bot token → Update TELEGRAM_BOT_TOKEN")
    print("   - Start chat with your bot")
    print("   - Get chat ID: https://api.telegram.org/bot<TOKEN>/getUpdates")
    print("   - Update TELEGRAM_CHAT_ID")
    print("\n3. LOCATION TRACKING:")
    print("   ✓ Browser will request GPS permission")
    print("   ✓ Click 'Allow' for high-accuracy location")
    print("   ✓ Location shows as ACTUAL ADDRESS (not just coordinates)")
    print("   ✓ Auto-updates every 30 seconds")
    print("\n✨ FEATURES:")
    print("  ✓ Computer Vision Fire Detection")
    print("  ✓ IoT Sensors (1=DETECTED, 0=NOT DETECTED)")
    print("  ✓ Live Address Location Tracking")
    print("  ✓ Telegram Alerts with Address")
    print("  ✓ Multi-source Verification")
    print("\n🚀 Starting server...")
    print("📱 Open: http://127.0.0.1:5000")
    print("="*70)
    
    # Get initial location
    print("\n📍 Fetching initial location...")
    if location_service.get_current_location():
        print(f"✓ Location: {current_location['address']}")
    else:
        print("⚠️ Will fetch location from browser")
    
    # Start background threads
    sensor_thread = threading.Thread(target=monitor_sensors, daemon=True)
    sensor_thread.start()
    
    location_thread = threading.Thread(target=monitor_location, daemon=True)
    location_thread.start()
    
    alert_thread = threading.Thread(target=alert_monitor, daemon=True)
    alert_thread.start()
    
    print("\n✓ All monitoring threads started")
    print("⚠️ Allow location access when browser prompts!\n")
    
    # Run Flask app
    app.run(debug=True, threaded=True, use_reloader=False)
