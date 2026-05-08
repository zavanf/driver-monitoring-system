#!/usr/bin/env python3
import cv2
import numpy as np
import time
import os
from datetime import datetime
from picamera2 import Picamera2
import mediapipe as mp
from collections import deque
import pygame
import threading
from math import atan2, degrees
import csv
import serial
from dataclasses import dataclass

# Suppress warnings
import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='google.protobuf')

# Initialize MediaPipe Face Mesh with optimized settings
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
    static_image_mode=False
)

# ==================== DROWSINESS DETECTION INDICES ====================
LEFT_EYE_VERTICAL = [159, 145]  # Top and bottom
LEFT_EYE_HORIZONTAL = [33, 133]  # Corners
RIGHT_EYE_VERTICAL = [386, 374]
RIGHT_EYE_HORIZONTAL = [362, 263]

# ==================== DISTRACTION DETECTION INDICES ====================
NOSE_TIP = 1
LEFT_EYE_OUTER = 33
RIGHT_EYE_OUTER = 263
CHIN = 152
LEFT_PUPIL = 468
RIGHT_PUPIL = 473
LEFT_EYE_INNER = 133
RIGHT_EYE_INNER = 362

# ==================== EVENT TYPES ====================
EVENT_TYPES = {
    'DROWSY': {'priority': 1, 'color': (0, 0, 255), 'description': 'Drowsiness Detection'},
    'SEVERE_HEAD_TURN_RIGHT': {'priority': 2, 'color': (0, 0, 255), 'description': 'Severe Head Turn Right'},
    'SEVERE_HEAD_TURN_LEFT': {'priority': 2, 'color': (0, 0, 255), 'description': 'Severe Head Turn Left'},
    'SEVERE_LOOKING_DOWN': {'priority': 2, 'color': (0, 0, 255), 'description': 'Severe Looking Down'},
    'LOOKING_RIGHT': {'priority': 3, 'color': (0, 165, 255), 'description': 'Looking Right'},
    'LOOKING_LEFT': {'priority': 3, 'color': (0, 165, 255), 'description': 'Looking Left'},
    'LOOKING_DOWN': {'priority': 3, 'color': (0, 165, 255), 'description': 'Looking Down'},
    'LOOKING_UP': {'priority': 3, 'color': (0, 165, 255), 'description': 'Looking Up'},
}

# ==================== GPS DATA PARSING ========================
@dataclass
class position:
    lon: float
    lat: float

def parse_nmea_coordinates(sentence):
    parts = sentence.split(',')
    
    # Identify sentence type and extract relevant raw fields
    if "$GNRMC" in parts[0]:
        # $GNRMC index: 3=Lat, 4=N/S, 5=Lon, 6=E/W
        raw_lat, lat_dir, raw_lon, lon_dir = parts[3], parts[4], parts[5], parts[6]
    elif "$GNGGA" in parts[0]:
        # $GNGGA index: 2=Lat, 3=N/S, 4=Lon, 5=E/W
        raw_lat, lat_dir, raw_lon, lon_dir = parts[2], parts[3], parts[4], parts[5]
    else:
        return "Unsupported sentence type"

    def to_decimal_degrees(value, direction):
        if not value or not direction: return None
        # Split degrees and minutes (Last 2 digits + decimals are minutes)
        dot_idx = value.find('.')
        degrees = float(value[:dot_idx-2])
        minutes = float(value[dot_idx-2:])
        
        decimal = degrees + (minutes / 60.0)
        # S and W are negative
        if direction in ['S', 'W']:
            decimal *= -1
        return round(decimal, 6)

    return position(to_decimal_degrees(raw_lat, lat_dir), to_decimal_degrees(raw_lon, lon_dir))
    #{
    #    "latitude": to_decimal_degrees(raw_lat, lat_dir),
    #    "longitude": to_decimal_degrees(raw_lon, lon_dir)
    #}

# ==================== EVENT RECORDER CLASS ====================
class EventRecorder:
    def __init__(self, base_dir="driver_monitoring_logs", pre_event_seconds=2, post_event_seconds=2, fps=30):
        self.base_dir = base_dir
        self.images_dir = os.path.join(base_dir, "images")
        self.videos_dir = os.path.join(base_dir, "videos")
        self.pre_event_seconds = pre_event_seconds
        self.post_event_seconds = post_event_seconds
        self.fps = fps
        
        # Create directories
        for dir_path in [self.images_dir, self.videos_dir]:
            os.makedirs(dir_path, exist_ok=True)
        
        # Initialize CSV log
        self.log_file = os.path.join(base_dir, "events_log.csv")
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w') as f:
                f.write("timestamp,longitude,latitude,event_type,description,duration_seconds,filename,frame_count\n")
        
        # Circular buffer for pre-event frames
        self.frame_buffer = deque(maxlen=self.pre_event_seconds * self.fps)
        
        # Event state
        self.recording_event = False
        self.event_frames = []
        self.event_start_time = None
        self.event_type = None
        self.event_description = None
        self.event_longitude = ''
        self.event_latitude = ''
        
        print(f"Event Recorder initialized - Saving to: {base_dir}")
        
    def add_frame(self, frame, event_type=None, event_description=None):
        """Add frame to buffer and handle event recording"""
        timestamp = datetime.now()
        
        # Always add to circular buffer (for pre-event capture)
        self.frame_buffer.append({
            'frame': frame.copy(),
            'timestamp': timestamp
        })
        
        # Check if we should start recording
        if event_type and not self.recording_event:
            self.start_event(event_type, event_description)
        
        # If recording, save frame
        if self.recording_event:
            self.event_frames.append({
                'frame': frame.copy(),
                'timestamp': timestamp
            })
            
            # Check if we should stop recording (event ended)
            if event_type is None:
                self.stop_event()
            elif len(self.event_frames) > (self.pre_event_seconds + self.post_event_seconds) * self.fps:
                # Max recording length reached
                self.stop_event()
    
    def start_event(self, event_type, description):
        """Start recording an event"""
        self.recording_event = True
        self.event_start_time = time.time()
        self.event_type = event_type
        self.event_description = description
        self.event_frames = []
        
        # Add pre-event frames from buffer
        self.event_frames.extend(list(self.frame_buffer))
        
        is_gpgga_gnrmc_sentence = False
        while is_gpgga_gnrmc_sentence == False:
            # Read a line of data from the GPS
            line = ser.readline().decode('ascii', errors='replace').strip()
            
            if line:
                if line.startswith('$GPGGA') or line.startswith('$GNRMC'):
                   print(line)        
                   is_gpgga_gnrmc_sentence = True
                   position = parse_nmea_coordinates(line)
                   self.event_latitude = position.lat
                   self.event_longitude = position.lon
        
        print(f"\n>>> RECORDING STARTED: {description}")
    
    def stop_event(self):
        """Stop recording and save event"""
        if not self.recording_event:
            return
        
        duration = time.time() - self.event_start_time
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save as video
        self.save_event_video(timestamp_str, duration)
        
        # Save key frame as image
        self.save_key_frame(timestamp_str)
        
        # Log to CSV
        self.log_event(timestamp_str, duration)
        
        print(f"<<< RECORDING STOPPED: {self.event_description} ({duration:.1f}s)")
        print(f"    Video: {timestamp_str}_{self.event_type.lower()}_{duration:.1f}s.mp4")
        print(f"    Key frame: {timestamp_str}_{self.event_type.lower()}_keyframe.jpg")
        
        self.recording_event = False
        self.event_frames = []
    
    def save_event_video(self, timestamp_str, duration):
        """Save event as video file"""
        if len(self.event_frames) < 10:  # Too short
            return
        
        filename = f"{timestamp_str}_{self.event_type.lower()}_{duration:.1f}s.mp4"
        filepath = os.path.join(self.videos_dir, filename)
        
        # Get frame dimensions
        h, w = self.event_frames[0]['frame'].shape[:2]
        
        # Create video writer
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(filepath, fourcc, self.fps, (w, h))
        
        # Write frames
        for i, frame_data in enumerate(self.event_frames):
            # Add timestamp and event info to frame
            frame = frame_data['frame'].copy()
            self.annotate_frame(frame, frame_data['timestamp'], i)
            out.write(frame)
        
        out.release()
    
    def save_key_frame(self, timestamp_str):
        """Save a key frame (the moment of detection)"""
        if not self.event_frames:
            return
        
        # Use the frame at the pre-event boundary (when detection occurred)
        pre_event_frames = self.pre_event_seconds * self.fps
        if len(self.event_frames) > pre_event_frames:
            frame_data = self.event_frames[pre_event_frames]
        else:
            frame_data = self.event_frames[-1]  # Use last frame
        
        filename = f"{timestamp_str}_{self.event_type.lower()}_keyframe.jpg"
        filepath = os.path.join(self.images_dir, filename)
        
        frame = frame_data['frame'].copy()
        self.annotate_frame(frame, frame_data['timestamp'], is_keyframe=True)
        cv2.imwrite(filepath, frame)
    
    def annotate_frame(self, frame, timestamp, frame_index=0, is_keyframe=False):
        """Add timestamp and event info to frame"""
        h, w = frame.shape[:2]
        
        # Add timestamp
        time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, time_str, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Add event type
        if self.event_type:
            color = EVENT_TYPES.get(self.event_type, {}).get('color', (0, 255, 255))
            cv2.putText(frame, self.event_description, (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        # Add frame counter
        cv2.putText(frame, f"Frame: {frame_index}", (10, h - 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        # Add indicator for keyframe
        if is_keyframe:
            cv2.putText(frame, "★ EVENT DETECTED", (w - 250, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    
    def log_event(self, timestamp_str, duration):
        """Log event to CSV file"""
        filename = f"{timestamp_str}_{self.event_type.lower()}_{duration:.1f}s.mp4"
        with open(self.log_file, 'a') as f:
            f.write(f"{timestamp_str},{self.event_longitude},{self.event_latitude},{self.event_type},{self.event_description},{duration:.2f},{filename},{len(self.event_frames)}\n")

# ==================== CAMERA SETUP ====================
picam2 = Picamera2()
config = picam2.create_preview_configuration(
    main={"size": (640, 480), "format": "RGB888"}
)
picam2.configure(config)
picam2.start()

# Warm up camera
time.sleep(1)

# ==================== PARAMETERS ====================
# Drowsiness parameters
EAR_THRESHOLD = 0.20
ALERT_DURATION = 2.0
CLOSED_FRAMES_NEEDED = 2
OPEN_FRAMES_NEEDED = 1

# Distraction parameters
LOOK_AWAY_DURATION = 3.0
LOOK_DOWN_DURATION = 1.5
LOOK_UP_DURATION = 2.0
SEVERE_DURATION = 1.0

# Smoothing
ear_history = deque(maxlen=2)
pose_history = deque(maxlen=3)

# State tracking - Drowsiness
closed_start_time = None
consecutive_closed = 0
consecutive_open = 0
is_eyes_closed = False
drowsy_alert_active = False

# State tracking - Distraction
distraction_start_time = None
current_distraction_type = "FOCUSED"
distraction_alert_active = False
is_distracted = False

# Calibration
calibration_mode = True
calibration_frames = 0
CALIBRATION_DURATION = 30
baseline_yaw = 0
baseline_pitch = 0
pitch_calibration_buffer = deque(maxlen=30)
yaw_calibration_buffer = deque(maxlen=30)

face_lost_time = None
FACE_LOST_TIMEOUT = 1.0

# Debug mode
debug_mode = True

# Initialize event recorder
event_recorder = EventRecorder(
    base_dir="driver_monitoring_logs",
    pre_event_seconds=2,
    post_event_seconds=2,
    fps=30
)

# Initialize pygame in background thread
pygame_initialized = False
sound = None

# Use the correct serial port for Pi 5 with the disable-bt overlay
ser = serial.Serial('/dev/ttyAMA0', 9600, timeout=1)


def init_pygame():
    global pygame_initialized, sound
    try:
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        sound = pygame.mixer.Sound('alarm.mp3')
        pygame_initialized = True
        print("Pygame initialized successfully")
    except Exception as e:
        print(f"Pygame initialization error: {e}")
        pygame_initialized = False

threading.Thread(target=init_pygame, daemon=True).start()

# ==================== DROWSINESS FUNCTIONS ====================
def calculate_ear(landmarks, vertical_idx, horizontal_idx, frame_shape):
    """Calculate Eye Aspect Ratio"""
    h, w = frame_shape[:2]
    
    top = landmarks.landmark[vertical_idx[0]]
    bottom = landmarks.landmark[vertical_idx[1]]
    left = landmarks.landmark[horizontal_idx[0]]
    right = landmarks.landmark[horizontal_idx[1]]
    
    vertical = abs(top.y - bottom.y) * h
    horizontal = abs(left.x - right.x) * w
    
    if horizontal < 1:
        return 0
    
    return vertical / horizontal

# ==================== DISTRACTION FUNCTIONS ====================
def calculate_head_pose(landmarks, frame_shape):
    """Improved head pose estimation with better yaw calculation"""
    h, w = frame_shape[:2]
    
    # Get key points
    nose_tip = landmarks.landmark[NOSE_TIP]
    left_eye = landmarks.landmark[LEFT_EYE_OUTER]
    right_eye = landmarks.landmark[RIGHT_EYE_OUTER]
    chin = landmarks.landmark[CHIN]
    
    # Convert to pixel coordinates
    nose_tip_px = np.array([nose_tip.x * w, nose_tip.y * h])
    left_eye_px = np.array([left_eye.x * w, left_eye.y * h])
    right_eye_px = np.array([right_eye.x * w, right_eye.y * h])
    chin_px = np.array([chin.x * w, chin.y * h])
    
    # Calculate eye center
    eye_center = (left_eye_px + right_eye_px) / 2
    
    # Calculate yaw using nose position relative to eye center
    nose_offset = nose_tip_px[0] - eye_center[0]
    eye_distance = abs(right_eye_px[0] - left_eye_px[0])
    
    if eye_distance > 0:
        yaw = (nose_offset / eye_distance) * 90
        yaw = max(-45, min(45, yaw))
    else:
        yaw = 0
    
    # Calculate pitch using nose vertical position
    face_height = chin_px[1] - eye_center[1]
    if face_height > 0:
        nose_ratio = (nose_tip_px[1] - eye_center[1]) / face_height
        pitch = (nose_ratio - 0.5) * 60
        pitch = max(-30, min(30, pitch))
    else:
        pitch = 0
    
    return yaw, pitch

def classify_distraction(yaw, pitch, baseline_pitch, baseline_yaw):
    """Distraction classification with proper right/left detection"""
    pitch_dev = pitch - baseline_pitch
    yaw_dev = yaw - baseline_yaw
    
    # Debug output for significant movements
    if debug_mode and (abs(yaw_dev) > 15 or abs(pitch_dev) > 10):
        print(f"Deviation - Yaw: {yaw_dev:+.1f}°, Pitch: {pitch_dev:+.1f}°")
    
    # Deadzone - ignore small movements
    if abs(pitch_dev) < 8 and abs(yaw_dev) < 15:
        return ("FOCUSED", False)
    
    # PRIORITY 1: SEVERE HEAD TURN (>45°)
    if yaw_dev > 45:
        print(f"*** SEVERE RIGHT TURN: {yaw_dev:.1f}°")
        return ("SEVERE HEAD TURN RIGHT", True)
    if yaw_dev < -45:
        print(f"*** SEVERE LEFT TURN: {yaw_dev:.1f}°")
        return ("SEVERE HEAD TURN LEFT", True)
    
    # PRIORITY 2: SEVERE LOOKING DOWN (>25°)
    if pitch_dev > 25:
        print(f"*** SEVERE LOOKING DOWN: {pitch_dev:.1f}°")
        return ("SEVERE LOOKING DOWN", True)
    
    # PRIORITY 3: LOOKING RIGHT/LEFT (25-45°)
    if yaw_dev > 25:
        print(f"*** LOOKING RIGHT: {yaw_dev:.1f}°")
        return ("LOOKING RIGHT", True)
    if yaw_dev < -25:
        print(f"*** LOOKING LEFT: {yaw_dev:.1f}°")
        return ("LOOKING LEFT", True)
    
    # PRIORITY 4: LOOKING DOWN (12-25°)
    if pitch_dev > 12:
        return ("LOOKING DOWN", True)
    
    # PRIORITY 5: LOOKING UP (>20°)
    if pitch_dev < -20:
        return ("LOOKING UP", True)
    
    # WARNINGS - visual only
    if abs(yaw_dev) > 15:
        return ("HEAD TURNED", False)
    if pitch_dev > 8:
        return ("LOOKING DOWN SLIGHTLY", False)
    if pitch_dev < -8:
        return ("LOOKING UP SLIGHTLY", False)
    
    return ("FOCUSED", False)

print("=" * 60)
print("Driver Monitoring System - Starting...")
print("=" * 60)
print("\n=== CALIBRATION MODE ===")
print("Look straight ahead for 1 second...")
print("=" * 60)

# ==================== MAIN LOOP ====================
try:
    while True:
        # Capture frame
        frame = picam2.capture_array()
        if frame is None:
            continue
            
        display_frame = frame.copy()
        
        # Process with MediaPipe
        results = face_mesh.process(frame)
        
        # Reset sound trigger
        should_play_sound = False
        
        # Determine current event type for recording
        current_event_type = None
        current_event_description = None
        
        if results and results.multi_face_landmarks:
            face_lost_time = None
            landmarks = results.multi_face_landmarks[0]
            
            # ===== DROWSINESS DETECTION =====
            left_ear = calculate_ear(landmarks, LEFT_EYE_VERTICAL, LEFT_EYE_HORIZONTAL, frame.shape)
            right_ear = calculate_ear(landmarks, RIGHT_EYE_VERTICAL, RIGHT_EYE_HORIZONTAL, frame.shape)
            current_ear = (left_ear + right_ear) / 2.0
            
            ear_history.append(current_ear)
            smoothed_ear = np.mean(ear_history)
            
            # Eye state logic
            if smoothed_ear < EAR_THRESHOLD:
                consecutive_closed += 1
                consecutive_open = 0
            else:
                consecutive_open += 1
                consecutive_closed = 0
            
            # Update eye state
            if consecutive_closed >= CLOSED_FRAMES_NEEDED:
                if not is_eyes_closed:
                    print(f">>> Eyes CLOSED (EAR: {smoothed_ear:.3f})")
                is_eyes_closed = True
            elif consecutive_open >= OPEN_FRAMES_NEEDED:
                if is_eyes_closed:
                    print(f">>> Eyes OPENED (EAR: {smoothed_ear:.3f})")
                is_eyes_closed = False
            
            # Drowsiness alert
            if is_eyes_closed:
                if closed_start_time is None:
                    closed_start_time = time.time()
                duration = time.time() - closed_start_time
                if duration >= ALERT_DURATION:
                    should_play_sound = True
                    drowsy_alert_active = True
                    current_event_type = 'DROWSY'
                    current_event_description = 'Drowsiness Detection'
            else:
                closed_start_time = None
                drowsy_alert_active = False
            
            # ===== HEAD POSE CALCULATION =====
            yaw, pitch = calculate_head_pose(landmarks, frame.shape)
            
            # ===== CALIBRATION =====
            if calibration_mode:
                if calibration_frames < CALIBRATION_DURATION:
                    pitch_calibration_buffer.append(pitch)
                    yaw_calibration_buffer.append(yaw)
                    calibration_frames += 1
                    
                    # Show progress
                    if calibration_frames % 10 == 0:
                        progress = int((calibration_frames / CALIBRATION_DURATION) * 100)
                        cv2.putText(display_frame, f"CALIBRATING: {progress}%", (10, 60),
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                else:
                    # Calibration complete
                    baseline_pitch = np.mean(pitch_calibration_buffer)
                    baseline_yaw = np.mean(yaw_calibration_buffer)
                    calibration_mode = False
                    print(f"\n=== CALIBRATION COMPLETE ===")
                    print(f"Baseline - Pitch: {baseline_pitch:.1f}°, Yaw: {baseline_yaw:.1f}°")
                    print("=" * 60)
            
            # ===== DISTRACTION DETECTION =====
            if not calibration_mode:
                # Smooth pose
                pose_history.append([yaw, pitch])
                if len(pose_history) == pose_history.maxlen:
                    smoothed = np.mean(pose_history, axis=0)
                    yaw, pitch = smoothed[0], smoothed[1]
                
                # Only check distraction when eyes are open
                if not is_eyes_closed:
                    distraction_type, is_distracted = classify_distraction(
                        yaw, pitch, baseline_pitch, baseline_yaw
                    )
                    
                    # Distraction timer logic
                    if is_distracted:
                        # Determine required duration based on type
                        if "SEVERE" in distraction_type:
                            required_time = SEVERE_DURATION
                        elif "LOOKING RIGHT" in distraction_type or "LOOKING LEFT" in distraction_type:
                            required_time = LOOK_AWAY_DURATION
                        elif "LOOKING DOWN" in distraction_type:
                            required_time = LOOK_DOWN_DURATION
                        elif "LOOKING UP" in distraction_type:
                            required_time = LOOK_UP_DURATION
                        else:
                            required_time = LOOK_AWAY_DURATION
                        
                        if distraction_type == current_distraction_type:
                            if distraction_start_time is None:
                                distraction_start_time = time.time()
                                if debug_mode:
                                    print(f"Started timer for: {distraction_type}")
                            
                            elapsed = time.time() - distraction_start_time
                            if elapsed >= required_time:
                                should_play_sound = True
                                if not distraction_alert_active:
                                    print(f"\n!!! DISTRACTION ALERT: {distraction_type} !!!")
                                    distraction_alert_active = True
                                    
                                    # Set event type for recording
                                    if "SEVERE HEAD TURN RIGHT" in distraction_type:
                                        current_event_type = 'SEVERE_HEAD_TURN_RIGHT'
                                        current_event_description = distraction_type
                                    elif "SEVERE HEAD TURN LEFT" in distraction_type:
                                        current_event_type = 'SEVERE_HEAD_TURN_LEFT'
                                        current_event_description = distraction_type
                                    elif "SEVERE LOOKING DOWN" in distraction_type:
                                        current_event_type = 'SEVERE_LOOKING_DOWN'
                                        current_event_description = distraction_type
                                    elif "LOOKING RIGHT" in distraction_type:
                                        current_event_type = 'LOOKING_RIGHT'
                                        current_event_description = distraction_type
                                    elif "LOOKING LEFT" in distraction_type:
                                        current_event_type = 'LOOKING_LEFT'
                                        current_event_description = distraction_type
                                    elif "LOOKING DOWN" in distraction_type:
                                        current_event_type = 'LOOKING_DOWN'
                                        current_event_description = distraction_type
                                    elif "LOOKING UP" in distraction_type:
                                        current_event_type = 'LOOKING_UP'
                                        current_event_description = distraction_type
                        else:
                            current_distraction_type = distraction_type
                            distraction_start_time = time.time()
                            distraction_alert_active = False
                    else:
                        distraction_start_time = None
                        distraction_alert_active = False
                        current_distraction_type = "FOCUSED"
            
            # ===== VISUALIZATION =====
            # Eye landmarks
            eye_color = (0, 0, 255) if is_eyes_closed else (0, 255, 0)
            for idx in LEFT_EYE_VERTICAL + LEFT_EYE_HORIZONTAL + RIGHT_EYE_VERTICAL + RIGHT_EYE_HORIZONTAL:
                point = landmarks.landmark[idx]
                x, y = int(point.x * frame.shape[1]), int(point.y * frame.shape[0])
                cv2.circle(display_frame, (x, y), 2, eye_color, -1)
            
            # Eye measurement lines
            for vert_idx in [LEFT_EYE_VERTICAL, RIGHT_EYE_VERTICAL]:
                p1 = (int(landmarks.landmark[vert_idx[0]].x * frame.shape[1]), 
                      int(landmarks.landmark[vert_idx[0]].y * frame.shape[0]))
                p2 = (int(landmarks.landmark[vert_idx[1]].x * frame.shape[1]), 
                      int(landmarks.landmark[vert_idx[1]].y * frame.shape[0]))
                cv2.line(display_frame, p1, p2, (0, 255, 255), 1)
            
            # Head pose arrow
            if not calibration_mode:
                h, w = frame.shape[:2]
                nose = landmarks.landmark[NOSE_TIP]
                nx, ny = int(nose.x * w), int(nose.y * h)
                
                pitch_dev = pitch - baseline_pitch
                yaw_dev = yaw - baseline_yaw
                
                # Arrow length based on deviation
                arrow_len = 50 + min(30, abs(int(yaw_dev)) + abs(int(pitch_dev)))
                end_x = int(nx + arrow_len * np.sin(np.radians(yaw_dev)))
                end_y = int(ny - arrow_len * np.sin(np.radians(pitch_dev)))
                
                # Arrow color based on severity
                if is_eyes_closed or drowsy_alert_active:
                    color = (0, 0, 255)  # Red
                elif distraction_alert_active:
                    color = (0, 0, 255)  # Red
                elif abs(yaw_dev) > 25 or pitch_dev > 12 or pitch_dev < -20:
                    color = (0, 0, 255)  # Red
                elif abs(yaw_dev) > 15 or abs(pitch_dev) > 8:
                    color = (0, 165, 255)  # Orange
                else:
                    color = (0, 255, 0)  # Green
                
                cv2.arrowedLine(display_frame, (nx, ny), (end_x, end_y), color, 2)
                cv2.circle(display_frame, (nx, ny), 3, (255, 255, 0), -1)
            
            # ===== TEXT OVERLAY =====
            y_pos = 30
            
            # Drowsiness info
            cv2.putText(display_frame, f"EAR: {smoothed_ear:.3f} (L:{left_ear:.2f} R:{right_ear:.2f})", 
                       (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            y_pos += 20
            
            # Eye state
            state_text = "EYES CLOSED" if is_eyes_closed else "EYES OPEN"
            state_color = (0, 0, 255) if is_eyes_closed else (0, 255, 0)
            cv2.putText(display_frame, state_text, (10, y_pos),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, state_color, 1)
            y_pos += 20
            
            # Head pose info
            if not calibration_mode:
                pitch_dev = pitch - baseline_pitch
                yaw_dev = yaw - baseline_yaw
                
                cv2.putText(display_frame, f"Yaw: {yaw:.1f} (dev: {yaw_dev:+.1f})", 
                           (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                y_pos += 20
                cv2.putText(display_frame, f"Pitch: {pitch:.1f} (dev: {pitch_dev:+.1f})", 
                           (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                y_pos += 20
                
                # Current distraction state
                if distraction_alert_active:
                    cv2.putText(display_frame, f"ALERT: {current_distraction_type}", 
                               (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                    y_pos += 20
                elif is_distracted:
                    cv2.putText(display_frame, f"WARNING: {current_distraction_type}", 
                               (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)
                    y_pos += 20
            
            # ===== YAW VISUAL INDICATOR =====
            if not calibration_mode:
                bar_x = 10
                bar_y = y_pos + 10
                bar_width = 200
                bar_height = 15
                
                # Draw background
                cv2.rectangle(display_frame, (bar_x, bar_y), 
                            (bar_x + bar_width, bar_y + bar_height), (50, 50, 50), -1)
                
                # Draw center line
                cv2.line(display_frame, 
                        (bar_x + bar_width//2, bar_y), 
                        (bar_x + bar_width//2, bar_y + bar_height), 
                        (100, 100, 100), 2)
                
                # Draw indicator based on yaw deviation
                indicator_x = bar_x + bar_width//2 + int((yaw_dev / 45) * bar_width//2)
                indicator_x = max(bar_x + 5, min(bar_x + bar_width - 5, indicator_x))
                
                # Color based on severity
                if abs(yaw_dev) > 25:
                    ind_color = (0, 0, 255)  # Red
                elif abs(yaw_dev) > 15:
                    ind_color = (0, 165, 255)  # Orange
                else:
                    ind_color = (0, 255, 0)  # Green
                
                cv2.circle(display_frame, (indicator_x, bar_y + bar_height//2), 8, ind_color, -1)
                
                # Labels
                cv2.putText(display_frame, "LEFT", (bar_x, bar_y + bar_height + 15),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                cv2.putText(display_frame, "RIGHT", (bar_x + bar_width - 40, bar_y + bar_height + 15),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                
                y_pos += 50
            
            # ===== PROGRESS BARS =====
            # Drowsiness progress
            if is_eyes_closed and closed_start_time and not drowsy_alert_active:
                elapsed = time.time() - closed_start_time
                if elapsed < ALERT_DURATION:
                    bar_len = int(200 * (elapsed / ALERT_DURATION))
                    cv2.rectangle(display_frame, (10, y_pos), (10 + bar_len, y_pos + 10), (0, 0, 255), -1)
                    cv2.putText(display_frame, f"Drowsy: {elapsed:.1f}/{ALERT_DURATION}s", 
                               (10, y_pos-5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                    y_pos += 20
            
            # Distraction progress
            elif not calibration_mode and distraction_start_time and not distraction_alert_active and is_distracted:
                # Determine required time
                if "SEVERE" in current_distraction_type:
                    required = SEVERE_DURATION
                elif "LOOKING RIGHT" in current_distraction_type or "LOOKING LEFT" in current_distraction_type:
                    required = LOOK_AWAY_DURATION
                elif "LOOKING DOWN" in current_distraction_type:
                    required = LOOK_DOWN_DURATION
                elif "LOOKING UP" in current_distraction_type:
                    required = LOOK_UP_DURATION
                else:
                    required = LOOK_AWAY_DURATION
                
                elapsed = time.time() - distraction_start_time
                if elapsed < required:
                    bar_len = int(200 * (elapsed / required))
                    cv2.rectangle(display_frame, (10, y_pos), (10 + bar_len, y_pos + 10), (0, 0, 255), -1)
                    cv2.putText(display_frame, f"Alert: {elapsed:.1f}/{required}s", 
                               (10, y_pos-5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                    y_pos += 20
            
            # Recording indicator
            if event_recorder.recording_event:
                cv2.putText(display_frame, "● REC", (display_frame.shape[1] - 100, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # ===== ALERT MESSAGES =====
            if drowsy_alert_active:
                cv2.putText(display_frame, "!!! WAKE UP !!!", (150, 200),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
            elif distraction_alert_active:
                if "SEVERE" in current_distraction_type:
                    cv2.putText(display_frame, "!!! FACE THE ROAD !!!", (120, 200),
                               cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
                else:
                    cv2.putText(display_frame, "!!! PAY ATTENTION !!!", (120, 200),
                               cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
        
        else:
            # No face detected
            cv2.putText(display_frame, "NO FACE", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            
            if face_lost_time is None:
                face_lost_time = time.time()
            
            if time.time() - face_lost_time > FACE_LOST_TIMEOUT:
                should_play_sound = False
                # Reset states
                is_eyes_closed = False
                consecutive_closed = 0
                consecutive_open = 0
                closed_start_time = None
                distraction_alert_active = False
                distraction_start_time = None
        
        # Add frame to event recorder
        event_recorder.add_frame(display_frame, current_event_type, current_event_description)
        
        # Control sound
        if pygame_initialized and sound:
            if should_play_sound:
                if not pygame.mixer.get_busy():
                    sound.play(-1)
            else:
                if pygame.mixer.get_busy():
                    sound.stop()
        
        # Show frame
        cv2.imshow('Driver Monitor', display_frame)
        
        # Handle keys
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('+') or key == ord('='):
            EAR_THRESHOLD = min(0.4, EAR_THRESHOLD + 0.01)
            print(f"EAR threshold: {EAR_THRESHOLD:.3f}")
        elif key == ord('-') or key == ord('_'):
            EAR_THRESHOLD = max(0.1, EAR_THRESHOLD - 0.01)
            print(f"EAR threshold: {EAR_THRESHOLD:.3f}")
        elif key == ord('d'):
            debug_mode = not debug_mode
            print(f"Debug mode: {'ON' if debug_mode else 'OFF'}")
        elif key == ord('c'):
            calibration_mode = True
            calibration_frames = 0
            pitch_calibration_buffer.clear()
            yaw_calibration_buffer.clear()
            print("\n=== RECALIBRATING ===")

except KeyboardInterrupt:
    print("\nShutting down...")

finally:
    # Cleanup
    if pygame_initialized and sound:
        sound.stop()
        pygame.mixer.quit()
    picam2.stop()
    ser.close()
    cv2.destroyAllWindows()
    print(f"\nEvent logs saved to: driver_monitoring_logs/")
    print("Done.")