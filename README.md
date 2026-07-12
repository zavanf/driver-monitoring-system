# Driver Monitoring System

A Raspberry Pi–based prototype for reviewing driver-safety events produced by a computer-vision monitoring workflow. The application organizes event metadata, GPS coordinates, thumbnails, and video clips in a local Flask dashboard.

> [!IMPORTANT]
> This repository is a local prototype and portfolio demonstration. It is not production-ready, does not include authentication, and should not be exposed directly to the public internet.

## Highlights

- Reviews fatigue and distraction events in a browser
- Associates events with timestamps and GPS coordinates
- Displays captured thumbnails and video clips
- Supports HTTP range requests for responsive video playback
- Converts recordings to browser-friendly H.264 with FFmpeg
- Filters, downloads, and deletes locally stored events
- Keeps real driver footage and location logs out of source control

## Technology

| Area | Tools |
| --- | --- |
| Backend | Python, Flask, Flask-CORS |
| Media | FFmpeg, MP4/WebM/OGG |
| Hardware target | Raspberry Pi 5, Raspberry Pi AI Camera, GPS module |
| Data | CSV event logs and local media files |
| Interface | HTML, CSS, JavaScript |

## Architecture

```text
Camera / detection pipeline
          |
          v
driver_monitoring_logs/
  events_log.csv
  images/
  videos/
          |
          v
Flask review API + dashboard
          |
          v
Browser-based event review
```

The repository contains the review application. Camera capture and model-training assets are outside this repository.

## Getting Started

### Prerequisites

- Python 3.10 or newer
- FFmpeg (optional, required only for video conversion)

### Installation

```bash
git clone https://github.com/zavanf/driver-monitoring-system.git
cd driver-monitoring-system
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate the environment with `.venv\Scripts\activate`.

### Run locally

```bash
python web_reviewer.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). When no event log is present, the API returns placeholder sample events.

## Expected Data Layout

```text
driver_monitoring_logs/
├── events_log.csv
├── images/
└── videos/
    └── converted/
```

The event log is expected to contain fields used by the viewer, including `timestamp`, `event_type`, `duration_seconds`, and `filename`. GPS fields may be included for map links.

## Privacy and Security

- Do not commit real driver footage, images, GPS coordinates, or event logs.
- The server binds to localhost by default.
- CORS is enabled for local development.
- Add authentication, authorization, validation, encrypted storage, and restricted CORS before any network deployment.

## Project Status

Portfolio prototype. The event review workflow is implemented; production hardening, automated tests, and integration with a complete capture/detection pipeline remain future work.
