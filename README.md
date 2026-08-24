# Habit Tracker — FastAPI + Excel

A local browser habit tracker built around your existing `Goal_Habit_Tracker_2026_2027.xlsx`.

## Features
- Red / yellow / black animated UI
- Progress Report, Daily, Weekly, Monthly tabs
- Existing Excel workbook is loaded automatically
- Daily habit entry using ✓ / ✗
- Daily score calculated from the 11 habits
- Weekly and monthly progress charts
- Average score cards
- Date-range filtering
- Safe data clearing with confirmation
- Data is written back to the same Excel workbook
- Built-in lightweight progress chat (no API key required)

## Run on Windows

```powershell
cd habit_tracker_app
py -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Open: http://127.0.0.1:8000

The app expects the workbook at:

`data/Goal_Habit_Tracker_2026_2027.xlsx`

If you want to use another workbook, replace that file while keeping the sheet names:
- Dashboard
- Daily Tracker
- Weekly Review
- Monthly Goals
- Instructions

## Linux / Ubuntu

```bash
cd habit_tracker_app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Backup

Before destructive operations, the app automatically creates a timestamped `.bak` copy of the workbook.
