# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bluetooth-based real-time motion tracking and heatmap system for facilities (offices, supermarkets, warehouses). Tracks visitor movement using BLE signals with privacy-preserving MAC address hashing. Provides trajectory analysis, dwell time metrics, flow visualization, and real-time alerts.

## System Architecture

### Core Data Flow
```
BLE Devices → Scanner → DeviceManager → PositionCalculator → Analysis Modules → Database/API → Dashboard
```

### Concurrent Processing (src/main.py)
- **Scanning Loop** (3s interval): BLE device detection and position updates
- **Analysis Loop** (10s): Trajectory/dwell time/flow analysis
- **Maintenance Loop** (1h): Database cleanup, old device removal
- **Reporting Loop** (30m): Analytics report generation

### Key Design Decisions
- **Zone-based processing**: Reduces data volume, improves performance
- **Golden angle positioning**: Distributes devices evenly with single receiver
- **Real-time cleanup**: Devices removed after 5s without detection
- **Duplicate prevention**: UNIQUE constraint on device_id, application-level checks

## Essential Commands

### Quick Start
```bash
# Setup
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env

# Run without database (testing)
uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000

# Dashboard
python -c "from src.visualization.dashboard import Dashboard; Dashboard({}).run()"

# Full system (requires PostgreSQL)
python scripts/init_db.py
python src/main.py
```

### Development
```bash
# Tests
make test                    # Run all tests
pytest tests/unit -v        # Unit tests only
pytest --cov=src tests/     # With coverage

# Code quality
make format                  # black + isort
make lint                   # flake8 + mypy
make clean                  # Remove temp files

# Database
make init-db                # Initialize
make check-db              # Check status
make reset-db              # Reset (destructive)

# Services
make run-api               # API server
make run-dashboard         # Dashboard
make run-all              # All services
```

## Configuration

### config/config.yaml
- Scanning: interval=3s, duration=2.5s, rssi_threshold=-100
- Device cleanup: 5s timeout (was 10s)
- API defaults: active_only=True, 30s window

### config/layouts/office_room.yaml
- 20m x 15m office with 3 zones:
  - entrance: Entry point
  - open_office: Main workspace
  - president_room: Executive office

### .env Variables
```
DB_HOST=localhost
DB_NAME=bluetooth_tracking
DB_USER=postgres
DB_PASSWORD=your_password
TIMESCALE_ENABLED=false    # Set true if TimescaleDB installed
```

## API Endpoints

### Device Management
- `GET /api/v1/devices?active_only=true` - Returns devices seen in last 30s
- `GET /api/v1/devices/{device_id}` - Single device details
- Default limit: 500 (max: 10000)

### Analytics
- `GET /api/v1/heatmap/current` - Current density map
- `GET /api/v1/dwell-time/current` - Zone dwell times
- `GET /api/v1/flow/transitions` - Zone-to-zone movements
- `WS /api/v1/realtime/ws` - WebSocket for live updates

## Dashboard Features

### KPI Cards
- **Active Devices**: Currently detected (30s window)
- **Average Dwell Time**: Calculated from first_seen to last_seen
- **Total Visitors**: Unique devices today
- **Alerts**: Long dwell (>30min), crowding (>10/zone), anomaly (>50 total)

### Visualizations
- **Heatmap**: Real-time device positions with Gaussian overlay
- **Zone Occupancy**: Bar chart with color-coded thresholds
- **Visitor Trend**: 1-hour timeline, 5-minute intervals
- **Popular Routes**: Top 5 zone transitions

## Recent Fixes & Improvements

### Device Duplicate Prevention
- DeviceManager.register_device() returns None for existing devices
- DataIntegration logs [SAVED] for new, [UPDATED] for existing
- Database UNIQUE constraint on device_id field

### Real-time Responsiveness
- Cleanup timeout: 10s → 5s
- API active window: 5min → 30s
- Scan interval: 5s → 3s
- Default active_only=true for API

### Dashboard Enhancements
- Added alert system with severity levels
- Implemented visitor trend graph
- Added popular routes visualization
- Fixed average dwell time calculation

## Common Issues & Solutions

### No Devices Detected
```bash
net start bthserv           # Start Bluetooth service (Windows)
# Check config: rssi_threshold=-100 (more sensitive)
# Run as Administrator if needed
```

### Database Connection Failed
```bash
# PostgreSQL not required for testing
# Set TIMESCALE_ENABLED=false in .env
# API and dashboard work without database
```

### Import Errors
```bash
# Ensure venv activated
venv\Scripts\activate
# Install dependencies
pip install -r requirements.txt
```

### Device Count Growing
- Fixed: Devices now removed after 5s without detection
- API returns only active devices by default
- Dashboard shows real-time counts

## Performance Optimization

### Current Limits
- DeviceManager: 100 positions/device history
- Scanner: 1000 detection buffer
- API: 500 devices default (10k max)
- Batch inserts: 100 point threshold

### Position Calculation
- Single receiver uses golden angle (2.39996 rad) for distribution
- RSSI range: -90 to -30 dBm → distance mapping
- Time-based variation for natural movement simulation

## Windows-Specific Notes

- Requires Windows 10+ with Bluetooth 4.0+
- Uses WindowsProactorEventLoopPolicy for async Bluetooth
- Administrator privileges may be needed for BLE
- All paths use forward slashes internally

## Incomplete Features (TODO)

Several API endpoints return mock data:
- `/api/v1/flow/*` - Flow analysis endpoints
- `/api/v1/analytics/visitor-trend` - Historical trends
- `/api/v1/reports/*` - Report generation
- Unit tests coverage (<5% implemented)
- Docker deployment (untested)

## Architecture Patterns

### Repository Pattern
All database operations through `src/database/repositories.py`:
- No direct SQL in business logic
- Automatic connection pooling
- Batch operations for performance

### Device Lifecycle
1. Scanner detects MAC address
2. DeviceManager hashes MAC → device_id
3. Position calculated (golden angle if single receiver)
4. Zone assigned based on polygon boundaries
5. Analysis modules update metrics
6. API/Dashboard display real-time data
7. Cleanup after timeout

### Alert System
Monitors three conditions:
- Long dwell: >30min (medium), >60min (high)
- Crowding: >10/zone (low), >15/zone (medium)
- Anomaly: >50 total devices (high)