#!/usr/bin/env python3
from flask import Flask, render_template, send_file, jsonify, request, abort, Response
from flask_cors import CORS
import os
import csv
import glob
import json
import mimetypes
from datetime import datetime
import subprocess
import sys

# Register MIME types
mimetypes.add_type('video/mp4', '.mp4')
mimetypes.add_type('video/webm', '.webm')
mimetypes.add_type('video/ogg', '.ogv')

app = Flask(__name__)
CORS(app)

# Configuration
BASE_DIR = "driver_monitoring_logs"
IMAGES_DIR = os.path.join(BASE_DIR, "images")
VIDEOS_DIR = os.path.join(BASE_DIR, "videos")
CONVERTED_DIR = os.path.join(VIDEOS_DIR, "converted")  # For converted videos
LOG_FILE = os.path.join(BASE_DIR, "events_log.csv")

# Ensure directories exist
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(VIDEOS_DIR, exist_ok=True)
os.makedirs(CONVERTED_DIR, exist_ok=True)

@app.route('/')
def index():
    """Main page"""
    return render_template('reviewer.html')

@app.route('/api/events')
def get_events():
    """Get all events from CSV"""
    events = []
    
    if not os.path.exists(LOG_FILE):
        events = create_sample_events()
    else:
        try:
            with open(LOG_FILE, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Format duration
                    try:
                        duration = float(row.get('duration_seconds', 0))
                        row['duration_seconds'] = round(duration, 1)
                    except:
                        row['duration_seconds'] = 0
                    
                    # Find actual files
                    timestamp = row.get('timestamp', '')
                    longitude = row.get('longitude', '')
                    latitude = row.get('latitude', '')
                    event_type = row.get('event_type', '').lower()
                    
                    # Find thumbnail
                    thumbnail = find_thumbnail(timestamp, event_type)
                    row['has_thumbnail'] = thumbnail is not None
                    row['thumbnail_url'] = f"/api/thumbnail/{timestamp}" if thumbnail else None
                    
                    # Find video (check both original and converted)
                    video = find_video(timestamp, event_type, row.get('filename', ''))
                    row['has_video'] = video is not None
                    row['video_url'] = f"/api/video/{timestamp}" if video else None
                    row['video_format'] = get_video_format(video) if video else None
                    
                    events.append(row)
        except Exception as e:
            print(f"Error loading events: {e}")
    
    # Sort by timestamp (newest first)
    events.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    return jsonify(events)

@app.route('/api/thumbnail/<timestamp>')
def get_thumbnail(timestamp):
    """Get thumbnail image for an event"""
    thumbnail_path = find_thumbnail_by_timestamp(timestamp)
    
    if thumbnail_path and os.path.exists(thumbnail_path):
        # Determine MIME type
        if thumbnail_path.endswith('.png'):
            mimetype = 'image/png'
        else:
            mimetype = 'image/jpeg'
        return send_file(thumbnail_path, mimetype=mimetype)
    else:
        abort(404, description="Thumbnail not found")

@app.route('/api/video/<timestamp>')
def get_video(timestamp):
    """Get video file for an event with proper MIME type"""
    video_path = find_video_by_timestamp(timestamp)
    
    if video_path and os.path.exists(video_path):
        # Get file size for range requests
        file_size = os.path.getsize(video_path)
        
        # Check if it's a converted video
        if 'converted' in video_path:
            print(f"Serving converted video: {video_path}")
        
        # Determine MIME type
        if video_path.endswith('.webm'):
            mimetype = 'video/webm'
        elif video_path.endswith('.ogv'):
            mimetype = 'video/ogg'
        else:
            mimetype = 'video/mp4'
        
        # Handle range requests for better seeking
        range_header = request.headers.get('Range', None)
        if not range_header:
            return send_file(video_path, mimetype=mimetype)
        
        # Parse range header
        byte1, byte2 = 0, None
        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if match:
            byte1 = int(match.group(1))
            if match.group(2):
                byte2 = int(match.group(2))
        
        if byte2 is None:
            byte2 = file_size - 1
        
        length = byte2 - byte1 + 1
        
        # Read the requested part of the file
        with open(video_path, 'rb') as f:
            f.seek(byte1)
            data = f.read(length)
        
        response = Response(data, 
                           status=206, 
                           mimetype=mimetype,
                           content_type=mimetype,
                           direct_passthrough=True)
        response.headers.add('Content-Range', f'bytes {byte1}-{byte2}/{file_size}')
        response.headers.add('Accept-Ranges', 'bytes')
        response.headers.add('Content-Length', str(length))
        
        return response
    else:
        abort(404, description="Video not found")

@app.route('/api/convert/<timestamp>', methods=['POST'])
def convert_video(timestamp):
    """Convert video to browser-friendly format"""
    video_path = find_original_video_by_timestamp(timestamp)
    
    if not video_path or not os.path.exists(video_path):
        return jsonify({'success': False, 'error': 'Video not found'}), 404
    
    # Create converted filename
    filename = os.path.basename(video_path)
    converted_path = os.path.join(CONVERTED_DIR, filename)
    
    # Check if already converted
    if os.path.exists(converted_path):
        return jsonify({'success': True, 'message': 'Video already converted'})
    
    try:
        # Convert to H.264 with faststart for web optimization
        subprocess.run([
            'ffmpeg', '-i', video_path,
            '-c:v', 'libx264', '-preset', 'fast',
            '-c:a', 'aac', '-b:a', '128k',
            '-movflags', '+faststart',
            '-y', converted_path
        ], check=True, capture_output=True)
        
        return jsonify({'success': True, 'message': 'Video converted successfully'})
    except subprocess.CalledProcessError as e:
        return jsonify({'success': False, 'error': f'Conversion failed: {e.stderr.decode()}'}), 500
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'ffmpeg not found. Please install ffmpeg.'}), 500

@app.route('/api/delete/<timestamp>', methods=['DELETE'])
def delete_event(timestamp):
    """Delete event files"""
    try:
        # Find and delete thumbnail
        thumbnail = find_thumbnail_by_timestamp(timestamp)
        if thumbnail and os.path.exists(thumbnail):
            os.remove(thumbnail)
        
        # Find and delete video (including converted)
        video = find_video_by_timestamp(timestamp)
        if video and os.path.exists(video):
            os.remove(video)
        
        # Check for converted version
        converted = find_converted_video_by_timestamp(timestamp)
        if converted and os.path.exists(converted):
            os.remove(converted)
        
        # Remove from CSV
        remove_from_csv(timestamp)
        
        return jsonify({'success': True, 'message': 'Event deleted'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/open-folder/<folder>')
def open_folder(folder):
    """Open folder in file explorer"""
    if folder == 'images':
        path = IMAGES_DIR
    elif folder == 'videos':
        path = VIDEOS_DIR
    elif folder == 'converted':
        path = CONVERTED_DIR
    else:
        path = BASE_DIR
    
    try:
        if sys.platform.startswith('linux'):
            subprocess.Popen(['xdg-open', path])
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        elif sys.platform == 'win32':
            os.startfile(path)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/check-ffmpeg')
def check_ffmpeg():
    """Check if ffmpeg is installed"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True)
        return jsonify({'installed': result.returncode == 0})
    except FileNotFoundError:
        return jsonify({'installed': False})

# ==================== Helper Functions ====================

def get_video_format(video_path):
    """Get video format for display"""
    if not video_path:
        return None
    if 'converted' in video_path:
        return 'converted'
    return 'original'

def find_thumbnail(timestamp, event_type):
    """Find thumbnail file by timestamp and type"""
    patterns = [
        os.path.join(IMAGES_DIR, f"{timestamp}_{event_type}_keyframe.jpg"),
        os.path.join(IMAGES_DIR, f"{timestamp}_{event_type}_keyframe.png"),
        os.path.join(IMAGES_DIR, f"{timestamp}_keyframe.jpg"),
        os.path.join(IMAGES_DIR, f"{timestamp}_keyframe.png"),
        os.path.join(IMAGES_DIR, f"{timestamp}*.jpg"),
    ]
    
    for pattern in patterns:
        if '*' in pattern:
            files = glob.glob(pattern)
            if files:
                return files[0]
        else:
            if os.path.exists(pattern):
                return pattern
    
    return None

def find_thumbnail_by_timestamp(timestamp):
    """Find thumbnail by timestamp only"""
    patterns = [
        os.path.join(IMAGES_DIR, f"{timestamp}_*_keyframe.jpg"),
        os.path.join(IMAGES_DIR, f"{timestamp}_keyframe.jpg"),
        os.path.join(IMAGES_DIR, f"{timestamp}*.jpg"),
    ]
    
    for pattern in patterns:
        files = glob.glob(pattern)
        if files:
            return files[0]
    
    return None

def find_video(timestamp, event_type, filename):
    """Find video file by timestamp and type (check converted first)"""
    # First check converted directory
    if filename:
        converted_path = os.path.join(CONVERTED_DIR, filename)
        if os.path.exists(converted_path):
            return converted_path
    
    # Try patterns in converted directory
    patterns = [
        os.path.join(CONVERTED_DIR, f"{timestamp}_{event_type}_*.mp4"),
        os.path.join(CONVERTED_DIR, f"{timestamp}_*.mp4"),
    ]
    
    for pattern in patterns:
        files = glob.glob(pattern)
        if files:
            return files[0]
    
    # Then check original videos directory
    if filename:
        original_path = os.path.join(VIDEOS_DIR, filename)
        if os.path.exists(original_path):
            return original_path
    
    patterns = [
        os.path.join(VIDEOS_DIR, f"{timestamp}_{event_type}_*.mp4"),
        os.path.join(VIDEOS_DIR, f"{timestamp}_*.mp4"),
        os.path.join(VIDEOS_DIR, f"*{timestamp}*.mp4"),
    ]
    
    for pattern in patterns:
        files = glob.glob(pattern)
        if files:
            return files[0]
    
    return None

def find_video_by_timestamp(timestamp):
    """Find video by timestamp only (check converted first)"""
    # Check converted first
    patterns = [
        os.path.join(CONVERTED_DIR, f"{timestamp}_*.mp4"),
        os.path.join(CONVERTED_DIR, f"*{timestamp}*.mp4"),
    ]
    
    for pattern in patterns:
        files = glob.glob(pattern)
        if files:
            return files[0]
    
    # Then check original
    patterns = [
        os.path.join(VIDEOS_DIR, f"{timestamp}_*.mp4"),
        os.path.join(VIDEOS_DIR, f"*{timestamp}*.mp4"),
    ]
    
    for pattern in patterns:
        files = glob.glob(pattern)
        if files:
            return files[0]
    
    return None

def find_original_video_by_timestamp(timestamp):
    """Find original (non-converted) video by timestamp"""
    patterns = [
        os.path.join(VIDEOS_DIR, f"{timestamp}_*.mp4"),
        os.path.join(VIDEOS_DIR, f"*{timestamp}*.mp4"),
    ]
    
    for pattern in patterns:
        files = glob.glob(pattern)
        if files:
            return files[0]
    
    return None

def find_converted_video_by_timestamp(timestamp):
    """Find converted video by timestamp"""
    patterns = [
        os.path.join(CONVERTED_DIR, f"{timestamp}_*.mp4"),
        os.path.join(CONVERTED_DIR, f"*{timestamp}*.mp4"),
    ]
    
    for pattern in patterns:
        files = glob.glob(pattern)
        if files:
            return files[0]
    
    return None

def remove_from_csv(timestamp):
    """Remove event from CSV file"""
    if not os.path.exists(LOG_FILE):
        return
    
    events = []
    with open(LOG_FILE, 'r') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row.get('timestamp') != timestamp:
                events.append(row)
    
    with open(LOG_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(events)

def create_sample_events():
    """Create sample events for testing"""
    return [
        {
            'timestamp': '20240315_143022',
            'longitude': 38.185718,
            'latitude': -78.395908,
            'event_type': 'DROWSY',
            'description': 'Drowsiness Detection',
            'duration_seconds': 2.5,
            'filename': '20240315_143022_drowsy_2.5s.mp4',
            'has_thumbnail': False,
            'has_video': False
        },
        {
            'timestamp': '20240315_143145',
            'longitude': 38.185718,
            'latitude': -78.395908,
            'event_type': 'LOOKING_RIGHT',
            'description': 'Looking Right',
            'duration_seconds': 3.2,
            'filename': '20240315_143145_looking_right_3.2s.mp4',
            'has_thumbnail': False,
            'has_video': False
        }
    ]

if __name__ == '__main__':
    import re  # Import for range request handling
    
    print("=" * 60)
    print("Driver Monitoring Event Viewer")
    print("=" * 60)
    print(f"Images directory: {IMAGES_DIR}")
    print(f"Videos directory: {VIDEOS_DIR}")
    print(f"Converted videos: {CONVERTED_DIR}")
    print(f"Log file: {LOG_FILE}")
    print("=" * 60)
    
    # Check ffmpeg
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True)
        print("✅ ffmpeg is installed")
    except FileNotFoundError:
        print("⚠️  ffmpeg not found. Video conversion will not work.")
        print("   Install ffmpeg for better video compatibility:")
        print("   sudo apt install ffmpeg  # Ubuntu/Debian")
        print("   brew install ffmpeg       # macOS")
        print("   choco install ffmpeg      # Windows")
    
    print("\nStarting web server...")
    print("Open your browser and go to: http://localhost:5000")
    print("\nPress Ctrl+C to stop the server")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)