# driver-monitoring-system
A computer vision-based driver monitoring system designed to detect fatigue and distracted driving behaviors using a Raspberry Pi 5 and a Raspberry Pi AI Camera.

# Driver Monitoring System
A computer vision-based driver monitoring system designed to detect fatigue and distracted driving behaviors using a Raspberry Pi 5 and a Raspberry Pi AI camera.

## Technologies
- Python
- Raspberry Pi 5
- Raspberry Pi AI Camera
- Computer Vision
- HTML/CSS/JavaScript
- Flask Web Interface

## Overview
This project implements a driver safety monitoring system that analyzes facial landmarks and eye movement to detect signs of driver fatigue or distraction.

Using computer vision techniques, the system monitors indicators such as eye closure and facial positioning. When unsafe behavior is detected, the system records timestamps, GPS coordinates, and safety-related events for later review.

## Hardware
- Raspberry Pi 5
- Raspberry Pi AI Camera
- GPS Module (Adafruit GPS HAT)

## Features
- Detects potential driver fatigue
- Monitors facial landmarks and eye movement
- Detects distracted driving behaviors
- Records safety-related events with timestamps
- Stores GPS coordinates for detected events
- Saves event thumbnails and video clips
- Web dashboard for reviewing driver events
- Video playback and download support
- Automatic event logging and management
- Demonstrates integration between embedded hardware and computer vision software

## Web Dashboard
The system includes a responsive browser-based dashboard for reviewing recorded driver monitoring events.

## Dashboard Features
- Event log viewer with timestamps and descriptions
- Video preview and playback support
- Thumbnail previews for recorded events
- GPS location links using Google Maps
- Event filtering and management
- Video conversion support using FFmpeg
- Download and delete functionality
- Auto-refreshing event updates

## Purpose
The goal of this project is to demonstrate how embedded systems and computer vision can improve driver safety through automated monitoring, fatigue detection, and event-based recording.

This project also demonstrates practical integration between AI-powered vision systems, embedded hardware, GPS tracking, and a custom-built web interface for real-time event review and analysis.
