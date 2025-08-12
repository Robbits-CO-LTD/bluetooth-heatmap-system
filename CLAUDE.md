# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bluetooth-based motion analysis and heatmap system for tracking visitor movement in facilities (offices, supermarkets, factories, warehouses) using BLE signals. Provides real-time tracking, trajectory analysis, dwell time analysis, and flow visualization while maintaining privacy through MAC address anonymization.

## System Architecture

### Core Data Flow
```
BLE Devices → Scanner(s) → DeviceManager → PositionCalculator → Analysis Modules → Database/API → Visualization
```

### Async Processing Architecture
The system uses 4 concurrent async loops in `src/main.py`:
1. **Scanning Loop** (`_scanning_loop`): BLE device detection at configurable intervals
2. **Analysis Loop** (`_analysis_loop`): Position processing and analysis module updates
3. **Maintenance Loop** (`_maintenance_loop`): Hourly data cleanup
4. **Reporting Loop** (`_reporting_loop`): Periodic report generation

### Key Architectural Decisions
- **Zone-Centric Analysis**: All business logic operates on zones rather than raw coordinates to reduce data volume and improve query performance
- **Multi-Receiver Positioning**: Auto-detects receiver count and switches between distance-only (1 receiver) and trilateration (3+ receivers)
- **Privacy-First**: MAC addresses immediately hashed, original MACs never stored
- **Event-Driven**: Non-blocking I/O for all external operations with graceful degradation
- **Position Distribution**: Uses golden angle algorithm for even device distribution when using single receiver

## Essential Commands

### Development Setup
```bash
# Virtual environment and dependencies
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt

# Environment configuration
copy .env.example .env  # Then edit .env with your settings

# Database initialization (requires PostgreSQL, TimescaleDB optional)
python scripts/init_db.py
python scripts/init_db.py --check  # Check database status
python scripts/init_db.py --reset  # Reset database (destructive)
```

### Running Components
```bash
# API Server (works without database for testing)
uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000
# OpenAPI docs: http://localhost:8000/docs

# Dashboard (standalone)
python -c "from src.visualization.dashboard import Dashboard; Dashboard({}).run()"
# Access at: http://localhost:8050

# Main Application (requires full setup)
python src/main.py

# WebSocket test endpoints
GET /api/v1/realtime/status  # Check WebSocket status
WS  /api/v1/realtime/ws      # WebSocket connection
```

### Testing Bluetooth
```bash
# Test Bluetooth scanning directly
python -m src.core.scanner

# Check Bluetooth service (Windows)
net start bthserv
```

## Configuration Hierarchy

1. **config/config.yaml**: System-wide settings
   - Contains `${ENV_VAR}` placeholders resolved from .env
   - Scanning parameters, positioning algorithms, analysis thresholds
   
2. **config/layouts/**: Facility geometry files
   - `office_room.yaml`: Office layout (20m x 15m)
   - `supermarket_a.yaml`: Supermarket layout example
   - Zone polygons determine position assignment
   - Receiver count affects positioning capability (≥3 for trilateration)
   
3. **.env**: Deployment-specific secrets
   - Database credentials, API keys, service endpoints
   - Copy from .env.example and customize
   - Set `TIMESCALE_ENABLED=false` if TimescaleDB not available

## API Structure

### Route Organization
```
src/api/
├── app.py              # FastAPI application, lifespan management
├── websocket.py        # WebSocket connection manager
├── schemas/            # Pydantic models for request/response
│   ├── device.py       # Device, trajectory schemas
│   ├── analytics.py    # Analysis result schemas
│   └── heatmap.py      # Heatmap data schemas
└── routes/             # API endpoints
    ├── devices.py      # Device CRUD operations (limit: 500 default, 10000 max)
    ├── trajectories.py # Trajectory tracking
    ├── dwell_time.py   # Dwell time analysis
    ├── flow.py         # Flow matrix and transitions
    ├── heatmap.py      # Heatmap generation
    ├── analytics.py    # Combined analytics
    ├── reports.py      # Report generation
    └── realtime.py     # WebSocket real-time updates
```

### WebSocket Channels
Subscribe to channels via WebSocket at `/api/v1/realtime/ws`:
- `positions`: Device position updates (1s interval)
- `heatmap`: Zone density updates (5s interval)
- `analytics`: Statistical updates (10s interval)
- `alerts`: Real-time alerts (event-driven)

## Database Architecture

### TimescaleDB Hypertables (Optional)
- `trajectory_points`: Time-series position data with automatic chunking
- `detections`: Raw BLE detection events
- `heatmap_data`: Aggregated density grids

### Repository Pattern
All database operations go through repositories in `src/database/repositories.py`:
- Direct SQL avoided in business logic
- Batch operations for performance (threshold: 100)
- Automatic connection pooling (5-20 connections)
- Default query limits: 500 items (was 100)

## Adding New Features

### New Analysis Module
1. Create analyzer in `src/analysis/` following existing patterns
2. Initialize in `MotionAnalysisSystem.__init__`
3. Add to appropriate processing loop or create new one
4. Update `_log_statistics` for metrics
5. Add config section to `config.yaml`

### New API Endpoint
1. Create route module in `src/api/routes/`
2. Define Pydantic schemas in `src/api/schemas/`
3. Implement repository methods if needed
4. Register route in `src/api/app.py`
5. Test via OpenAPI docs at `/docs`

### New Position Algorithm
1. Add method to `PositionCalculator` class
2. Update `calculate_position` method's algorithm selection
3. Add config parameters to `positioning` section
4. Document receiver requirements

### New Facility Layout
1. Create YAML file in `config/layouts/`
2. Define zones with polygons (list of [x, y] coordinates)
3. Add receivers if using multiple (≥3 for trilateration)
4. Update config.yaml to reference new layout

## Windows-Specific Notes

- Bluetooth requires Windows 10+ with Bluetooth 4.0+
- May need Administrator privileges for BLE access
- `WindowsProactorEventLoopPolicy` set in main.py for Bluetooth compatibility
- All internal paths use forward slashes
- Use `cmd` commands in documentation examples

## Performance Considerations

### Memory Limits
- DeviceManager keeps last 100 positions per device
- Scanner maintains last 1000 detections
- TrajectoryAnalyzer clears points after finalization

### Database Optimization
- TimescaleDB chunks by day with 90-day retention (when enabled)
- Batch inserts for trajectory points (100 point threshold)
- Zone-based aggregation reduces raw data volume
- API returns up to 500 devices by default (configurable to 10000)

### Position Calculation
- Single receiver: Golden angle distribution for device separation
- RSSI normalization: -90 to -30 dBm mapped to distance
- Position updates include time-based variation for natural movement

## Common Issues

### API Import Errors
- Ensure working directory is project root
- Check PYTHONPATH includes project root
- Verify virtual environment is activated

### No BLE Devices Detected
- Check RSSI threshold in config (default -90)
- Verify Bluetooth enabled and receivers configured
- Try running with Administrator privileges on Windows
- Check Bluetooth service: `net start bthserv`

### Database Connection Failed
- Verify PostgreSQL running and .env credentials correct
- TimescaleDB is optional: set `TIMESCALE_ENABLED=false` if not installed
- Check connection pooling settings if under load

### Devices Clustering at One Point
- Fixed in latest version using golden angle distribution
- Check that position calculation logs show different angles
- Verify API returns current_x and current_y values

### Device Count Stops at 100
- Fixed: Default limit increased to 500
- Can request up to 10000 with `limit` parameter
- Check both API and repository limits

## Current Implementation Status

### ✅ Fully Implemented
- Core BLE scanning and device management
- Position calculation with golden angle distribution
- Analysis modules (trajectory, dwell time, flow)
- Database layer with repository pattern
- FastAPI with all endpoints and WebSocket
- Visualization (heatmap, flow, dashboard)
- Office room layout configuration

### 🚧 Partial/Pending
- Unit and integration tests (only 3 tests exist)
- Docker configuration (files exist but untested)
- Web frontend (separate from dashboard)
- Desktop GUI application

## Design Document Reference

Original design document: `bluetooth-heatmap-design.md` (Japanese)
Implementation status: `docs/IMPLEMENTATION_STATUS.md`