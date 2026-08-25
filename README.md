# HabitForge — Habit Tracker

FastAPI + browser habit tracker with a red / yellow / black animated UI.

## Storage

The live tracker data is stored in:

`data/habit_data.csv`

The first run automatically imports the existing `Goal_Habit_Tracker_2026_2027.xlsx` from the `data` folder into CSV. After that, the app reads and writes the CSV, so the app can be stopped and restarted every day without losing previous entries and without Excel file-locking problems.

Timestamped `.bak` backups are created before every save/clear operation.

## Run on Windows

```powershell
py -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Open `http://127.0.0.1:8000`.

## Run on Linux / Ubuntu

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Daily usage

1. Start the app when you want to record progress.
2. Open **Daily**.
3. Select the date.
4. Mark each habit and add notes.
5. Click **SAVE CHECK-IN**.
6. Stop the app when finished.

Previous days remain stored in `habit_data.csv`. Weekly, monthly and date-range reports are calculated from all saved check-ins.

## Important

Do not delete or rename `data/habit_data.csv` after the first migration unless you intentionally want to recreate it from the original Excel workbook.
