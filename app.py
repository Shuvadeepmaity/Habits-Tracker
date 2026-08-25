from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime
import shutil
import csv
import os
import math
import tempfile
import pandas as pd
from openpyxl import load_workbook

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
DATA_DIR.mkdir(exist_ok=True)

# CSV is the live data store. Unlike an Excel workbook, it can be updated
# reliably from the web app without Excel file-locking issues.
DATA_FILE = DATA_DIR / "habit_data.csv"
LEGACY_WORKBOOK = DATA_DIR / "Goal_Habit_Tracker_2026_2027.xlsx"

EXCLUDE_DAILY = {"Date", "Day", "Daily Score %", "Notes"}

class DailyUpdate(BaseModel):
    date: str
    values: dict[str, str]
    notes: str = ""

class ChatRequest(BaseModel):
    message: str

class ClearRequest(BaseModel):
    start: str
    end: str
    scope: str = "daily"

app = FastAPI(title="Habit Tracker")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))

def atomic_write_csv(df: pd.DataFrame):
    """Write the complete CSV atomically so a browser request cannot leave
    the data file half-written if the process is interrupted."""
    fd, tmp_name = tempfile.mkstemp(prefix="habit_", suffix=".csv", dir=DATA_DIR)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        df.to_csv(tmp, index=False, encoding="utf-8-sig", lineterminator="\n")
        os.replace(tmp, DATA_FILE)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)

def backup_data():
    if DATA_FILE.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(DATA_FILE, DATA_DIR / f"habit_data_{stamp}.bak")

def migrate_excel_to_csv():
    """One-time migration from the supplied workbook."""
    if DATA_FILE.exists():
        return

    if not LEGACY_WORKBOOK.exists():
        raise FileNotFoundError(
            f"No data file found. Expected {DATA_FILE.name} or {LEGACY_WORKBOOK.name}"
        )

    df = pd.read_excel(LEGACY_WORKBOOK, sheet_name="Daily Tracker", engine="openpyxl")
    if "Date" not in df.columns:
        raise ValueError("Daily Tracker sheet must contain a Date column.")

    # Keep the workbook's structure, but convert formulas to stored numeric
    # values where possible. The app itself calculates scores, so the formula
    # column is not required for future operation.
    if "Daily Score %" in df.columns:
        df["Daily Score %"] = pd.to_numeric(df["Daily Score %"], errors="coerce")

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df[df["Date"].notna()].copy()

    for c in df.columns:
        if c != "Date":
            df[c] = df[c].where(pd.notna(df[c]), "")

    atomic_write_csv(df)

def load_daily() -> pd.DataFrame:
    migrate_excel_to_csv()
    df = pd.read_csv(DATA_FILE, encoding="utf-8-sig", dtype=str, keep_default_na=False)

    if "Date" not in df.columns:
        raise ValueError("habit_data.csv must contain a Date column.")

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df

def habit_cols(df):
    return [c for c in df.columns if c not in EXCLUDE_DAILY]

def score_row(row, cols):
    marks = [str(row.get(c, "")).strip() for c in cols]
    # A blank row is not a tracked day.
    if not any(v in ("✓", "✗") for v in marks):
        return None
    # Score is always out of all configured habits, including missed/unfilled
    # habits, so a partial check-in cannot artificially become 100%.
    return sum(v == "✓" for v in marks) / len(cols) if cols else None

def build_stats(start=None, end=None):
    df = load_daily()
    cols = habit_cols(df)
    work = df.dropna(subset=["Date"]).copy()

    if start:
        work = work[work["Date"] >= pd.Timestamp(start)]
    if end:
        work = work[work["Date"] <= pd.Timestamp(end)]

    work["score"] = work.apply(lambda r: score_row(r, cols), axis=1)
    completed = work[work["score"].notna()].copy()

    avg = float(completed["score"].mean()) if len(completed) else 0.0
    completed = completed.sort_values("Date")
    daily_labels = completed["Date"].dt.strftime("%Y-%m-%d").tolist()
    daily_scores = [round(float(x) * 100, 1) for x in completed["score"]]

    if len(completed):
        # Week starts on Monday.
        completed["week"] = completed["Date"] - pd.to_timedelta(
            completed["Date"].dt.weekday, unit="D"
        )
        weekly = completed.groupby("week")["score"].mean().reset_index()
        weekly_labels = weekly["week"].dt.strftime("%Y-%m-%d").tolist()
        weekly_scores = [round(float(x) * 100, 1) for x in weekly["score"]]

        completed["month"] = completed["Date"].dt.to_period("M").dt.to_timestamp()
        monthly = completed.groupby("month")["score"].mean().reset_index()
        monthly_labels = monthly["month"].dt.strftime("%Y-%m").tolist()
        monthly_scores = [round(float(x) * 100, 1) for x in monthly["score"]]
    else:
        weekly_labels, weekly_scores, monthly_labels, monthly_scores = [], [], [], []

    habit_avgs = {}
    for c in cols:
        marks = completed[c].astype(str).str.strip()
        valid = marks.isin(["✓", "✗"])
        habit_avgs[c] = (
            round(float((marks[valid] == "✓").mean() * 100), 1)
            if valid.any() else 0.0
        )

    return {
        "avg": round(avg * 100, 1),
        "days": int(len(completed)),
        "daily": {"labels": daily_labels, "scores": daily_scores},
        "weekly": {"labels": weekly_labels, "scores": weekly_scores},
        "monthly": {"labels": monthly_labels, "scores": monthly_scores},
        "habit_avgs": habit_avgs,
        "habit_columns": cols,
    }

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/stats")
def stats(start: str | None = None, end: str | None = None):
    return JSONResponse(build_stats(start, end))

@app.get("/api/daily")
def daily(start: str | None = None, end: str | None = None):
    df = load_daily()
    if start:
        df = df[df["Date"] >= pd.Timestamp(start)]
    if end:
        df = df[df["Date"] <= pd.Timestamp(end)]

    output = df.copy()
    output["Date"] = output["Date"].dt.strftime("%Y-%m-%d")
    output = output.fillna("")
    rows = output.to_dict(orient="records")

    return {
        "columns": list(output.columns),
        "rows": rows,
        "habit_columns": habit_cols(output),
    }

@app.post("/api/daily")
def update_daily(payload: DailyUpdate):
    try:
        target = pd.Timestamp(payload.date).normalize()
    except Exception:
        raise HTTPException(400, "Invalid date")

    df = load_daily()
    cols = list(df.columns)
    if "Date" not in cols or "Day" not in cols:
        raise HTTPException(500, "CSV is missing Date or Day column.")

    # Ensure all incoming fields already exist; never create arbitrary columns
    # from browser input.
    valid_values = {k: v for k, v in payload.values.items() if k in cols}

    date_series = pd.to_datetime(df["Date"], errors="coerce")
    matches = date_series.dt.normalize() == target

    if matches.any():
        idx = df.index[matches][0]
    else:
        idx = len(df)
        df.loc[idx, :] = ""
        df.at[idx, "Date"] = target.strftime("%Y-%m-%d")
        df.at[idx, "Day"] = target.strftime("%A")

    # Start from a clean daily state only for fields the UI actually submits.
    for col, value in valid_values.items():
        df.at[idx, col] = value if value in ("✓", "✗") else ""

    if "Notes" in cols:
        df.at[idx, "Notes"] = payload.notes.strip()

    habit_columns = habit_cols(df)
    marks = [str(df.at[idx, c]).strip() for c in habit_columns]
    score = sum(v == "✓" for v in marks) / len(habit_columns) if habit_columns else 0

    if "Daily Score %" in cols:
        df.at[idx, "Daily Score %"] = str(round(score, 6))

    # Keep dates sorted so the CSV remains easy to inspect manually.
    df["__sort_date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.sort_values("__sort_date").drop(columns="__sort_date").reset_index(drop=True)

    backup_data()
    atomic_write_csv(df)

    return {"ok": True, "score": round(score * 100, 1), "storage": DATA_FILE.name}

@app.post("/api/clear")
def clear_data(payload: ClearRequest):
    if payload.scope != "daily":
        raise HTTPException(400, "Only daily range clearing is enabled.")

    try:
        start = pd.Timestamp(payload.start).normalize()
        end = pd.Timestamp(payload.end).normalize()
    except Exception:
        raise HTTPException(400, "Invalid date range")

    if start > end:
        raise HTTPException(400, "Start date cannot be after end date")

    df = load_daily()
    dates = pd.to_datetime(df["Date"], errors="coerce")
    mask = dates.between(start, end, inclusive="both")

    protected = {"Date", "Day"}
    for col in df.columns:
        if col not in protected:
            df.loc[mask, col] = ""

    backup_data()
    atomic_write_csv(df)

    return {"ok": True, "cleared": int(mask.sum())}

@app.post("/api/chat")
def chat(payload: ChatRequest):
    msg = payload.message.lower().strip()
    s = build_stats()
    avg = s["avg"]
    days = s["days"]

    if any(x in msg for x in ["average", "avg", "score"]):
        answer = f"Your current average daily score is {avg:.1f}% across {days} tracked day(s)."
    elif "best" in msg:
        labels, scores = s["daily"]["labels"], s["daily"]["scores"]
        if scores:
            i = scores.index(max(scores))
            answer = f"Your best tracked day is {labels[i]} with a score of {scores[i]:.1f}%."
        else:
            answer = "I don't have enough completed days to identify your best day."
    elif "worst" in msg or "weak" in msg:
        labels, scores = s["daily"]["labels"], s["daily"]["scores"]
        if scores:
            i = scores.index(min(scores))
            answer = f"Your weakest tracked day is {labels[i]} with a score of {scores[i]:.1f}%. Focus on consistency rather than perfection."
        else:
            answer = "I don't have enough completed days to identify a weak day."
    elif "habit" in msg:
        pairs = sorted(s["habit_avgs"].items(), key=lambda x: x[1])
        if pairs:
            answer = (
                "Your weakest habit is " + pairs[0][0] +
                f" ({pairs[0][1]:.1f}%). Your strongest is " +
                pairs[-1][0] + f" ({pairs[-1][1]:.1f}%)."
            )
        else:
            answer = "No completed habit data is available yet."
    elif "help" in msg:
        answer = "Try: 'What is my average?', 'What is my best day?', 'Which habit is weakest?', or 'Give me a quick summary.'"
    else:
        answer = (
            f"Quick summary: {days} tracked day(s), average score {avg:.1f}%. "
            "Ask me about your average, best/worst day, or weakest habit."
        )
    return {"answer": answer}
