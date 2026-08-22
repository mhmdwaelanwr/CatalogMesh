from __future__ import annotations

import csv, os, shutil, sqlite3
try: import fcntl
except ImportError: fcntl=None
try: import msvcrt
except ImportError: msvcrt=None
from datetime import datetime
from pathlib import Path
from typing import Any

VERSION = "3.1.0-rc1"
SCHEMA_VERSION = 2

class OperationLock:
    def __init__(self, output: Path):
        self.path = output / ".product_sorter.lock"; self.handle = None
    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("w")
        self.handle.write("0"); self.handle.flush(); self.handle.seek(0)
        try:
            if fcntl: fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            elif msvcrt: msvcrt.locking(self.handle.fileno(),msvcrt.LK_NBLCK,1)
        except (BlockingIOError,OSError): self.handle.close(); self.handle=None; return False
        self.handle.write(str(os.getpid())); self.handle.flush(); return True
    def release(self) -> None:
        if self.handle:
            if fcntl: fcntl.flock(self.handle, fcntl.LOCK_UN)
            elif msvcrt:
                try: self.handle.seek(0); msvcrt.locking(self.handle.fileno(),msvcrt.LK_UNLCK,1)
                except OSError: pass
            self.handle.close(); self.handle=None

def migrate_database(db: sqlite3.Connection) -> None:
    db.execute("CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    row=db.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
    current=int(row[0]) if row else 0
    if current < 1: ensure_failure_schema(db)
    if current < 2:
        db.execute("""CREATE TABLE IF NOT EXISTS api_usage (
          id INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT, model TEXT,
          input_tokens INTEGER, output_tokens INTEGER, estimated_cost REAL,
          created_at TEXT)""")
    db.execute("INSERT OR REPLACE INTO schema_meta VALUES ('schema_version',?)",(str(SCHEMA_VERSION),)); db.commit()

def record_usage(db:sqlite3.Connection,provider:str,model:str,input_tokens:int=0,output_tokens:int=0)->float:
    in_rate=float(os.getenv(f"{provider.upper()}_INPUT_COST_PER_MILLION","0") or 0)
    out_rate=float(os.getenv(f"{provider.upper()}_OUTPUT_COST_PER_MILLION","0") or 0)
    cost=input_tokens/1_000_000*in_rate+output_tokens/1_000_000*out_rate
    db.execute("INSERT INTO api_usage(provider,model,input_tokens,output_tokens,estimated_cost,created_at) VALUES(?,?,?,?,?,?)",(provider,model,input_tokens,output_tokens,cost,datetime.now().isoformat())); db.commit(); return cost

def export_usage(db:sqlite3.Connection,output:Path)->None:
    rows=db.execute("SELECT provider,model,input_tokens,output_tokens,estimated_cost,created_at FROM api_usage").fetchall()
    with (output/"api_usage.csv").open("w",newline="",encoding="utf-8-sig") as h:
        w=csv.writer(h); w.writerow(["provider","model","input_tokens","output_tokens","estimated_cost","created_at"]); w.writerows(rows)

def backup_progress(db_path: Path) -> Path | None:
    if not db_path.is_file(): return None
    folder = db_path.parent / "backups"; folder.mkdir(exist_ok=True)
    target = folder / f"progress_{datetime.now():%Y%m%d_%H%M%S_%f}.sqlite3"
    shutil.copy2(db_path, target)
    backups = sorted(folder.glob("progress_*.sqlite3"))
    for old in backups[:-10]: old.unlink(missing_ok=True)
    return target

def rotate_log(path: Path, max_bytes: int = 5_000_000) -> None:
    if path.is_file() and path.stat().st_size >= max_bytes:
        path.replace(path.with_suffix(path.suffix + f".{datetime.now():%Y%m%d_%H%M%S}"))

def ensure_failure_schema(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS failures (
      batch_key TEXT PRIMARY KEY, filenames TEXT NOT NULL, error TEXT NOT NULL,
      attempts INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL)"""); db.commit()

def record_failure(db: sqlite3.Connection, key: str, filenames: str, error: str) -> None:
    db.execute("""INSERT INTO failures VALUES (?,?,?,?,?) ON CONFLICT(batch_key) DO UPDATE SET
      error=excluded.error, attempts=failures.attempts+1, updated_at=excluded.updated_at""",
      (key, filenames, error[:2000], 1, datetime.now().isoformat())); db.commit()

def clear_failure(db: sqlite3.Connection, key: str) -> None:
    db.execute("DELETE FROM failures WHERE batch_key=?", (key,)); db.commit()

def export_failures(db: sqlite3.Connection, output: Path) -> None:
    rows=db.execute("SELECT filenames,error,attempts,updated_at FROM failures ORDER BY updated_at").fetchall()
    with (output/"error_report.csv").open("w",newline="",encoding="utf-8-sig") as h:
        w=csv.writer(h); w.writerow(["filenames","error","attempts","updated_at"]); w.writerows(rows)

def estimate_work(photo_count: int, batch_size: int, cost_per_request: float) -> dict[str, Any]:
    step=max(1,batch_size-1); requests=0 if not photo_count else (max(0,photo_count-2)//step)+1
    return {"photos":photo_count,"requests":requests,"estimated_cost":requests*cost_per_request}

def evaluate_report(actual: Path, expected: Path, output: Path) -> float:
    with actual.open(encoding="utf-8-sig") as h: a={r["filename"]:r for r in csv.DictReader(h)}
    with expected.open(encoding="utf-8-sig") as h: e=list(csv.DictReader(h))
    fields=("category","view","brand","model"); total=correct=0
    for row in e:
        got=a.get(row.get("filename",""),{})
        for field in fields:
            if row.get(field): total+=1; correct+=got.get(field,"").casefold()==row[field].casefold()
    score=correct/total if total else 0.0
    (output/"quality_score.txt").write_text(f"accuracy={score:.2%}\nchecked_fields={total}\n",encoding="utf-8")
    return score
