from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime, date
import shutil
import tempfile
import os
import math
import pandas as pd
from openpyxl import load_workbook

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
DATA_DIR.mkdir(exist_ok=True)
WORKBOOK = DATA_DIR / "Goal_Habit_Tracker_2026_2027.xlsx"

app = FastAPI(title="Habit Tracker")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))

HABIT_COLUMNS = [
    "Study (1.5-2h)", "Coding (30-45m)", "Workout ABS + Steps 2k+",
    "Diet 90%", "Water 2.5-3L", "English 15m", "Finance 5m",
    "Screen <2h", "Sleep 6-7h", "Reflection"
]
# The workbook has 11 habit columns including the "Day" helper column after Date.
# We derive the actual habit columns from the sheet so the app stays compatible.
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

def backup_workbook():
    if WORKBOOK.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(WORKBOOK, DATA_DIR / f"Goal_Habit_Tracker_2026_2027_{stamp}.bak")

def load_daily():
    if not WORKBOOK.exists():
        raise FileNotFoundError(f"Workbook not found: {WORKBOOK}")
    df = pd.read_excel(WORKBOOK, sheet_name="Daily Tracker")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df

def clean_num(v):
    if pd.isna(v):
        return None
    try:
        return float(v)
    except Exception:
        return None

def habit_cols(df):
    return [c for c in df.columns if c not in EXCLUDE_DAILY]

def score_row(row, cols):
    vals = [str(row.get(c, "")).strip() for c in cols]
    done = sum(v == "✓" for v in vals)
    total = len(cols)
    return done / total if total else None

def build_stats(start=None, end=None):
    df = load_daily()
    cols = habit_cols(df)
    work = df.dropna(subset=["Date"]).copy()
    if start:
        work = work[work["Date"] >= pd.Timestamp(start)]
    if end:
        work = work[work["Date"] <= pd.Timestamp(end)]

    # Always derive score from the habit marks for reliable dashboard numbers.
    work["score"] = work.apply(lambda r: score_row(r, cols), axis=1)
    completed = work[work["score"].notna()].copy()

    avg = float(completed["score"].mean()) if len(completed) else 0.0
    daily_labels = completed["Date"].dt.strftime("%Y-%m-%d").tolist()
    daily_scores = [round(float(x) * 100, 1) for x in completed["score"]]

    if len(completed):
        completed["week"] = completed["Date"].dt.to_period("W-MON").apply(lambda p: p.start_time)
        weekly = completed.groupby("week")["score"].mean().reset_index()
        weekly_labels = weekly["week"].dt.strftime("%Y-%m-%d").tolist()
        weekly_scores = [round(float(x) * 100, 1) for x in weekly["score"]]
        completed["month"] = completed["Date"].dt.to_period("M").apply(lambda p: p.start_time)
        monthly = completed.groupby("month")["score"].mean().reset_index()
        monthly_labels = monthly["month"].dt.strftime("%Y-%m").tolist()
        monthly_scores = [round(float(x) * 100, 1) for x in monthly["score"]]
    else:
        weekly_labels, weekly_scores, monthly_labels, monthly_scores = [], [], [], []

    habit_avgs = {}
    for c in cols:
        marks = completed[c].astype(str).str.strip()
        valid = marks.isin(["✓", "✗"])
        habit_avgs[c] = round(float((marks[valid] == "✓").mean() * 100), 1) if valid.any() else 0.0

    return {
        "avg": round(avg * 100, 1),
        "days": int(len(completed)),
        "daily": {"labels": daily_labels, "scores": daily_scores},
        "weekly": {"labels": weekly_labels, "scores": weekly_scores},
        "monthly": {"labels": monthly_labels, "scores": monthly_scores},
        "habit_avgs": habit_avgs,
        "habit_columns": cols,
    }

def json_safe(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj

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
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    cols = list(df.columns)
    rows = []
    for _, r in df.iterrows():
        rows.append({c: (None if pd.isna(r[c]) else r[c]) for c in cols})
    return {"columns": cols, "rows": rows, "habit_columns": habit_cols(df)}

@app.post("/api/daily")
def update_daily(payload: DailyUpdate):
    if not WORKBOOK.exists():
        raise HTTPException(404, "Workbook not found")
    try:
        target = pd.Timestamp(payload.date)
    except Exception:
        raise HTTPException(400, "Invalid date")

    backup_workbook()
    wb = load_workbook(WORKBOOK)
    ws = wb["Daily Tracker"]
    headers = {ws.cell(1, c).value: c for c in range(1, ws.max_column + 1)}
    target_row = None
    for r in range(2, ws.max_row + 1):
        cell = ws.cell(r, headers["Date"]).value
        if cell is not None and pd.Timestamp(cell).date() == target.date():
            target_row = r
            break
    if target_row is None:
        target_row = ws.max_row + 1
        ws.cell(target_row, headers["Date"]).value = target.to_pydatetime()
        ws.cell(target_row, headers["Day"]).value = target.strftime("%A")

    for col, val in payload.values.items():
        if col in headers:
            ws.cell(target_row, headers[col]).value = val if val else None

    if "Notes" in headers:
        ws.cell(target_row, headers["Notes"]).value = payload.notes or None

    # Calculate score from the habit marks.
    actual_cols = [c for c in headers if c not in EXCLUDE_DAILY]
    marks = [str(ws.cell(target_row, headers[c]).value or "").strip() for c in actual_cols]
    valid = [m for m in marks if m in ("✓", "✗")]
    score = (valid.count("✓") / len(actual_cols)) if actual_cols else 0
    if "Daily Score %" in headers:
        ws.cell(target_row, headers["Daily Score %"]).value = score

    wb.save(WORKBOOK)
    return {"ok": True, "score": round(score * 100, 1)}

@app.post("/api/clear")
def clear_data(payload: ClearRequest):
    if payload.scope != "daily":
        raise HTTPException(400, "Only daily range clearing is enabled.")
    start, end = pd.Timestamp(payload.start), pd.Timestamp(payload.end)
    backup_workbook()
    wb = load_workbook(WORKBOOK)
    ws = wb["Daily Tracker"]
    headers = {ws.cell(1, c).value: c for c in range(1, ws.max_column + 1)}
    protected = {"Date", "Day"}
    cleared = 0
    for r in range(2, ws.max_row + 1):
        raw = ws.cell(r, headers["Date"]).value
        if raw is None:
            continue
        d = pd.Timestamp(raw)
        if start <= d <= end:
            for name, c in headers.items():
                if name not in protected:
                    ws.cell(r, c).value = None
            cleared += 1
    wb.save(WORKBOOK)
    return {"ok": True, "cleared": cleared}

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
            answer = "Your weakest habit is " + pairs[0][0] + f" ({pairs[0][1]:.1f}%). Your strongest is " + pairs[-1][0] + f" ({pairs[-1][1]:.1f}%)."
        else:
            answer = "No completed habit data is available yet."
    elif "help" in msg:
        answer = "Try: 'What is my average?', 'What is my best day?', 'Which habit is weakest?', or 'Give me a quick summary.'"
    else:
        answer = f"Quick summary: {days} tracked day(s), average score {avg:.1f}%. Ask me about your average, best/worst day, or weakest habit."
    return {"answer": answer}
