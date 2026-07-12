# Driver Monitoring System

A Raspberry Pi 5 and computer-vision prototype developed during a Telematics GPS, LLC cybersecurity and software engineering internship and George Mason University capstone. The project researched how an existing fleet-tracking environment could evolve toward a newer driver-monitoring system and, ultimately, a future AI-enabled dashcam offering.

> [!IMPORTANT]
> This repository represents the working driver-monitoring prototype and its local event-review interface. It does not claim that a commercial AI dashcam was deployed. The dashcam was a researched future implementation path evaluated alongside migration to a newer GPS tracking platform.

## Professional Context

| Project detail | Scope |
| --- | --- |
| Organization | Telematics GPS, LLC |
| Engagement | Cybersecurity and Software Engineering Internship / George Mason University capstone |
| Role | Team Lead |
| Timeline | August 2025 - April 2026 |
| Objective | Research, prototype, and evaluate a driver-safety monitoring capability for a fleet and telematics environment |
| Hardware | Raspberry Pi 5, Raspberry Pi AI Camera, and GPS integration |
| Future direction | Evaluate migration to a newer GPS platform and explore an AI dashcam product offering |

## Research-to-Implementation Story

The work connected business research with a functioning technical prototype:

1. **Research and requirements** - Evaluated driver-safety use cases, fatigue and distraction indicators, fleet event-review needs, and the organization's future GPS-platform direction.
2. **Prototype development** - Built an AI-powered monitoring workflow using a Raspberry Pi 5 and computer vision to detect fatigue and distraction behaviors in real time.
3. **Hardware and data integration** - Connected camera-based detection with GPS coordinates, timestamps, incident metadata, thumbnails, and video clips.
4. **Operational review** - Developed a local Flask dashboard so recorded safety events could be filtered, reviewed, played back, downloaded, and managed.
5. **Future-product evaluation** - Used the prototype and research findings to explore how a future AI dashcam solution could complement a newer GPS tracking platform.

Prototype testing achieved approximately 90% behavioral detection accuracy under the conditions used during the project. Business evaluation estimated that a fully implemented AI dashcam offering could increase projected subscription revenue by approximately 33% per vehicle. These figures describe prototype testing and future projections, not production results.

## What This Repository Demonstrates

- Translating research and stakeholder needs into a working technical prototype
- Detecting potential fatigue and distraction behaviors with computer vision
- Integrating Raspberry Pi hardware, an AI camera, and GPS event data
- Recording timestamps, incident types, coordinates, thumbnails, and video clips
- Reviewing events through a browser-based Flask dashboard
- Supporting HTTP range requests for responsive video playback
- Converting recordings to browser-friendly H.264 with FFmpeg
- Applying privacy-conscious source-control practices for driver and location data

## Technology

| Area | Tools |
| --- | --- |
| Backend | Python, Flask, Flask-CORS |
| Computer vision target | Raspberry Pi AI Camera |
| Hardware | Raspberry Pi 5 and GPS module |
| Media | FFmpeg, MP4, WebM, OGG |
| Data | CSV event logs and local media files |
| Interface | HTML, CSS, JavaScript |

## System Architecture

```text
Raspberry Pi AI Camera
          |
          v
Fatigue / distraction detection
          |
          +---- GPS coordinates
          +---- timestamp
          +---- incident metadata
          +---- thumbnail / video clip
          |
          v
driver_monitoring_logs/
          |
          v
Flask review API and dashboard
          |
          v
Local browser-based safety review
```

The repository contains the event-review component of the prototype. Complete camera-capture, detection-model, and production telematics-platform assets are outside this public repository.

## Getting Started

### Prerequisites

- Python 3.10 or newer
- FFmpeg, required only for video conversion

### Installation

```bash
git clone https://github.com/zavanf/driver-monitoring-system.git
cd driver-monitoring-system
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate the environment with `.venv\Scripts\activate`.

### Run Locally

```bash
python web_reviewer.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). If no event log exists, the API returns clearly identified placeholder events for interface testing.

## Expected Local Data Layout

```text
driver_monitoring_logs/
|-- events_log.csv
|-- images/
`-- videos/
    `-- converted/
```

The viewer uses event fields such as `timestamp`, `event_type`, `duration_seconds`, and `filename`. GPS fields may be included for map links.

## Privacy and Security

- Real driver footage, images, GPS coordinates, and event logs are intentionally excluded from source control.
- Placeholder coordinates are used for public demonstration data.
- The Flask server binds to localhost by default.
- The current application is a local research prototype and does not include production authentication.
- Authentication, authorization, input validation, encrypted storage, retention controls, consent procedures, and restricted CORS would be required before deployment.

## Project Status

Completed research and portfolio prototype from the 2025-2026 internship and capstone engagement. The project demonstrates the technical foundation and evaluation process for a potential future driver-monitoring and AI dashcam solution; commercial deployment and production hardening were outside the scope of this repository.
