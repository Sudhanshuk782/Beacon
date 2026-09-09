"""
Beacon — Simplifying Overhead
Offline personal engineering secretary.

pip install PySide6 openpyxl

Storage (deliberate):
  LIVE DB -> local C: (%LOCALAPPDATA%\\Beacon)  — never on OneDrive (sync
             corrupts an open SQLite file).
  FILES   -> OneDrive\\Beacon\\Projects when OneDrive exists, else Documents.
"""

import math
import os
import sys
import csv
import shutil
import random
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Roles / capabilities
# ---------------------------------------------------------------------------

ROLES = ["Head", "Program Manager", "Manager",
         "System Engineer", "Developer", "Tester"]

CAPS = {
    "Head":            {"projects", "files", "people", "timeline"},
    "Program Manager": {"projects", "files", "people", "timeline"},
    "Manager":         {"projects", "files", "people", "timeline", "requirements"},
    "System Engineer": {"projects", "files", "requirements"},
    "Developer":       {"projects", "files", "requirements"},
    "Tester":          {"projects", "files", "requirements"},
}
REQ_TYPES  = ["Functional", "Performance", "Safety", "Interface", "Constraint"]
REQ_STATUS = ["Draft", "Reviewed", "Approved", "Implemented", "Verified"]
VERIFY     = ["Test", "Analysis", "Inspection", "Demonstration"]


def caps_for(role):
    return CAPS.get(role, {"projects", "files"})


# ---------------------------------------------------------------------------
# Themes  (placeholder substitution — avoids QSS brace pitfalls)
# ---------------------------------------------------------------------------

# Professional light themes. Hero is a clean, subtle panel (dark text on a soft
# tint), a single refined accent per theme, restrained borders.
THEMES = {
    "Slate": {
        "BG": "#f4f6fb", "PANEL": "#ffffff", "PANEL2": "#eef1f8",
        "ACCENT": "#4263eb", "ACCENT2": "#5c7cfa", "TEXT": "#1a2233",
        "MUTED": "#6b7688", "BORDER": "#e2e7f0",
        "HERO1": "#ffffff", "HERO3": "#f6f8fd", "HERO2": "#eef2fb",
        "HEROTEXT": "#1a2233", "HEROSUB": "#4263eb", "HEROMONO": "#8a93a5",
    },
    "Graphite": {
        "BG": "#f5f6f7", "PANEL": "#ffffff", "PANEL2": "#ecedf0",
        "ACCENT": "#0ca678", "ACCENT2": "#12b886", "TEXT": "#1f2937",
        "MUTED": "#6b7280", "BORDER": "#e3e6e9",
        "HERO1": "#ffffff", "HERO3": "#f5f8f7", "HERO2": "#eef4f2",
        "HEROTEXT": "#1f2937", "HEROSUB": "#0ca678", "HEROMONO": "#8a9199",
    },
    "Navy": {
        "BG": "#f4f6fa", "PANEL": "#ffffff", "PANEL2": "#edf1f7",
        "ACCENT": "#1e3a8a", "ACCENT2": "#2b4bb0", "TEXT": "#16213a",
        "MUTED": "#6b7688", "BORDER": "#e0e6f0",
        "HERO1": "#ffffff", "HERO3": "#f5f8fd", "HERO2": "#edf2fb",
        "HEROTEXT": "#16213a", "HEROSUB": "#1e3a8a", "HEROMONO": "#8791a5",
    },
    "Forest": {
        "BG": "#f4f8f5", "PANEL": "#ffffff", "PANEL2": "#e9f2ec",
        "ACCENT": "#2f855a", "ACCENT2": "#38a169", "TEXT": "#1a2b22",
        "MUTED": "#6b7c72", "BORDER": "#dce9e1",
        "HERO1": "#ffffff", "HERO3": "#f4faf6", "HERO2": "#ecf5ef",
        "HEROTEXT": "#1a2b22", "HEROSUB": "#2f855a", "HEROMONO": "#869488",
    },
}
DEFAULT_THEME = "Slate"
CURRENT = THEMES[DEFAULT_THEME]          # updated by apply_theme

# restrained, professional tones for the project file-tiles
TILE_COLORS = ["#4263eb", "#0ca678", "#2b8ae0", "#6741d9",
               "#0b7285", "#3b5bdb", "#37795a", "#5f6b7a"]

# vibrant "positive" gradients for the greeting banner
HERO_PALETTES = [
    ["#ff6b6b", "#ee5a67", "#c44fb0"],   ["#f7797d", "#fbd786", "#c471f5"],
    ["#43cea2", "#2fa4c9", "#185a9d"],   ["#11998e", "#38ef7d"],
    ["#4facfe", "#3a7bff", "#7b5cff"],   ["#f857a6", "#ff5858"],
    ["#8e2de2", "#c471ed", "#f64f8b"],   ["#00b4db", "#0083b0"],
    ["#f7971e", "#ff705b", "#ff4e8b"],   ["#2193b0", "#37cfa0", "#6dd5ed"],
    ["#654ea3", "#7b5cff", "#eaafc8"],   ["#ff8008", "#ff5f6d", "#d64b9c"],
    ["#396afc", "#2948ff"],              ["#c33764", "#1d2671"],
    ["#3a1c71", "#d76d77", "#ffaf7b"],   ["#00c6ff", "#0072ff"],
    ["#fc5c7d", "#6a82fb"],              ["#1fa2ff", "#12d8fa", "#a6ffcb"],
    ["#f00000", "#dc281e"],              ["#7f00ff", "#e100ff"],
    ["#ff512f", "#dd2476"],              ["#11998e", "#43cea2", "#185a9d"],
    ["#f953c6", "#b91d73"],              ["#00f260", "#0575e6"],
]
# texture styles cycle across palettes -> 24 visually distinct hero designs (Req1)
HERO_TEXTURES = ["blobs", "rings", "stripes", "dots", "waves", "grid"]
HERO_DESIGNS = [{"palette": p, "texture": HERO_TEXTURES[i % len(HERO_TEXTURES)]}
                for i, p in enumerate(HERO_PALETTES)]

CURRENT_DESIGN = HERO_DESIGNS[0]         # set per launch / per 6-hour block
CURRENT_HERO = HERO_DESIGNS[0]["palette"]  # kept for compatibility
CURRENT_PUNCH = ""                       # active positive punchline
LAUNCH_UI_INDEX = 0                      # rotation index chosen at launch


def time_block(now=None):
    """0..3 for the 6-hour clock blocks 00/06/12/18."""
    now = now or datetime.now()
    return now.hour // 6


def hero_mode(now=None):
    """Sunrise 06:00–11:00, moon 23:00–04:00, otherwise the rotating design."""
    now = now or datetime.now()
    mins = now.hour * 60 + now.minute
    if 6 * 60 <= mins < 11 * 60:
        return "sunrise"
    if mins >= 23 * 60 or mins < 4 * 60:
        return "moon"
    return "design"


def apply_ui_rotation(index, now=None):
    """Select the active hero design + punchline for a rotation index."""
    global CURRENT_DESIGN, CURRENT_HERO, CURRENT_PUNCH
    CURRENT_DESIGN = HERO_DESIGNS[index % len(HERO_DESIGNS)]
    CURRENT_HERO = CURRENT_DESIGN["palette"]
    CURRENT_PUNCH = GREETING_LINES[index % len(GREETING_LINES)]

_QSS = """
* { font-family: 'Segoe UI', 'Consolas', sans-serif; color: __TEXT__; font-size: 13px; }
QMainWindow { background: __BG__; }
QDialog, QMessageBox, QInputDialog, QColorDialog { background: __BG__; }

#TopBar { background: __PANEL__; border-bottom: 1px solid __BORDER__; }
#Brand  { color: __ACCENT__; font-size: 16px; font-weight: 800; letter-spacing: 2px; }
QPushButton#navlink { background: transparent; border: none; color: __MUTED__;
    padding: 8px 14px; font-size: 13px; }
QPushButton#navlink:hover   { color: __TEXT__; }
QPushButton#navlink:checked { color: __ACCENT__; font-weight: 700; }
QPushButton#gear { background: __ACCENT__; color: #ffffff; border: none;
    border-radius: 10px; padding: 8px 16px; font-weight: 700; }
QPushButton#gear:hover { background: __ACCENT2__; }

#Mono   { color: #ffffff; font-size: 12px; letter-spacing: 1px; background: transparent; }
#Salute { color: #ffffff; font-size: 38px; font-weight: 800; background: transparent; }
#Line   { color: #f3f6ff; font-size: 16px; font-weight: 500; background: transparent; }
#Day    { color: #f3f6ff; font-size: 13px; background: transparent; }

#SectionH { color: __TEXT__; font-size: 15px; font-weight: 800; letter-spacing: 1px; }
#Card { background: __PANEL__; border: 1px solid __BORDER__; border-radius: 12px; }
#CardTitle { color: __ACCENT__; font-size: 12px; font-weight: 800; letter-spacing: 1px; }
#ProjCanvas { background: __PANEL2__; border: 1px solid __BORDER__; border-radius: 10px; }
#FmtBar { background: __PANEL2__; border: 1px solid __BORDER__; border-radius: 8px; }
#FmtLabel { color: __MUTED__; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
#FmtSep { color: __BORDER__; }
QToolButton#fmtbtn { background: __PANEL__; border: 1px solid __BORDER__; border-radius: 6px;
    color: __TEXT__; font-weight: 700; }
QToolButton#fmtbtn:hover { background: __ACCENT__; color: #ffffff; border-color: __ACCENT__; }
QPushButton#modebtn { background: __PANEL__; border: 1px solid __BORDER__; border-radius: 8px;
    padding: 7px 14px; color: __MUTED__; font-weight: 600; }
QPushButton#modebtn:hover { border-color: __ACCENT__; color: __TEXT__; }
QPushButton#modebtn:checked { background: __ACCENT__; color: #ffffff; border-color: __ACCENT__; }
#RecentCanvas { background: #ebedf1; border: 1px solid __BORDER__; border-radius: 10px; }
#Muted { color: __MUTED__; }
#H1 { color: __TEXT__; font-size: 22px; font-weight: 800; }

QPushButton { background: __PANEL__; border: 1px solid __BORDER__; border-radius: 8px;
    padding: 8px 14px; color: __TEXT__; }
QPushButton:hover { border-color: __ACCENT__; }
QPushButton#primary { background: __ACCENT__; color: #ffffff; border: none; font-weight: 700; }
QPushButton#primary:hover { background: __ACCENT2__; }

QLineEdit, QComboBox, QDateEdit, QPlainTextEdit, QTextEdit {
    background: __PANEL2__; border: 1px solid __BORDER__; border-radius: 8px;
    padding: 8px; color: __TEXT__; }
QComboBox QAbstractItemView { background: __PANEL__; color: __TEXT__;
    selection-background-color: __ACCENT__; }
QMenu { background: __PANEL__; color: __TEXT__; border: 1px solid __BORDER__; }
QMenu::item:selected { background: __ACCENT__; color: #ffffff; }

QTabWidget::pane { border: 1px solid __BORDER__; border-radius: 10px; background: __PANEL__; }
QTabBar::tab { background: __PANEL2__; color: __MUTED__; padding: 8px 16px; margin-right: 2px;
    border-top-left-radius: 8px; border-top-right-radius: 8px; }
QTabBar::tab:selected { background: __ACCENT__; color: #ffffff; font-weight: 700; }

QHeaderView::section { background: __PANEL2__; color: __TEXT__; padding: 7px; border: none;
    border-right: 1px solid __BORDER__; font-weight: 600; }
QTableWidget, QListWidget { background: __PANEL__; border: 1px solid __BORDER__;
    border-radius: 10px; gridline-color: __BORDER__; color: __TEXT__; }
QTableWidget::item:selected, QTableView::item:selected,
QListWidget::item:selected { background: __ACCENT__; color: #ffffff; }
QListWidget::item { border-radius: 8px; }
QListWidget::item:hover { background: __PANEL2__; color: __TEXT__; }
QTableWidget::item:hover { color: __TEXT__; }
QTreeWidget::item:hover { color: __TEXT__; }
QListWidget::item:selected:!active { background: __ACCENT__; color: #ffffff; }
QListWidget::item:focus { outline: none; }
QAbstractItemView { selection-background-color: __ACCENT__; selection-color: #ffffff;
    outline: 0; }
QTreeWidget, QTreeView { background: __PANEL__; border: 1px solid __BORDER__;
    border-radius: 10px; color: __TEXT__; }
QTreeWidget::item, QTreeView::item { padding: 4px 2px; color: __TEXT__; }
QTreeWidget::item:selected, QTreeView::item:selected { background: __ACCENT__; color: #ffffff; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: __BORDER__; border-radius: 5px; }
QStatusBar { background: __PANEL2__; color: __MUTED__; }
"""


def make_qss(theme_name):
    c = THEMES[theme_name]
    s = _QSS
    for k, v in c.items():
        s = s.replace(f"__{k}__", v)
    return s


def apply_theme(app, theme_name):
    global CURRENT
    CURRENT = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    app.setStyleSheet(make_qss(theme_name if theme_name in THEMES else DEFAULT_THEME))


# ---------------------------------------------------------------------------
# Data locations
# ---------------------------------------------------------------------------

def live_data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = Path(base) / "Beacon"; d.mkdir(parents=True, exist_ok=True); return d


def onedrive_dir():
    for var in ("OneDriveCommercial", "OneDrive", "OneDriveConsumer"):
        val = os.environ.get(var)
        if val and Path(val).exists():
            return Path(val)
    return None


PROJECT_ROOT = None   # set at launch from the 'files_root' setting (Req: user-chosen)


def default_root():
    od = onedrive_dir()
    return (od / "Beacon") if od else (Path(os.path.expanduser("~")) / "Documents" / "Beacon")


def set_project_root(path):
    global PROJECT_ROOT
    PROJECT_ROOT = str(path) if path else None


def files_root():
    root = Path(PROJECT_ROOT) if PROJECT_ROOT else default_root()
    (root / "Projects").mkdir(parents=True, exist_ok=True)
    (root / "Backups").mkdir(parents=True, exist_ok=True)
    return root


def desktop_dir():
    d = Path(os.path.expanduser("~")) / "Desktop"
    return d if d.exists() else None


def documents_dir():
    d = Path(os.path.expanduser("~")) / "Documents"
    return d if d.exists() else None


def db_path():
    return live_data_dir() / "beacon.db"


def safe_name(name):
    keep = "".join(c for c in name if c not in '\\/:*?"<>|').strip()
    return keep or "Untitled"


def open_in_explorer(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))           # noqa: Windows only
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        print("open_in_explorer failed:", e)


USER_FOLDER = "User"          # the user's own folder structure lives here
PROJECT_SUBFOLDERS = [USER_FOLDER, "Requirements", "Design", "Tests", "Reports", "Material"]

# --- file organisation by format (Req: same format -> same subfolder) --------
FILE_CATEGORIES = {
    "pdf": "PDF",
    "doc": "Word", "docx": "Word", "rtf": "Word", "odt": "Word",
    "xls": "Excel", "xlsx": "Excel", "xlsm": "Excel", "csv": "Excel",
    "ppt": "PowerPoint", "pptx": "PowerPoint",
    "png": "Images", "jpg": "Images", "jpeg": "Images", "gif": "Images",
    "bmp": "Images", "svg": "Images", "webp": "Images", "tif": "Images", "tiff": "Images",
    "slx": "Simulink", "mdl": "Simulink",
    "m": "MATLAB", "mat": "MATLAB", "mlx": "MATLAB",
    "c": "Code", "h": "Code", "cpp": "Code", "cc": "Code", "hpp": "Code",
    "py": "Code", "pyw": "Code", "ino": "Code", "exe": "Code", "hex": "Code",
    "bin": "Code", "js": "Code", "java": "Code",
    "txt": "Text", "md": "Text", "log": "Text", "html": "Text", "htm": "Text",
    "xml": "Text", "json": "Text", "yaml": "Text", "yml": "Text",
    "zip": "Archives", "rar": "Archives", "7z": "Archives", "tar": "Archives", "gz": "Archives",
}
# the 10 common categories, in order; everything else -> Miscellaneous
CATEGORY_ORDER = ["PDF", "Word", "Excel", "PowerPoint", "Images",
                  "Simulink", "MATLAB", "Code", "Text", "Archives"]
MISC = "Miscellaneous"
CATEGORY_LIST = CATEGORY_ORDER + [MISC]
MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"]


def fmt_date(dt):
    """DD-Sept-YYYY (used everywhere in Beacon)."""
    return f"{dt.day:02d}-{MONTH_ABBR[dt.month - 1]}-{dt.year}"


def fmt_dt(dt):
    return f"{fmt_date(dt)} {dt.strftime('%H:%M')}"


def categorize(src) -> str:
    ext = Path(src).suffix.lower().lstrip(".")
    return FILE_CATEGORIES.get(ext, MISC)


def downloads_dir() -> Path:
    d = Path(os.path.expanduser("~")) / "Downloads"
    return d if d.exists() else Path(os.path.expanduser("~"))


def import_file(project_root, src, move=False):
    """Place src into <project>/<Category>/ (created on demand). Returns (dir, dest)."""
    cat = categorize(src)
    dest_dir = Path(project_root) / cat
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / Path(src).name
    base = dest; i = 2
    while dest.exists():
        dest = base.with_name(f"{base.stem}_{i}{base.suffix}"); i += 1
    if move:
        shutil.move(str(src), str(dest))
    else:
        shutil.copy2(src, dest)
    return dest_dir, dest


def monogram(name):
    """A short symbol for a project — its initials."""
    words = [w for w in name.split() if w]
    if len(words) >= 2:
        s = words[0][0] + words[1][0]
    elif words:
        s = words[0][:2]
    else:
        s = "?"
    return s.upper()


# folders Beacon can watch for new downloads (Req1)
WATCH_DEFS = [
    ("watch_downloads", "Downloads", downloads_dir, "1"),
    ("watch_desktop",   "Desktop",   desktop_dir,   "0"),
    ("watch_documents", "Documents", documents_dir, "0"),
    ("watch_onedrive",  "OneDrive",  onedrive_dir,  "0"),
]
TEMP_DOWNLOAD_EXT = {".crdownload", ".part", ".partial", ".tmp", ".download", ".opdownload"}


def watched_folders(conn):
    out, seen = [], set()
    for key, _label, getter, default in WATCH_DEFS:
        if get_setting(conn, key, default) == "1":
            f = getter()
            if f and f.exists() and str(f) not in seen:
                seen.add(str(f)); out.append(f)
    return out


def human_size(n):
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def init_db():
    conn = sqlite3.connect(db_path())
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY CHECK (id=1),
            name TEXT NOT NULL, role TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, path TEXT NOT NULL,
            status TEXT DEFAULT 'Active', owner TEXT, start_date TEXT, end_date TEXT,
            created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS project_people (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
            name TEXT NOT NULL, role TEXT, added_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
            title TEXT NOT NULL, due_date TEXT, done INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS requirements (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
            req_key TEXT NOT NULL, title TEXT NOT NULL, description TEXT, rtype TEXT,
            status TEXT, verification TEXT, assignee TEXT, parent_key TEXT,
            created_at TEXT NOT NULL, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS notes (
            entry_date TEXT PRIMARY KEY, body TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT, plan_date TEXT NOT NULL,
            text TEXT NOT NULL, done INTEGER DEFAULT 0, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS recent_opens (
            id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, opened_at TEXT);
        CREATE TABLE IF NOT EXISTS note (
            id INTEGER PRIMARY KEY AUTOINCREMENT, note_date TEXT NOT NULL,
            purpose TEXT, place TEXT, body_html TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT, purpose TEXT, url TEXT,
            position INTEGER, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS manager_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
            manager TEXT NOT NULL, workbook TEXT, sheet TEXT,
            weight REAL DEFAULT 0, position INTEGER, created_at TEXT);
        CREATE TABLE IF NOT EXISTS apps (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            target TEXT NOT NULL, kind TEXT DEFAULT 'path',
            position INTEGER, created_at TEXT);
        CREATE TABLE IF NOT EXISTS shots (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tag TEXT NOT NULL,
            path TEXT NOT NULL, note TEXT, project_id INTEGER,
            created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS pending_downloads (
            path TEXT PRIMARY KEY, seen_at TEXT, dismissed INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS relax_play (
            play_date TEXT PRIMARY KEY, seconds INTEGER DEFAULT 0, best_level INTEGER DEFAULT 0);
        """
    )
    for col, ddl in [("owner", "TEXT"), ("start_date", "TEXT"), ("end_date", "TEXT"),
                     ("code", "TEXT"), ("position", "INTEGER"),
                     ("held", "INTEGER"), ("closed", "INTEGER")]:
        if col not in _columns(conn, "projects"):
            conn.execute(f"ALTER TABLE projects ADD COLUMN {col} {ddl}")
    conn.execute("UPDATE projects SET position=id WHERE position IS NULL")
    conn.execute("UPDATE projects SET held=0 WHERE held IS NULL")
    conn.execute("UPDATE projects SET closed=0 WHERE closed IS NULL")
    for col, ddl in [("remind_time", "TEXT"), ("reminded", "INTEGER")]:
        if col not in _columns(conn, "plan"):
            conn.execute(f"ALTER TABLE plan ADD COLUMN {col} {ddl}")
    conn.commit()
    ensure_unique_codes(conn)
    return conn


def get_setting(conn, key, default=None):
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r else default


def set_setting(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, value))
    conn.commit()


def get_profile(conn):
    r = conn.execute("SELECT name, role, created_at FROM profile WHERE id=1").fetchone()
    return {"name": r[0], "role": r[1], "created_at": r[2]} if r else None


def save_profile(conn, name, role):
    conn.execute("INSERT OR REPLACE INTO profile (id,name,role,created_at) VALUES (1,?,?,?)",
                 (name.strip(), role, datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def clear_profile(conn):
    conn.execute("DELETE FROM profile"); conn.commit()


def suggest_code(name):
    alnum = [c for c in name.upper() if c.isalnum()]
    return "".join(alnum[:3]).ljust(3, "X") if alnum else "PRJ"


def code_exists(conn, code):
    return conn.execute("SELECT 1 FROM projects WHERE UPPER(code)=UPPER(?)", (code,)).fetchone() is not None


def _make_unique_code(code, used):
    import string
    alnum = string.ascii_uppercase + string.digits
    code = (code or "PRJ").upper()[:3].ljust(3, "X")
    if code not in used:
        return code
    for ch in alnum:                      # vary last char
        cand = code[:2] + ch
        if cand not in used:
            return cand
    for a in alnum:                       # exhaustive fallback
        for b_ in alnum:
            for c_ in alnum:
                cand = a + b_ + c_
                if cand not in used:
                    return cand
    return code


def ensure_unique_codes(conn):
    """Give every project a non-empty, globally-unique 3-char code (Req: no dupes)."""
    used = set()
    rows = conn.execute("SELECT id,name,code FROM projects "
                        "ORDER BY position IS NULL, position, id").fetchall()
    for pid, name, code in rows:
        c = (code or "").strip().upper() or suggest_code(name)
        c = _make_unique_code(c, used)
        used.add(c)
        if c != (code or "").strip().upper():
            conn.execute("UPDATE projects SET code=? WHERE id=?", (c, pid))
    conn.commit()


def create_project(conn, name, code, owner):
    folder = files_root() / "Projects" / safe_name(name)
    base = folder; i = 2
    while folder.exists():
        folder = base.with_name(base.name + f"_{i}"); i += 1
    for sub in PROJECT_SUBFOLDERS:
        (folder / sub).mkdir(parents=True, exist_ok=True)
    existing = {(r[0] or "").upper() for r in conn.execute("SELECT code FROM projects") if r[0]}
    code = (code or "").strip().upper() or suggest_code(name)
    code = _make_unique_code(code, existing)
    pos = (conn.execute("SELECT COALESCE(MAX(position),0) FROM projects").fetchone()[0] or 0) + 1
    cur = conn.execute(
        "INSERT INTO projects (name,path,owner,code,position,created_at) VALUES (?,?,?,?,?,?)",
        (name.strip(), str(folder), owner, code, pos,
         datetime.now().isoformat(timespec="seconds")))
    conn.commit(); return cur.lastrowid


def list_projects(conn):
    return conn.execute(
        "SELECT id,name,path,status,owner,start_date,end_date,code,held "
        "FROM projects WHERE COALESCE(closed,0)=0 ORDER BY position IS NULL, position, id").fetchall()


def list_closed_projects(conn):
    return conn.execute(
        "SELECT id,name,path FROM projects WHERE COALESCE(closed,0)=1 ORDER BY name").fetchall()


def set_project_held(conn, pid, held):
    conn.execute("UPDATE projects SET held=? WHERE id=?", (1 if held else 0, pid)); conn.commit()


def set_project_closed(conn, pid, closed):
    conn.execute("UPDATE projects SET closed=? WHERE id=?", (1 if closed else 0, pid)); conn.commit()


def delete_project(conn, pid):
    row = conn.execute("SELECT path FROM projects WHERE id=?", (pid,)).fetchone()
    if row and row[0]:
        path = Path(row[0])
        # safety: only remove folders that live under Beacon's Projects root
        try:
            if path.exists() and str(path).startswith(str(files_root() / "Projects")):
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass
    for tbl in ("requirements", "project_people", "milestones"):
        conn.execute(f"DELETE FROM {tbl} WHERE project_id=?", (pid,))
    conn.execute("DELETE FROM projects WHERE id=?", (pid,))
    conn.commit()


def set_project_order(conn, ordered_ids):
    for pos, pid in enumerate(ordered_ids, start=1):
        conn.execute("UPDATE projects SET position=? WHERE id=?", (pos, pid))
    conn.commit()


def project_code(row):
    """Display code for a project row (from list_projects): stored code or a fallback."""
    code = row[7] if len(row) > 7 else None
    return (code or suggest_code(row[1])).upper()[:3]


def get_note(conn, date):
    r = conn.execute("SELECT body FROM notes WHERE entry_date=?", (date,)).fetchone()
    return r[0] if r else ""


def save_note(conn, date, body):
    if body.strip():
        conn.execute("INSERT OR REPLACE INTO notes (entry_date,body,updated_at) VALUES (?,?,?)",
                     (date, body, datetime.now().isoformat(timespec="seconds")))
    else:
        conn.execute("DELETE FROM notes WHERE entry_date=?", (date,))
    conn.commit()


def list_note_dates(conn):
    return [r[0] for r in conn.execute(
        "SELECT entry_date FROM notes ORDER BY entry_date DESC").fetchall()]


# ---- rich notes (multiple per date, with purpose/place/HTML) ----
def add_note(conn, date, purpose, place, body_html):
    now = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO note (note_date,purpose,place,body_html,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?)", (date, purpose, place, body_html, now, now))
    conn.commit(); return cur.lastrowid


def update_note(conn, note_id, purpose, place, body_html):
    conn.execute("UPDATE note SET purpose=?,place=?,body_html=?,updated_at=? WHERE id=?",
                 (purpose, place, body_html, datetime.now().isoformat(timespec="seconds"), note_id))
    conn.commit()


def get_note_row(conn, note_id):
    return conn.execute("SELECT id,note_date,purpose,place,body_html FROM note WHERE id=?",
                        (note_id,)).fetchone()


def note_dates(conn):
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT note_date FROM note ORDER BY note_date DESC").fetchall()]


def notes_for_date(conn, date):
    return conn.execute("SELECT id, purpose FROM note WHERE note_date=? ORDER BY id",
                        (date,)).fetchall()


def delete_note(conn, note_id):
    conn.execute("DELETE FROM note WHERE id=?", (note_id,)); conn.commit()


# ---- plan (today's tasks) with reminders ----
def list_plan(conn, date):
    return conn.execute(
        "SELECT id, text, done, remind_time FROM plan WHERE plan_date=? ORDER BY done, id",
        (date,)).fetchall()


def add_plan(conn, date, text):
    cur = conn.execute("INSERT INTO plan (plan_date,text,done,created_at) VALUES (?,?,0,?)",
                       (date, text.strip(), datetime.now().isoformat(timespec="seconds")))
    conn.commit(); return cur.lastrowid


def update_plan_text(conn, plan_id, text):
    conn.execute("UPDATE plan SET text=? WHERE id=?", (text.strip(), plan_id)); conn.commit()


def set_plan_done(conn, plan_id, done):
    conn.execute("UPDATE plan SET done=? WHERE id=?", (1 if done else 0, plan_id)); conn.commit()


def set_plan_reminder(conn, plan_id, hhmm):
    conn.execute("UPDATE plan SET remind_time=?, reminded=0 WHERE id=?", (hhmm, plan_id)); conn.commit()


def delete_plan(conn, plan_id):
    conn.execute("DELETE FROM plan WHERE id=?", (plan_id,)); conn.commit()


def due_plan_reminders(conn, date, now_hhmm):
    return conn.execute(
        "SELECT id, text, remind_time FROM plan WHERE plan_date=? AND remind_time IS NOT NULL "
        "AND remind_time<>'' AND COALESCE(reminded,0)=0 AND remind_time<=?",
        (date, now_hhmm)).fetchall()


def mark_plan_reminded(conn, plan_id):
    conn.execute("UPDATE plan SET reminded=1 WHERE id=?", (plan_id,)); conn.commit()


def clear_done_plan(conn, date):
    conn.execute("DELETE FROM plan WHERE plan_date=? AND done=1", (date,)); conn.commit()


# ---- recently opened files ----
def record_open(conn, path):
    conn.execute("INSERT INTO recent_opens (path, opened_at) VALUES (?,?)",
                 (str(path), datetime.now().isoformat(timespec="seconds")))
    # keep the log from growing unbounded
    conn.execute("DELETE FROM recent_opens WHERE id NOT IN "
                 "(SELECT id FROM recent_opens ORDER BY id DESC LIMIT 200)")
    conn.commit()


def list_recent_opens(conn, limit=10):
    rows = conn.execute("SELECT path, opened_at FROM recent_opens ORDER BY id DESC").fetchall()
    seen, out = set(), []
    for path, _ts in rows:                       # dedupe, keep most recent open of each file
        if path in seen:
            continue
        seen.add(path); out.append(Path(path))
        if len(out) >= limit:
            break
    return out


def recent_files(limit=12):
    root = files_root() / "Projects"
    items = []
    if root.exists():
        for f in root.rglob("*"):
            if f.is_file():
                try:
                    items.append((f, f.stat().st_mtime))
                except OSError:
                    pass
    items.sort(key=lambda x: x[1], reverse=True)
    return [f for f, _ in items[:limit]]


def list_links(conn):
    return conn.execute("SELECT id, purpose, url FROM links "
                        "ORDER BY position IS NULL, position, id").fetchall()


def add_link(conn, purpose, url):
    pos = (conn.execute("SELECT COALESCE(MAX(position),0) FROM links").fetchone()[0] or 0) + 1
    conn.execute("INSERT INTO links (purpose,url,position,created_at) VALUES (?,?,?,?)",
                 (purpose.strip(), url.strip(), pos, datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def delete_link(conn, link_id):
    conn.execute("DELETE FROM links WHERE id=?", (link_id,)); conn.commit()


# ---- Head <-> Manager workbook links ----
def list_manager_links(conn, project_id):
    return conn.execute(
        "SELECT id, manager, workbook, sheet, weight FROM manager_links "
        "WHERE project_id=? ORDER BY position IS NULL, position, id", (project_id,)).fetchall()


def set_managers(conn, project_id, managers):
    """Replace the manager list for a project, keeping any existing links/weights."""
    existing = {m.strip().lower(): (w, s, wt)
                for _i, m, w, s, wt in list_manager_links(conn, project_id)}
    conn.execute("DELETE FROM manager_links WHERE project_id=?", (project_id,))
    share = round(1.0 / max(len(managers), 1), 4)
    for pos, mgr in enumerate(managers, start=1):
        prev = existing.get(mgr.strip().lower())
        wbk, sheet, weight = prev if prev else (None, None, share)
        conn.execute(
            "INSERT INTO manager_links (project_id,manager,workbook,sheet,weight,position,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (project_id, mgr.strip(), wbk, sheet, weight, pos,
             datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def set_manager_link(conn, link_id, workbook, sheet):
    conn.execute("UPDATE manager_links SET workbook=?, sheet=? WHERE id=?",
                 (str(workbook), sheet, link_id)); conn.commit()


def set_manager_weight(conn, link_id, weight):
    conn.execute("UPDATE manager_links SET weight=? WHERE id=?", (float(weight), link_id))
    conn.commit()


# ---- Applications (launch installed apps) ----
# kind: 'uri' (protocol/shell command) or 'path' (executable on disk)
DEFAULT_APPS = [
    ("Calculator", "calc.exe", "path"),
    ("Outlook", "outlook.exe", "path"),
    ("Teams", "msteams:", "uri"),
]

# Common install locations searched when detecting apps (Windows).
APP_HINTS = {
    "Outlook": [r"C:\Program Files\Microsoft Office\root\Office16\OUTLOOK.EXE",
                r"C:\Program Files (x86)\Microsoft Office\root\Office16\OUTLOOK.EXE"],
    "Excel": [r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
              r"C:\Program Files (x86)\Microsoft Office\root\Office16\EXCEL.EXE"],
    "Word": [r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
             r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE"],
    "VS Code": [r"C:\Program Files\Microsoft VS Code\Code.exe"],
    "Notepad": [r"C:\Windows\System32\notepad.exe"],
    "Paint": [r"C:\Windows\System32\mspaint.exe"],
    "Snipping Tool": [r"C:\Windows\System32\SnippingTool.exe"],
}


def detect_apps():
    """Return [(name, target, kind)] for apps found on this machine."""
    found = []
    for name, paths in APP_HINTS.items():
        for pth in paths:
            p = Path(os.path.expandvars(pth))
            if p.exists():
                found.append((name, str(p), "path")); break
    # user-local installs
    local = os.environ.get("LOCALAPPDATA")
    if local:
        for name, rel in [("VS Code", r"Programs\Microsoft VS Code\Code.exe"),
                          ("Teams", r"Microsoft\Teams\current\Teams.exe")]:
            p = Path(local) / rel
            if p.exists() and not any(n == name for n, _t, _k in found):
                found.append((name, str(p), "path"))
    return found


# Windows Store / built-in apps have no .exe to browse to — launch them by URI
# or by their shell command. These are offered by name in the picker.
KNOWN_URI_APPS = [
    ("Calculator", "calc.exe", "path"),
    ("Camera", "microsoft.windows.camera:", "uri"),
    ("Snipping Tool", "ms-screensketch:", "uri"),
    ("Photos", "ms-photos:", "uri"),
    ("Settings", "ms-settings:", "uri"),
    ("Teams", "msteams:", "uri"),
    ("Notepad", "notepad.exe", "path"),
    ("Paint", "mspaint.exe", "path"),
    ("WordPad", "write.exe", "path"),
    ("Command Prompt", "cmd.exe", "path"),
    ("File Explorer", "explorer.exe", "path"),
]


def start_menu_apps():
    """Every shortcut in the Start Menu — this is where installed apps really live."""
    out = []
    roots = []
    for base in (os.environ.get("ProgramData"), os.environ.get("APPDATA")):
        if base:
            p = Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            if p.exists():
                roots.append(p)
    for root in roots:
        try:
            for lnk in root.rglob("*.lnk"):
                out.append((lnk.stem, str(lnk), "path"))
        except OSError:
            continue
    seen, uniq = set(), []
    for name, target, kind in sorted(out, key=lambda x: x[0].lower()):
        key = name.lower()
        if key not in seen and not _is_noise(name):
            seen.add(key); uniq.append((name, target, kind))
    return uniq


def registry_installed_apps():
    """Read Windows' installed-programs registry — the same source Settings ▸ Apps ▸
    Installed apps uses. Returns [(name, target, kind)] where target may be an exe."""
    out = []
    if not sys.platform.startswith("win"):
        return out
    try:
        import winreg
    except ImportError:
        return out
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", 0),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", 0),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", 0),
    ]
    seen = set()
    for hive, subkey, flags in roots:
        try:
            key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ | flags)
        except OSError:
            continue
        try:
            count = winreg.QueryInfoKey(key)[0]
            for i in range(count):
                try:
                    name_k = winreg.EnumKey(key, i)
                    sub = winreg.OpenKey(key, name_k)
                except OSError:
                    continue
                try:
                    def val(n):
                        try:
                            return winreg.QueryValueEx(sub, n)[0]
                        except OSError:
                            return None
                    disp = val("DisplayName")
                    if not disp or val("SystemComponent") == 1:
                        continue
                    if val("ParentKeyName") or val("ReleaseType") in ("Update", "Hotfix", "Security Update"):
                        continue
                    key_l = str(disp).strip().lower()
                    if key_l in seen:
                        continue
                    seen.add(key_l)
                    target = None
                    icon = val("DisplayIcon")
                    if icon:
                        cand = str(icon).split(",")[0].strip().strip('"')
                        if cand.lower().endswith(".exe") and Path(cand).exists():
                            target = cand
                    if not target:
                        loc = val("InstallLocation")
                        if loc and Path(loc).exists():
                            try:
                                exes = sorted(Path(loc).glob("*.exe"))
                                if exes:
                                    target = str(exes[0])
                            except OSError:
                                pass
                    if target:
                        out.append((str(disp).strip(), target, "path"))
                finally:
                    sub.Close()
        finally:
            key.Close()
    return out


def store_apps():
    """UWP / Store apps (Calculator, Photos…) via their AppsFolder shell IDs."""
    if not sys.platform.startswith("win"):
        return []
    out = []
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"SOFTWARE\Classes\ActivatableClasses\Package")
        try:
            for i in range(winreg.QueryInfoKey(key)[0]):
                pkg = winreg.EnumKey(key, i)
                friendly = pkg.split("_")[0].replace("Microsoft.", "").replace("Windows", "").strip()
                if friendly:
                    out.append((friendly, f"shell:AppsFolder\\{pkg}", "uri"))
        finally:
            key.Close()
    except OSError:
        pass
    return out


def _is_noise(name):
    n = name.lower()
    return any(k in n for k in ("uninstall", "readme", "read me", "help", "documentation",
                                "release notes", "license", "eula", "website", "web site",
                                "support", "manual", "changelog"))


def available_apps():
    """Everything the user could add, best sources first:
    Windows 'Installed apps' registry, Start Menu shortcuts, then known built-ins."""
    apps = []
    seen = set()

    def push(items):
        for name, target, kind in items:
            key = name.strip().lower()
            if not name.strip() or key in seen or _is_noise(name):
                continue
            seen.add(key); apps.append((name.strip(), target, kind))

    push(registry_installed_apps())
    push(start_menu_apps())
    push(KNOWN_URI_APPS)
    return sorted(apps, key=lambda x: x[0].lower())


def seed_default_apps(conn):
    if conn.execute("SELECT COUNT(*) FROM apps").fetchone()[0]:
        return
    for pos, (name, target, kind) in enumerate(DEFAULT_APPS, start=1):
        conn.execute("INSERT INTO apps (name,target,kind,position,created_at) VALUES (?,?,?,?,?)",
                     (name, target, kind, pos, datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def list_apps(conn):
    return conn.execute("SELECT id,name,target,kind FROM apps "
                        "ORDER BY position IS NULL, position, id").fetchall()


def add_app(conn, name, target, kind="path"):
    pos = (conn.execute("SELECT COALESCE(MAX(position),0) FROM apps").fetchone()[0] or 0) + 1
    conn.execute("INSERT INTO apps (name,target,kind,position,created_at) VALUES (?,?,?,?,?)",
                 (name.strip(), str(target).strip(), kind, pos,
                  datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def delete_app(conn, app_id):
    conn.execute("DELETE FROM apps WHERE id=?", (app_id,)); conn.commit()


def launch_app(target, kind="path"):
    """Launch an application. Returns (ok, message)."""
    try:
        if kind == "uri":
            if sys.platform.startswith("win"):
                os.startfile(target)                      # noqa: Windows only
            else:
                subprocess.Popen(["xdg-open", target])
            return True, ""
        p = Path(target)
        if p.exists():
            if sys.platform.startswith("win"):
                os.startfile(str(p))                      # noqa: Windows only
            else:
                subprocess.Popen([str(p)])
            return True, ""
        # not a full path -> let the OS resolve it from PATH / App Paths
        subprocess.Popen(target, shell=True)
        return True, ""
    except Exception as e:
        return False, str(e)


# ---- Screenshots (tagged images) ----
def shots_dir():
    d = files_root() / "Screenshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_shots(conn, query=""):
    q = f"%{query.strip().lower()}%"
    if query.strip():
        return conn.execute(
            "SELECT id,tag,path,note,created_at FROM shots "
            "WHERE LOWER(tag) LIKE ? OR LOWER(COALESCE(note,'')) LIKE ? "
            "ORDER BY id DESC", (q, q)).fetchall()
    return conn.execute("SELECT id,tag,path,note,created_at FROM shots "
                        "ORDER BY id DESC").fetchall()


def add_shot(conn, tag, path, note=""):
    conn.execute("INSERT INTO shots (tag,path,note,created_at) VALUES (?,?,?,?)",
                 (tag.strip(), str(path), note.strip(),
                  datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def delete_shot(conn, shot_id, remove_file=False):
    row = conn.execute("SELECT path FROM shots WHERE id=?", (shot_id,)).fetchone()
    if remove_file and row and row[0]:
        try:
            Path(row[0]).unlink()
        except OSError:
            pass
    conn.execute("DELETE FROM shots WHERE id=?", (shot_id,)); conn.commit()


def add_pending(conn, path):
    conn.execute("INSERT OR IGNORE INTO pending_downloads (path,seen_at,dismissed) VALUES (?,?,0)",
                 (str(path), datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def list_pending(conn):
    rows = conn.execute("SELECT path FROM pending_downloads WHERE COALESCE(dismissed,0)=0 "
                        "ORDER BY seen_at DESC").fetchall()
    out = []
    for (p,) in rows:
        if Path(p).exists():
            out.append(Path(p))
        else:
            conn.execute("DELETE FROM pending_downloads WHERE path=?", (p,))
    conn.commit()
    return out


def clear_pending(conn, path):
    conn.execute("DELETE FROM pending_downloads WHERE path=?", (str(path),)); conn.commit()


def dismiss_pending(conn, path):
    conn.execute("UPDATE pending_downloads SET dismissed=1 WHERE path=?", (str(path),)); conn.commit()


# ---------------------------------------------------------------------------
# Relax — "Catch the Colour" ping-pong game (max 15 min/day)
#   Balls fall from the top; the board at the bottom has a colour.
#   Catch a matching ball -> +10.  Catch a wrong colour -> -5.
#   Clear a level with 20 catches OR 90 points inside 2 minutes.  7 levels.
# ---------------------------------------------------------------------------

RELAX_DAILY_SECONDS = 15 * 60
LEVEL_SECONDS = 60                 # each level lasts 1 minute
CLEAR_CATCHES = 20
CLEAR_SCORE = 90
BALLS_PER_COLOR = 30               # 30 balls of every colour in play per level
CATCH_POINTS = 10                  # correct colour caught
WRONG_PENALTY = -7                 # wrong colour caught
MISS_PENALTY = -1                  # board-colour ball allowed to fall through

# six ball colours in total
BALL_COLORS = ["#e63946", "#2a9d8f", "#457b9d", "#f4a261", "#9b5de5", "#ffd166"]

# motion: straight | sine | drift | zigzag | chaos
# speed/amp are 1.3x the previous tuning; the board shrinks faster each level.
GAME_LEVELS = [
    dict(level=1, speed=7.2,  colors=2, motion="straight",
         amp=0,   board=170, swap_ms=0,     accel=0.0,   morph_ms=0),
    dict(level=2, speed=9.1,  colors=3, motion="sine",
         amp=36,  board=150, swap_ms=0,     accel=0.0,   morph_ms=0),
    dict(level=3, speed=9.9,  colors=3, motion="sine",
         amp=60,  board=132, swap_ms=0,     accel=0.0,   morph_ms=0),
    dict(level=4, speed=10.4, colors=4, motion="drift",
         amp=78,  board=116, swap_ms=0,     accel=0.004, morph_ms=0),
    dict(level=5, speed=12.0, colors=5, motion="zigzag",
         amp=117, board=100, swap_ms=30000, accel=0.010, morph_ms=0),
    dict(level=6, speed=14.3, colors=6, motion="zigzag",
         amp=195, board=82,  swap_ms=12000, accel=0.022, morph_ms=1600),  # extremely hard
    dict(level=7, speed=17.6, colors=6, motion="chaos",
         amp=260, board=64,  swap_ms=6000,  accel=0.034, morph_ms=800),   # brutal
]


def level_pool(cfg, rng=random):
    """The level's ball supply: BALLS_PER_COLOR of each active colour, shuffled."""
    pool = []
    for c in BALL_COLORS[:cfg["colors"]]:
        pool.extend([c] * BALLS_PER_COLOR)
    rng.shuffle(pool)
    return pool


def spawn_burst(cfg):
    """How many balls arrive together (keeps fast levels visually dense)."""
    lvl = cfg["level"]
    return 1 if lvl <= 3 else (2 if lvl <= 5 else 3)


def spawn_interval_ms(cfg):
    """Deliver the whole pool inside the level's minute."""
    n = max(1, cfg["colors"] * BALLS_PER_COLOR)
    per = LEVEL_SECONDS * 1000 / n
    return max(120, int(per * spawn_burst(cfg)))


def level_config(n):
    return GAME_LEVELS[max(0, min(len(GAME_LEVELS) - 1, n - 1))]


def step_ball(ball, cfg, width, dt=1.0):
    """Advance one ball. Mutates and returns it (pure enough to unit-test)."""
    ball["t"] = ball.get("t", 0.0) + dt
    ball["vy"] = ball.get("vy", cfg["speed"]) + cfg["accel"] * dt
    ball["y"] += ball["vy"] * dt
    # level 7: balls change colour while falling
    morph = cfg.get("morph_ms", 0)
    if morph:
        ticks = morph / 16.0
        if ball["t"] - ball.get("last_morph", 0) >= ticks:
            ball["last_morph"] = ball["t"]
            choices = [c for c in BALL_COLORS[:cfg["colors"]] if c != ball["color"]]
            if choices:
                ball["color"] = random.choice(choices)
    motion = cfg["motion"]
    if motion == "straight":
        pass
    elif motion == "sine":
        ball["x"] = ball["x0"] + cfg["amp"] * math.sin(ball["t"] * 0.045 + ball["phase"])
    elif motion == "drift":
        ball["x"] += ball["vx"] * dt
        if ball["x"] < ball["r"] or ball["x"] > width - ball["r"]:
            ball["vx"] = -ball["vx"]
            ball["x"] = max(ball["r"], min(width - ball["r"], ball["x"]))
    elif motion == "zigzag":
        ball["x"] += ball["vx"] * dt
        if ball["t"] - ball.get("last_turn", 0) > ball["turn_every"]:
            ball["vx"] = -ball["vx"]; ball["last_turn"] = ball["t"]
        if ball["x"] < ball["r"] or ball["x"] > width - ball["r"]:
            ball["vx"] = -ball["vx"]
            ball["x"] = max(ball["r"], min(width - ball["r"], ball["x"]))
    elif motion == "chaos":
        ball["x"] += ball["vx"] * dt + cfg["amp"] * 0.012 * math.sin(ball["t"] * 0.11 + ball["phase"])
        if ball["t"] - ball.get("last_turn", 0) > ball["turn_every"]:
            ball["vx"] = -ball["vx"] * random.uniform(0.8, 1.4)
            ball["last_turn"] = ball["t"]
        if ball["x"] < ball["r"] or ball["x"] > width - ball["r"]:
            ball["vx"] = -ball["vx"]
            ball["x"] = max(ball["r"], min(width - ball["r"], ball["x"]))
    return ball


def new_ball(cfg, width, rng=random, color=None):
    r = 13
    lvl = cfg["level"]
    x = rng.uniform(r + 6, max(r + 7, width - r - 6))
    # zig-zag lateral speed is 1.3x the previous tuning
    vx = rng.choice([-1, 1]) * rng.uniform(1.2, 2.6) * (1 + lvl * 0.14) * 1.3
    # higher levels swing further before reversing -> wider, harder tracking
    turn = rng.uniform(34, 78) if lvl >= 5 else rng.uniform(22, 46)
    return {"x": x, "x0": x, "y": -r, "r": r, "vy": cfg["speed"], "vx": vx,
            "color": color or rng.choice(BALL_COLORS[:cfg["colors"]]),
            "phase": rng.uniform(0, 6.28), "t": 0.0,
            "turn_every": turn, "last_turn": 0.0}


def ball_caught(ball, board_x, board_w, board_y):
    """True when the ball's lower edge reaches the board and it's within its span."""
    return (ball["y"] + ball["r"] >= board_y
            and ball["y"] - ball["r"] <= board_y + 16
            and board_x <= ball["x"] <= board_x + board_w)


def score_for(ball_color, board_color):
    return CATCH_POINTS if ball_color == board_color else WRONG_PENALTY


def score_for_miss(ball_color, board_color):
    """Letting a board-colour ball fall through costs a point."""
    return MISS_PENALTY if ball_color == board_color else 0


def level_cleared(catches, score):
    return catches >= CLEAR_CATCHES or score >= CLEAR_SCORE


# ---- daily play budget ----
def relax_today(conn):
    d = datetime.now().date().isoformat()
    r = conn.execute("SELECT seconds, best_level FROM relax_play WHERE play_date=?", (d,)).fetchone()
    return (r[0] or 0, r[1] or 0) if r else (0, 0)


def relax_remaining(conn):
    used, _best = relax_today(conn)
    return max(0, RELAX_DAILY_SECONDS - used)


def add_relax_seconds(conn, secs, best_level=None):
    d = datetime.now().date().isoformat()
    used, best = relax_today(conn)
    new_best = max(best, best_level or 0)
    conn.execute("INSERT OR REPLACE INTO relax_play (play_date,seconds,best_level) VALUES (?,?,?)",
                 (d, used + int(secs), new_best))
    conn.commit()


def user_dir(project_path):
    """The project's User folder, created on demand."""
    d = Path(project_path) / USER_FOLDER
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def fast_scan(root, skip_names=()):
    """Walk a tree with os.scandir — much cheaper than rglob on network/OneDrive paths.

    Returns [(Path, name, category, datetime, size)].
    """
    out = []
    stack = [str(root)]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if e.name not in skip_names:
                                stack.append(e.path)
                        elif e.is_file(follow_symlinks=False):
                            st = e.stat()
                            out.append((Path(e.path), e.name, categorize(e.name),
                                        datetime.fromtimestamp(st.st_mtime), st.st_size))
                    except OSError:
                        continue
        except OSError:
            continue
    return out


def count_files(root):
    """Cheap file count without building a list."""
    n = 0
    stack = [str(root)]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        elif e.is_file(follow_symlinks=False):
                            n += 1
                    except OSError:
                        continue
        except OSError:
            continue
    return n


def next_req_key(conn, pid):
    n = conn.execute("SELECT COUNT(*) FROM requirements WHERE project_id=?", (pid,)).fetchone()[0]
    return f"REQ-{n+1:03d}"


# ---------------------------------------------------------------------------
# Three-level status workbooks:  Head -> Manager -> Team
#
#  MANAGER workbook (one per manager, released to their team)
#     sheet per team: row1 title, row2 headers
#       A Status % | B Employee Name | C Task Doing | D Start Date | E End Date | F Remark
#     TEAM_STATUS_ROW holds =AVERAGE(A3:A..)  -> locked (non-editable)
#
#  HEAD workbook (one per project, held by the Head)
#     "Summary" sheet, rows from HEAD_FIRST_ROW:
#       A Manager | B Status % (external link to that manager's file) |
#       C Normalization (0-1, the ONLY editable column) | D Weighted (=B*C)
#     FINAL_STATUS_CELL = SUM(D)   WEIGHT_SUM_CELL = SUM(C)
#
#  Beacon reads the manager workbooks DIRECTLY via the registered links, so it
#  never depends on Excel having refreshed/cached the external-link values.
# ---------------------------------------------------------------------------

STATUS_SHEET = "Summary"
FINAL_STATUS_CELL = "B3"
WEIGHT_SUM_CELL = "C3"
HEAD_FIRST_ROW = 6
TEAM_COLUMNS = ["Status %", "Employee Name", "Task Doing", "Start Date", "End Date", "Remark"]
TEAM_ROWS = 30
TEAM_STATUS_ROW = TEAM_ROWS + 3          # row holding the team's computed status
TEAM_STATUS_CELL = f"A{TEAM_STATUS_ROW}"


def workbook_blocked_reason(out):
    """Return a human reason the workbook can't be written, or None if it's fine."""
    out = Path(out)
    lock = out.parent / ("~$" + out.name)
    if lock.exists():
        return (f"'{out.name}' appears to be open in Excel (lock file {lock.name}).\n"
                "Close it in Excel and try again.")
    if out.exists():
        try:
            with open(out, "ab"):
                pass
        except PermissionError:
            return (f"'{out.name}' is locked or read-only.\n"
                    "Close it in Excel (and check it isn't marked read-only), then try again.")
        except OSError as e:
            return f"Cannot write '{out.name}': {e}"
    else:
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            probe = out.parent / ".beacon_write_test"
            probe.write_text("x"); probe.unlink()
        except PermissionError:
            return (f"No permission to write in:\n{out.parent}\n"
                    "Pick a different project location (Settings ▸ Change Project Location).")
        except OSError as e:
            return f"Cannot write to {out.parent}: {e}"
    return None


def head_workbook_path(project_path, project_name):
    return Path(project_path) / "Excel" / f"{safe_name(project_name)}_HEAD.xlsx"


MGR_SUMMARY_FIRST_ROW = 6


def _hdr(cell, fill, font, Alignment):
    cell.fill = fill; cell.font = font
    cell.alignment = Alignment(horizontal="center")


def manager_workbook_path(manager):
    """One workbook per manager, covering ALL their projects."""
    return files_root() / "Excel" / f"{safe_name(manager)}_Manager.xlsx"


def create_manager_workbook(manager, projects):
    """Manager's file: Summary sheet (one row per project) + one sheet per project.

    projects: list of project names. Each project sheet carries the 6 fixed columns;
    its computed status feeds the Summary, which the Head workbook links to.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    out = manager_workbook_path(manager)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    fill = PatternFill("solid", fgColor="1F3864"); hf = Font(bold=True, color="FFFFFF")

    sm = wb.active; sm.title = STATUS_SHEET
    sm["A1"] = f"{manager} — Project Status Summary"; sm["A1"].font = Font(bold=True, size=15)
    sm["A2"] = "Auto-calculated from each project sheet — do not edit."
    sm["A2"].font = Font(italic=True, size=9, color="808080")
    for j, name in enumerate(["Project", "Status %", "Sheet"], start=1):
        _hdr(sm.cell(row=MGR_SUMMARY_FIRST_ROW - 1, column=j, value=name), fill, hf, Alignment)

    safe_titles = []
    for i, proj in enumerate(projects):
        title = safe_name(proj)[:31] or f"Project{i+1}"
        base = title; n = 2
        while title in safe_titles:
            title = f"{base[:28]}_{n}"; n += 1
        safe_titles.append(title)
        r = MGR_SUMMARY_FIRST_ROW + i
        sm.cell(row=r, column=1, value=proj)
        sm.cell(row=r, column=2, value=f"='{title}'!{TEAM_STATUS_CELL}").number_format = "0.0"
        sm.cell(row=r, column=3, value=title)
    for col, wdt in zip("ABC", (34, 14, 24)):
        sm.column_dimensions[col].width = wdt
    sm.protection.sheet = True          # Summary is not directly editable
    sm.protection.enable()

    for proj, title in zip(projects, safe_titles):
        ws = wb.create_sheet(title)
        ws["A1"] = f"{manager} — {proj}"; ws["A1"].font = Font(bold=True, size=12)
        for j, name in enumerate(TEAM_COLUMNS, start=1):
            _hdr(ws.cell(row=2, column=j, value=name), fill, hf, Alignment)
        for r in range(3, 3 + TEAM_ROWS):
            ws.cell(row=r, column=1).number_format = "0"
            ws.cell(row=r, column=4).number_format = "DD-MMM-YYYY"
            ws.cell(row=r, column=5).number_format = "DD-MMM-YYYY"
        sc = ws.cell(row=TEAM_STATUS_ROW, column=1,
                     value=f"=IF(COUNT(A3:A{TEAM_ROWS + 2})=0,0,"
                           f"ROUND(AVERAGE(A3:A{TEAM_ROWS + 2}),1))")
        sc.font = Font(bold=True, size=12); sc.number_format = "0.0"
        ws.cell(row=TEAM_STATUS_ROW, column=2,
                value="<- PROJECT STATUS (auto-calculated)").font = Font(bold=True)
        for col, wdt in zip("ABCDEF", (10, 22, 34, 14, 14, 30)):
            ws.column_dimensions[col].width = wdt
        ws.freeze_panes = "A3"
    wb.save(out)
    return out


def manager_summary_row(workbook, project_name):
    """Find the Summary row number for a project in a manager workbook."""
    from openpyxl import load_workbook
    p = Path(workbook)
    if not p.exists():
        return None
    try:
        wb = load_workbook(p, read_only=True)
        if STATUS_SHEET not in wb.sheetnames:
            return None
        sm = wb[STATUS_SHEET]
        r = MGR_SUMMARY_FIRST_ROW
        while sm.cell(row=r, column=1).value:
            if str(sm.cell(row=r, column=1).value).strip().lower() == project_name.strip().lower():
                return r
            r += 1
    except Exception:
        return None
    return None


def read_manager_status(workbook, project_name):
    """Read one project's status from a manager workbook's Summary sheet."""
    from openpyxl import load_workbook
    import tempfile
    p = Path(workbook)
    if not p.exists():
        return {"ok": False, "error": "Manager workbook not found", "path": str(p)}
    try:
        stamp = datetime.fromtimestamp(p.stat().st_mtime)
    except OSError:
        stamp = None
    tmp = None; wb = None
    try:
        try:
            wb = load_workbook(p, data_only=True, read_only=True)
        except PermissionError:
            fd, tmp = tempfile.mkstemp(suffix=".xlsx"); os.close(fd)
            shutil.copyfile(p, tmp)
            wb = load_workbook(tmp, data_only=True, read_only=True)
        if STATUS_SHEET not in wb.sheetnames:
            return {"ok": False, "error": f"No '{STATUS_SHEET}' sheet", "path": str(p),
                    "modified": stamp}
        sm = wb[STATUS_SHEET]
        val = None
        r = MGR_SUMMARY_FIRST_ROW
        while sm.cell(row=r, column=1).value:
            if str(sm.cell(row=r, column=1).value).strip().lower() == project_name.strip().lower():
                val = sm.cell(row=r, column=2).value; break
            r += 1
    except PermissionError as e:
        return {"ok": False, "error": f"Permission denied ({e})", "path": str(p), "modified": stamp}
    except Exception as e:
        return {"ok": False, "error": f"Could not open: {e}", "path": str(p), "modified": stamp}
    finally:
        try:
            if wb: wb.close()
        except Exception:
            pass
        if tmp:
            try: os.remove(tmp)
            except OSError: pass
    if val is None:
        return {"ok": False, "error": f"'{project_name}' not found in the manager Summary",
                "path": str(p), "modified": stamp}
    try:
        pct = float(val)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Manager Summary has no calculated value — open it in "
                                      "Excel and save it once",
                "path": str(p), "modified": stamp}
    return {"ok": True, "percent": max(0.0, min(100.0, pct)), "path": str(p), "modified": stamp}


def create_head_workbook(project_path, project_name, managers):
    """Head's file: one row per manager, only the normalization column editable."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    out = head_workbook_path(project_path, project_name)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook(); sm = wb.active; sm.title = STATUS_SHEET
    fill = PatternFill("solid", fgColor="1F3864"); hf = Font(bold=True, color="FFFFFF")
    sm["A1"] = f"{project_name} — Project Status (Head)"; sm["A1"].font = Font(bold=True, size=16)
    sm["A2"] = "FINAL PROJECT STATUS"; sm["A2"].font = Font(bold=True, size=14)
    sm["A3"] = "Final %"; sm["A3"].font = Font(bold=True)
    sm["D3"] = "<- weights must total 1.00"
    sm["D3"].font = Font(italic=True, size=9, color="808080")
    for j, name in enumerate(["Manager", "Status %", "Normalization (0-1)", "Weighted"], start=1):
        _hdr(sm.cell(row=HEAD_FIRST_ROW - 1, column=j, value=name), fill, hf, Alignment)
    share = round(1.0 / max(len(managers), 1), 4)
    for i, mgr in enumerate(managers):
        r = HEAD_FIRST_ROW + i
        sm.cell(row=r, column=1, value=mgr)
        sm.cell(row=r, column=2, value=0).number_format = "0.0"     # filled when linked
        sm.cell(row=r, column=3, value=share)                       # Head edits weights here
        sm.cell(row=r, column=4, value=f"=B{r}*C{r}").number_format = "0.00"
    last = HEAD_FIRST_ROW + len(managers) - 1
    sm[FINAL_STATUS_CELL] = f"=ROUND(SUM(D{HEAD_FIRST_ROW}:D{last}),1)"
    sm[FINAL_STATUS_CELL].font = Font(bold=True, size=14)
    sm[FINAL_STATUS_CELL].number_format = "0.0"
    sm[WEIGHT_SUM_CELL] = f"=ROUND(SUM(C{HEAD_FIRST_ROW}:C{last}),3)"
    sm[WEIGHT_SUM_CELL].font = Font(bold=True)
    for col, wdt in zip("ABCD", (28, 14, 20, 12)):
        sm.column_dimensions[col].width = wdt
    # NOTE: sheet protection disabled during development (Summary fully editable)
    wb.save(out)
    return out


def link_manager_in_head(head_path, manager, workbook, project_name):
    """Point the Head row for `manager` at that manager's Summary row for this project."""
    from openpyxl import load_workbook
    hp = Path(head_path)
    if not hp.exists():
        return False
    row = manager_summary_row(workbook, project_name)
    if row is None:
        return False
    wb = load_workbook(hp)
    if STATUS_SHEET not in wb.sheetnames:
        return False
    sm = wb[STATUS_SHEET]
    wbp = Path(workbook)
    ref = f"'{wbp.parent}\\[{wbp.name}]{STATUS_SHEET}'!B{row}"
    r = HEAD_FIRST_ROW
    while sm.cell(row=r, column=1).value:
        if str(sm.cell(row=r, column=1).value).strip().lower() == manager.strip().lower():
            sm.cell(row=r, column=2, value=f"={ref}")
            sm.cell(row=r, column=2).number_format = "0.0"
            wb.save(hp)
            return True
        r += 1
    return False


def read_team_status(workbook, sheet):
    """Read one team's computed status from a manager workbook (via a copy if locked)."""
    from openpyxl import load_workbook
    import tempfile
    p = Path(workbook)
    if not p.exists():
        return {"ok": False, "error": "File not found", "path": str(p)}
    try:
        stamp = datetime.fromtimestamp(p.stat().st_mtime)
    except OSError:
        stamp = None
    tmp = None; wb = None
    try:
        try:
            wb = load_workbook(p, data_only=True, read_only=True)
        except PermissionError:
            fd, tmp = tempfile.mkstemp(suffix=".xlsx"); os.close(fd)
            shutil.copyfile(p, tmp)
            wb = load_workbook(tmp, data_only=True, read_only=True)
        if sheet not in wb.sheetnames:
            return {"ok": False, "error": f"No sheet '{sheet}'", "path": str(p), "modified": stamp}
        val = wb[sheet][TEAM_STATUS_CELL].value
    except PermissionError as e:
        return {"ok": False, "error": f"Permission denied ({e})", "path": str(p), "modified": stamp}
    except Exception as e:
        return {"ok": False, "error": f"Could not open: {e}", "path": str(p), "modified": stamp}
    finally:
        try:
            if wb: wb.close()
        except Exception:
            pass
        if tmp:
            try: os.remove(tmp)
            except OSError: pass
    if val is None:
        return {"ok": False, "error": "No cached value — open in Excel and save once",
                "path": str(p), "modified": stamp}
    try:
        pct = float(val)
    except (TypeError, ValueError):
        return {"ok": False, "error": f"Status is not a number ({val!r})",
                "path": str(p), "modified": stamp}
    return {"ok": True, "percent": max(0.0, min(100.0, pct)), "path": str(p), "modified": stamp}


def read_head_workbook(path):
    """Read the Head Excel's Summary sheet: final % (B3), weight sum, manager rows."""
    from openpyxl import load_workbook
    import tempfile
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": "Head Excel not found", "path": str(p)}
    try:
        stamp = datetime.fromtimestamp(p.stat().st_mtime)
    except OSError:
        stamp = None
    tmp = None; wb = None
    try:
        try:
            wb = load_workbook(p, data_only=True, read_only=True)
        except PermissionError:
            fd, tmp = tempfile.mkstemp(suffix=".xlsx"); os.close(fd)
            shutil.copyfile(p, tmp)
            wb = load_workbook(tmp, data_only=True, read_only=True)
        if STATUS_SHEET not in wb.sheetnames:
            return {"ok": False, "error": f"No '{STATUS_SHEET}' sheet", "path": str(p),
                    "modified": stamp}
        sm = wb[STATUS_SHEET]
        final = sm[FINAL_STATUS_CELL].value
        wsum = sm[WEIGHT_SUM_CELL].value
        managers = []
        r = HEAD_FIRST_ROW
        while sm.cell(row=r, column=1).value:
            managers.append((str(sm.cell(row=r, column=1).value),
                             sm.cell(row=r, column=2).value,
                             sm.cell(row=r, column=3).value))
            r += 1
    except PermissionError as e:
        return {"ok": False, "error": f"Permission denied ({e})", "path": str(p), "modified": stamp}
    except Exception as e:
        return {"ok": False, "error": f"Could not open: {e}", "path": str(p), "modified": stamp}
    finally:
        try:
            if wb: wb.close()
        except Exception:
            pass
        if tmp:
            try: os.remove(tmp)
            except OSError: pass

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    err_vals = {"#N/A", "#REF!", "#VALUE!", "#NAME?", "#DIV/0!"}
    link_errors = [m for m, s, _w in managers if isinstance(s, str) and s.strip() in err_vals]
    pct = num(final)
    if pct is None:
        if link_errors:
            msg = ("Head Excel's links to the manager files haven't resolved "
                   f"({', '.join(link_errors[:3])}). Open it in Excel, choose "
                   "'Enable Content'/'Update Links', and save.")
        else:
            msg = ("Head Excel has no calculated value — open it in Excel, "
                   "allow the links to update, and save it once")
        return {"ok": False, "path": str(p), "modified": stamp, "managers": managers,
                "error": msg}
    return {"ok": True, "percent": max(0.0, min(100.0, pct)), "weight_sum": num(wsum),
            "managers": [(m, num(s), num(w)) for m, s, w in managers],
            "path": str(p), "modified": stamp}


def compute_project_status(conn, project_id):
    """Project status from the HEAD Excel (primary source).

    Managers link their team workbooks into the Head file, so the Head file is
    authoritative. If it has no calculated value yet (never opened/saved in Excel),
    fall back to reading the linked manager workbooks so the Head still sees a number.
    """
    row = conn.execute("SELECT name, path FROM projects WHERE id=?", (project_id,)).fetchone()
    if not row:
        return {"ok": False, "percent": None, "managers": [], "weight_sum": 0,
                "problems": ["project not found"], "modified": None, "source": "none"}
    name, path = row
    head = head_workbook_path(path, name)
    res = read_head_workbook(head)
    problems = []

    if res.get("ok"):
        wsum = res.get("weight_sum")
        if wsum is not None and abs(wsum - 1.0) > 0.001:
            problems.append(f"normalization weights total {round(wsum, 3)} (should be 1.00)")
        managers = [(m, s, w) for m, s, w in res["managers"]]
        for m, s, _w in managers:
            if s is None:
                problems.append(f"{m}: no status in Head Excel (not linked yet?)")
        return {"ok": True, "percent": round(res["percent"], 1), "managers": managers,
                "weight_sum": res.get("weight_sum") or 0, "problems": problems,
                "modified": res.get("modified"), "source": "head"}

    # --- fallback: compute from the manager workbooks Beacon knows about ---
    problems.append(res.get("error", "Head Excel unreadable"))
    links = list_manager_links(conn, project_id)
    managers, total, wsum, newest = [], 0.0, 0.0, None
    for _lid, mgr, wbk, sheet, weight in links:
        weight = float(weight or 0.0); wsum += weight
        if not wbk or not sheet:
            managers.append((mgr, None, weight)); continue
        tr = read_manager_status(wbk, name)
        if tr.get("ok"):
            managers.append((mgr, tr["percent"], weight)); total += tr["percent"] * weight
            if tr.get("modified") and (newest is None or tr["modified"] > newest):
                newest = tr["modified"]
        else:
            managers.append((mgr, None, weight)); problems.append(f"{mgr}: {tr.get('error')}")
    ok = any(p is not None for _m, p, _w in managers)
    return {"ok": ok, "percent": round(total, 1) if ok else None, "managers": managers,
            "weight_sum": round(wsum, 3), "problems": problems, "modified": newest,
            "source": "manager files" if ok else "none"}


# ---------------------------------------------------------------------------
# Greeting engine — 320-line pool (80 per bucket) built combinatorially
# ---------------------------------------------------------------------------

_OPEN = {
    "morning":   ["A fresh start.", "New day.", "Morning.", "Here we go.",
                  "Clean slate today.", "First light.", "Another sunrise.", "The day is young."],
    "afternoon": ["Halfway there.", "Afternoon.", "Keep the momentum.", "Post-lunch push.",
                  "The middle stretch.", "Steady now.", "Second wind.", "You're in the flow."],
    "evening":   ["Winding down.", "Evening.", "Golden hour.", "The day softens.",
                  "Almost there.", "Lights coming on.", "Day's tail end.", "Time to close loops."],
    "late":      ["Burning the midnight oil.", "Late one.", "Quiet hours.", "The world's asleep.",
                  "Deep night.", "Still at it.", "Small hours.", "Night shift."],
}
_ENC = {
    "morning":   ["Let's make it count.", "One clear priority beats ten vague ones.",
                  "Small steps, steady pace.", "What's the one thing that matters most?",
                  "Momentum starts now.", "Deep work before noise.", "Set the tone early.",
                  "Progress over perfection.", "Pick the hard thing first.", "Build something today."],
    "afternoon": ["Finish what you started this morning.", "One more solid block of focus.",
                  "Tidy the loose ends.", "Keep it rolling.", "Small wins add up.",
                  "Stay with it.", "Don't let the inbox win.", "Ship a little something.",
                  "Refocus on the main thing.", "Push through the dip."],
    "evening":   ["Finish one thing well.", "Log what today taught you.", "Tie a bow on it.",
                  "Note tomorrow's first step.", "Rest is part of the work.", "Reflect, then release.",
                  "Leave it better than you found it.", "Wrap up and unplug.",
                  "Capture the loose thoughts.", "Set up tomorrow-you for a win."],
    "late":      ["Be kind to yourself.", "Note it down and rest soon.",
                  "The best idea can wait till morning.", "Don't trade tomorrow for tonight.",
                  "One last thought, then sleep.", "Rest is a feature, not a bug.",
                  "Sharp minds need sleep.", "Save your progress and step away.",
                  "Tomorrow will thank you.", "Close the laptop soon."],
}
_SALUTE = {"morning": "Good morning", "afternoon": "Good afternoon",
           "evening": "Good evening", "late": "Still up"}
_DAY_NOTE = {0: "It's Monday — set the week's direction.", 1: "Tuesday: deep-work day.",
             2: "Midweek — review progress.", 3: "Thursday — tie up loose ends.",
             4: "Friday — close out cleanly.", 5: "Weekend mode.",
             6: "Sunday — a little planning goes a long way."}


def build_pool():
    pool = {}
    for b in _OPEN:
        pool[b] = [f"{o} {e}" for o in _OPEN[b] for e in _ENC[b]]
    return pool

POOL = build_pool()   # {bucket: [80 lines]}  -> 320 total

# time-agnostic positive punchlines that rotate every launch / 6 hours (Req2)
_PUNCH_A = [
    "Keep going.", "You've got this.", "One step at a time.", "Small wins compound.",
    "Progress over perfection.", "Stay curious.", "Do the hard thing first.",
    "Focus wins.", "Ship it.", "Make it count.", "Trust the process.", "Show up.",
    "Keep it simple.", "Build momentum.", "Aim a little higher.",
]
_PUNCH_B = [
    "Great engineers are made, not born.", "Every fix makes you sharper.",
    "Clarity beats cleverness.", "The details are the work.",
    "Done is better than perfect.", "Curiosity is a superpower.",
    "Consistency compounds.", "Your future self will thank you.",
    "Momentum is a choice.", "Depth beats speed.", "Discipline is freedom.",
    "Effort is the shortcut.", "Learning is never wasted time.",
    "Calm mind, clean code.", "Steady beats fast.",
]
PUNCHLINES = [f"{a} {b}" for a in _PUNCH_A for b in _PUNCH_B]   # 225

# Curated short quotes (each attributed, kept brief) shown below the username.
QUOTES = [
    "The important thing is to never stop questioning. — Einstein",
    "Imagination is more important than knowledge. — Einstein",
    "In the middle of difficulty lies opportunity. — Einstein",
    "Life is like a bicycle — to keep balance, keep moving. — Einstein",
    "Look deep into nature, you will understand everything better. — Einstein",
    "Strive not to be a success, but to be of value. — Einstein",
    "Nothing in life is to be feared, only understood. — Marie Curie",
    "Be less curious about people and more curious about ideas. — Marie Curie",
    "Somewhere, something incredible is waiting to be known. — Carl Sagan",
    "Science is a way of thinking more than a body of knowledge. — Carl Sagan",
    "We are made of star-stuff. — Carl Sagan",
    "I would rather have questions that can't be answered. — Feynman",
    "The first principle is that you must not fool yourself. — Feynman",
    "Study hard what interests you the most. — Feynman",
    "If I have seen further, it is by standing on giants' shoulders. — Newton",
    "Genius is one percent inspiration, ninety-nine percent perspiration. — Edison",
    "I have not failed. I've found ten thousand ways that won't work. — Edison",
    "Chance favors the prepared mind. — Louis Pasteur",
    "Look up at the stars, not down at your feet. — Stephen Hawking",
    "Intelligence is the ability to adapt to change. — Stephen Hawking",
    "The present is theirs; the future is mine. — Tesla",
    "Measure what is measurable; make measurable what is not. — Galileo",
    "The good thing about science is it's true whether you believe it. — Tyson",
    "Dream, dream, dream — dreams transform into thoughts. — A. P. J. Abdul Kalam",
    "If you want to shine like a sun, first burn like a sun. — Kalam",
    "Failure will never overtake me if my will to succeed is strong. — Kalam",
    "An experiment is a question science poses to nature. — Max Planck",
    "Everything you can imagine is real. — Picasso",
    "Art washes from the soul the dust of everyday life. — Picasso",
    "I dream my painting and I paint my dream. — Van Gogh",
    "Great things are done by small things brought together. — Van Gogh",
    "Learning never exhausts the mind. — Leonardo da Vinci",
    "Simplicity is the ultimate sophistication. — Leonardo da Vinci",
    "I am still learning. — Michelangelo",
    "Creativity takes courage. — Henri Matisse",
    "Color is my day-long obsession, joy and torment. — Monet",
    "To create one's own world takes courage. — Georgia O'Keeffe",
    "You are the universe in ecstatic motion. — Rumi",
    "What you seek is seeking you. — Rumi",
    "The wound is the place where the light enters you. — Rumi",
    "Faith is the bird that feels the light before the dawn. — Tagore",
    "You can't cross the sea by standing and staring at the water. — Tagore",
    "Let life be beautiful like summer flowers. — Tagore",
    "Nothing will work unless you do. — Maya Angelou",
    "We may encounter many defeats but must not be defeated. — Maya Angelou",
    "Go confidently in the direction of your dreams. — Thoreau",
    "That which we persist in doing becomes easier. — Emerson",
    "Write it on your heart that every day is the best day. — Emerson",
    "Adopt the pace of nature: her secret is patience. — Emerson",
    "What lies within us matters most. — Emerson",
    "Whatever you are, be a good one. — Abraham Lincoln",
    "Live as if you die tomorrow; learn as if you live forever. — Gandhi",
    "The future depends on what you do today. — Gandhi",
    "Strength comes from an indomitable will. — Gandhi",
    "Be the change you wish to see in the world. — Gandhi",
    "It always seems impossible until it's done. — Nelson Mandela",
    "The greatest glory is rising every time we fall. — Mandela",
    "Success is not final, failure is not fatal. — Churchill",
    "If you're going through hell, keep going. — Churchill",
    "Darkness cannot drive out darkness; only light can. — Martin Luther King Jr.",
    "Faith is taking the first step without seeing the staircase. — MLK Jr.",
    "The only limit to tomorrow is our doubts of today. — F. D. Roosevelt",
    "Believe you can and you're halfway there. — Theodore Roosevelt",
    "Credit belongs to the one in the arena. — Theodore Roosevelt",
    "The journey of a thousand miles begins with one step. — Lao Tzu",
    "Nature does not hurry, yet everything is accomplished. — Lao Tzu",
    "He who conquers himself is the mightiest warrior. — Confucius",
    "It does not matter how slowly you go, so long as you don't stop. — Confucius",
    "Our life is what our thoughts make it. — Marcus Aurelius",
    "The happiness of your life depends on your thoughts. — Marcus Aurelius",
    "We suffer more in imagination than in reality. — Seneca",
    "Luck is preparation meeting opportunity. — Seneca",
    "Knowing yourself is the beginning of all wisdom. — Aristotle",
    "Quality is not an act, it is a habit. — Aristotle",
    "Well begun is half done. — Aristotle",
    "What we think, we become. — Buddha",
    "Peace comes from within. Do not seek it without. — Buddha",
    "Three things cannot be hidden: the sun, the moon, the truth. — Buddha",
    "In every walk with nature one receives more than he seeks. — John Muir",
    "The mountains are calling and I must go. — John Muir",
    "Keep close to Nature's heart. — John Muir",
    "Study nature, love nature, stay close to nature. — Frank Lloyd Wright",
    "Fall seven times, stand up eight. — Japanese proverb",
    "The best time to plant a tree was twenty years ago; the next is now. — Proverb",
    "A ship in harbor is safe, but that's not what ships are for. — John A. Shedd",
    "Well done is better than well said. — Benjamin Franklin",
    "An investment in knowledge pays the best interest. — Benjamin Franklin",
    "Energy and persistence conquer all things. — Benjamin Franklin",
    "The best way out is always through. — Robert Frost",
    "In three words I can sum up life: it goes on. — Robert Frost",
    "Do what you can, with what you have, where you are. — Theodore Roosevelt",
    "The mind is everything. What you think you become. — Buddha",
    "Turn your wounds into wisdom. — Oprah Winfrey",
    "A person who never made a mistake never tried anything new. — Einstein",
    "The scientist is not a person who gives the right answers. — Claude Lévi-Strauss",
    "Curiosity is the wick in the candle of learning. — William Arthur Ward",
    "Waste no more time arguing what a good person should be. Be one. — Marcus Aurelius",
    "The noblest pleasure is the joy of understanding. — Leonardo da Vinci",
    "Errors using inadequate data are less than using no data. — Charles Babbage",
    "Not everything that counts can be counted. — William Bruce Cameron",
    "The universe is under no obligation to make sense to you. — Tyson",
    "Have the courage to follow your heart and intuition. — Steve Jobs",
    "Stay hungry, stay foolish. — Steve Jobs",
    "Innovation distinguishes a leader from a follower. — Steve Jobs",
    "Whether you think you can or can't, you're right. — Henry Ford",
    "Quality means doing it right when no one is looking. — Henry Ford",
    "The only way to do great work is to love what you do. — Steve Jobs",
    "Discipline is the bridge between goals and accomplishment. — Jim Rohn",
    "Patience and perseverance have a magical effect. — John Quincy Adams",
    "Perfection is not attainable, but chasing it we catch excellence. — Vince Lombardi",
    "Everything is theoretically impossible until it is done. — Robert Heinlein",
    "Dreams are not what you see in sleep; dreams don't let you sleep. — A. P. J. Abdul Kalam",
    "Excellence is a continuous process, not an accident. — A. P. J. Abdul Kalam",
    "Don't take rest after your first victory. — A. P. J. Abdul Kalam",
    "Man needs difficulties in life; they are necessary for success. — A. P. J. Abdul Kalam",
    "Thinking is capital, enterprise the way, hard work the solution. — A. P. J. Abdul Kalam",
    "You have to dream before your dreams can come true. — A. P. J. Abdul Kalam",
    "Let us sacrifice today so our children have a better tomorrow. — A. P. J. Abdul Kalam",
    "Your most unhappy customers are your greatest source of learning. — Bill Gates",
    "Patience is a key element of success. — Bill Gates",
    "The way to get started is to quit talking and begin doing. — Walt Disney",
    "Chase the vision, not the money. — Tony Hsieh",
    "Ideas are easy; implementation is hard. — Guy Kawasaki",
    "Make something people want. — Paul Graham",
    "The best way to predict the future is to invent it. — Alan Kay",
    "Any sufficiently advanced technology is indistinguishable from magic. — Arthur C. Clarke",
    "Simplicity is prerequisite for reliability. — Edsger Dijkstra",
    "First, solve the problem. Then, write the code. — John Johnson",
    "Scientists study the world as it is; engineers create what never was. — von Kármán",
    "Good design is as little design as possible. — Dieter Rams",
    "The details are not the details; they make the design. — Charles Eames",
    "Whatever you can do or dream, begin it. Boldness has genius. — Goethe",
    "The unexamined life is not worth living. — Socrates",
    "I know that I know nothing. — Socrates",
    "Wonder is the beginning of wisdom. — Socrates",
    "He who has a why to live can bear almost any how. — Nietzsche",
    "That which does not kill us makes us stronger. — Nietzsche",
    "I think, therefore I am. — Descartes",
    "Common sense is not so common. — Voltaire",
    "Judge a person by their questions rather than their answers. — Voltaire",
    "Knowing others is wisdom; knowing yourself is enlightenment. — Lao Tzu",
    "Happiness depends upon ourselves. — Aristotle",
    "It is the mark of an educated mind to entertain a thought without accepting it. — Aristotle",
    "The obstacle is the way. — Marcus Aurelius",
    "No great thing is created suddenly. — Epictetus",
    "First say to yourself what you would be; then do what you must. — Epictetus",
    "Persistence guarantees that results are inevitable. — Paramahansa Yogananda",
    "A goal without a plan is just a wish. — Antoine de Saint-Exupéry",
    "Perfection is achieved when there is nothing left to take away. — Saint-Exupéry",
    "Vision without execution is hallucination. — Thomas Edison",
    "The value of an idea lies in the using of it. — Thomas Edison",
]
GREETING_LINES = PUNCHLINES + QUOTES
# interleave quotes with punchlines so BOTH show up across the first few opens
_qs = QUOTES[:]; _ps = PUNCHLINES[:]
random.Random(7).shuffle(_qs); random.Random(11).shuffle(_ps)
GREETING_LINES = []
for _i in range(max(len(_qs), len(_ps))):
    if _i < len(_qs): GREETING_LINES.append(_qs[_i])   # quote
    if _i < len(_ps): GREETING_LINES.append(_ps[_i])   # punchline


def _bucket(h):
    return ("morning" if 5 <= h < 12 else "afternoon" if 12 <= h < 17
            else "evening" if 17 <= h < 21 else "late")


def greeting(name, now=None):
    now = now or datetime.now()
    b = _bucket(now.hour)
    rng = random.Random(now.strftime("%Y-%m-%d-%H") + b)  # varies through the day
    return {"salute": f"{_SALUTE[b]}, {name.split()[0] if name else 'there'}",
            "line": rng.choice(POOL[b]), "day_note": _DAY_NOTE[now.weekday()],
            "date_str": f"{now.strftime('%A')} · {fmt_date(now)}",
            "time_str": now.strftime("%I:%M %p").lstrip("0")}


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

def run_gui():
    from PySide6.QtWidgets import (
        QApplication, QDialog, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QComboBox, QPushButton, QFrame,
        QStackedWidget, QTableWidget, QTableWidgetItem,
        QListWidget, QFileDialog, QDateEdit, QPlainTextEdit, QHeaderView,
        QMessageBox, QAbstractItemView, QInputDialog, QMenu, QCheckBox,
    )
    from PySide6.QtCore import Qt, QTimer, QDate, QRectF, QPointF, QSize, QPoint
    from PySide6.QtGui import (QAction, QPainter, QColor, QPen, QBrush, QFont,
                               QPainterPath, QLinearGradient, QRadialGradient, QPixmap)

    def text_prompt(parent, title, label, text=""):
        t, ok = QInputDialog.getText(parent, title, label, text=text)
        return t, ok

    # ---- project file-tile (custom painted) ------------------------------
    class SoftBg(QWidget):
        """A subtle, professional light backdrop behind the whole app body."""
        def paintEvent(self, _):
            p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
            r = self.rect()
            g = QLinearGradient(0, 0, 0, r.height())
            g.setColorAt(0.0, QColor(CURRENT["BG"]))
            g.setColorAt(1.0, QColor(CURRENT["PANEL2"]))
            p.fillRect(r, QBrush(g))
            rng = random.Random("beacon-softbg")
            acc = QColor(CURRENT["ACCENT"])
            p.setPen(Qt.NoPen)
            for _ in range(5):
                rad = rng.randint(160, 340)
                cx = rng.uniform(0, r.width()); cy = rng.uniform(0, r.height())
                c = QColor(acc); c.setAlpha(9)
                p.setBrush(c); p.drawEllipse(QPointF(cx, cy), rad, rad)
            p.end()

    class FileDropTable(QTableWidget):
        """Results table that also accepts dropped files (routes them by format)."""
        def __init__(self, rows, cols):
            super().__init__(rows, cols)
            self._on_drop = None
            self.setAcceptDrops(True)

        def dragEnterEvent(self, e):
            if e.mimeData().hasUrls(): e.acceptProposedAction()

        def dragMoveEvent(self, e):
            if e.mimeData().hasUrls(): e.acceptProposedAction()

        def dropEvent(self, e):
            paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            if paths and self._on_drop:
                self._on_drop(paths)

    class PieChart(QWidget):
        """Simple pie: list of (label, value, color)."""
        def __init__(self):
            super().__init__(); self.data = []; self.setMinimumHeight(220)

        def set_data(self, data): self.data = data; self.update()

        def paintEvent(self, _):
            p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
            total = sum(max(0.0, v) for _l, v, _c in self.data)
            side = min(self.width() * 0.55, self.height()) - 16
            if side <= 10:
                p.end(); return
            box = QRectF(8, (self.height() - side) / 2, side, side)
            if total <= 0:
                p.setPen(QPen(QColor(CURRENT["MUTED"])))
                p.drawText(self.rect(), Qt.AlignCenter, "No data"); p.end(); return
            start = 90 * 16
            p.setPen(QPen(QColor(CURRENT["PANEL"]), 2))
            for _label, val, col in self.data:
                span = int(-360 * 16 * (max(0.0, val) / total))
                p.setBrush(QColor(col)); p.drawPie(box, start, span); start += span
            # legend
            lx = box.right() + 18; ly = box.top() + 6
            f = QFont("Segoe UI"); f.setPointSize(9); p.setFont(f)
            for label, val, col in self.data:
                p.setPen(Qt.NoPen); p.setBrush(QColor(col))
                p.drawRoundedRect(QRectF(lx, ly, 11, 11), 3, 3)
                p.setPen(QPen(QColor(CURRENT["TEXT"])))
                pct = 100.0 * max(0.0, val) / total
                p.drawText(QRectF(lx + 17, ly - 3, self.width() - lx - 20, 18),
                           Qt.AlignVCenter | Qt.AlignLeft, f"{label}  {pct:.0f}%")
                ly += 20
            p.end()

    class BarChart(QWidget):
        """Horizontal % bars: list of (label, percent, color). Clickable rows."""
        def __init__(self, on_click=None):
            super().__init__(); self.data = []; self.setMinimumHeight(220)
            self._on_click = on_click; self._rects = []
            if on_click:
                self.setCursor(Qt.PointingHandCursor)

        def set_data(self, data): self.data = data; self.update()

        def mousePressEvent(self, e):
            if not self._on_click:
                return
            for i, (y0, y1) in enumerate(self._rects):
                if y0 <= e.position().y() <= y1:
                    self._on_click(i); return

        def paintEvent(self, _):
            p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
            self._rects = []
            if not self.data:
                p.setPen(QPen(QColor(CURRENT["MUTED"])))
                p.drawText(self.rect(), Qt.AlignCenter, "No data"); p.end(); return
            f = QFont("Segoe UI"); f.setPointSize(9); p.setFont(f)
            label_w = 120
            bar_h = min(26, max(14, (self.height() - 20) / max(len(self.data), 1) - 8))
            y = 10
            track_w = self.width() - label_w - 70
            for label, pct, col in self.data:
                pct = max(0.0, min(100.0, float(pct or 0)))
                p.setPen(QPen(QColor(CURRENT["TEXT"])))
                p.drawText(QRectF(6, y, label_w - 10, bar_h), Qt.AlignVCenter | Qt.AlignLeft,
                           label if len(label) <= 16 else label[:15] + "…")
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(CURRENT["PANEL2"]))
                p.drawRoundedRect(QRectF(label_w, y, track_w, bar_h), 6, 6)
                p.setBrush(QColor(col))
                p.drawRoundedRect(QRectF(label_w, y, max(6.0, track_w * pct / 100.0), bar_h), 6, 6)
                p.setPen(QPen(QColor(CURRENT["TEXT"])))
                p.drawText(QRectF(label_w + track_w + 8, y, 60, bar_h),
                           Qt.AlignVCenter | Qt.AlignLeft, f"{pct:.0f}%")
                self._rects.append((y, y + bar_h))
                y += bar_h + 8
            p.end()

    class HeroBanner(QWidget):
        """Vibrant textured banner; design (palette+texture) rotates (CURRENT_DESIGN)."""
        def __init__(self):
            super().__init__()
            self.setMinimumHeight(150)

        def paintEvent(self, _):
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            rf = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            clip = QPainterPath(); clip.addRoundedRect(rf, 16, 16)
            p.setClipPath(clip)
            mode = hero_mode()
            if mode == "sunrise":
                self._paint_sunrise(p, rf)
            elif mode == "moon":
                self._paint_moon(p, rf)
            else:
                self._paint_design(p, rf)
            # contrast scrim (keeps white text readable on any scene)
            p.fillRect(rf, QColor(0, 0, 0, 34))
            rg = QRadialGradient(rf.center(), max(rf.width(), rf.height()) * 0.62)
            rg.setColorAt(0.0, QColor(0, 0, 0, 80)); rg.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(rf, QBrush(rg))
            p.end()

        def _paint_sunrise(self, p, rf):
            W, H = rf.width(), rf.height()
            g = QLinearGradient(rf.topLeft(), rf.bottomLeft())
            g.setColorAt(0.0, QColor("#3a4a80")); g.setColorAt(0.45, QColor("#f0906a"))
            g.setColorAt(0.75, QColor("#ffb26b")); g.setColorAt(1.0, QColor("#ffd98a"))
            p.fillRect(rf, QBrush(g))
            cx, cy, r = rf.left() + W * 0.5, rf.bottom() - H * 0.05, H * 0.42
            glow = QRadialGradient(QPointF(cx, cy), r * 2.4)
            glow.setColorAt(0.0, QColor(255, 240, 200, 150)); glow.setColorAt(1.0, QColor(255, 240, 200, 0))
            p.setPen(Qt.NoPen); p.setBrush(QBrush(glow)); p.drawEllipse(QPointF(cx, cy), r * 2.4, r * 2.4)
            p.setBrush(QColor("#fff3c4")); p.drawEllipse(QPointF(cx, cy), r, r)

        def _paint_moon(self, p, rf):
            W, H = rf.width(), rf.height()
            g = QLinearGradient(rf.topLeft(), rf.bottomLeft())
            g.setColorAt(0.0, QColor("#0a0f26")); g.setColorAt(0.6, QColor("#182247"))
            g.setColorAt(1.0, QColor("#2a2f5c"))
            p.fillRect(rf, QBrush(g))
            rng = random.Random("beacon-stars")
            p.setPen(Qt.NoPen)
            for _ in range(48):
                x, y = rng.uniform(0, W), rng.uniform(0, H * 0.85)
                s = rng.choice([1, 1, 1.5, 2])
                p.setBrush(QColor(255, 255, 255, rng.randint(90, 210)))
                p.drawEllipse(QPointF(x, y), s, s)
            mx, my, mr = rf.right() - W * 0.18, rf.top() + H * 0.32, H * 0.24
            glow = QRadialGradient(QPointF(mx, my), mr * 2.2)
            glow.setColorAt(0.0, QColor(230, 235, 255, 120)); glow.setColorAt(1.0, QColor(230, 235, 255, 0))
            p.setBrush(QBrush(glow)); p.drawEllipse(QPointF(mx, my), mr * 2.2, mr * 2.2)
            p.setBrush(QColor("#eef1ff")); p.drawEllipse(QPointF(mx, my), mr, mr)
            p.setBrush(QColor("#182247"))   # crescent shadow
            p.drawEllipse(QPointF(mx + mr * 0.5, my - mr * 0.15), mr * 0.92, mr * 0.92)

        def _paint_design(self, p, rf):
            palette = CURRENT_DESIGN["palette"]; texture = CURRENT_DESIGN["texture"]
            cols = [QColor(c) for c in palette]
            grad = QLinearGradient(rf.topLeft(), rf.bottomRight())
            n = max(len(cols) - 1, 1)
            for i, c in enumerate(cols):
                grad.setColorAt(i / n, c)
            p.fillRect(rf, QBrush(grad))
            rng = random.Random("".join(palette) + texture)
            W, H = rf.width(), rf.height()
            white = lambda a: QColor(255, 255, 255, a)
            black = lambda a: QColor(0, 0, 0, a)
            p.setPen(Qt.NoPen)
            if texture == "blobs":
                for _ in range(7):
                    r = rng.randint(70, 190)
                    p.setBrush(white(rng.randint(10, 24)) if rng.random() < .6 else black(rng.randint(8, 18)))
                    p.drawEllipse(QPointF(rng.uniform(0, W), rng.uniform(0, H)), r, r)
            elif texture == "rings":
                p.setBrush(Qt.NoBrush)
                for _ in range(6):
                    cx, cy = rng.uniform(0, W), rng.uniform(0, H); r = rng.randint(40, 150)
                    p.setPen(QPen(white(rng.randint(14, 30)), 3)); p.drawEllipse(QPointF(cx, cy), r, r)
                p.setPen(Qt.NoPen)
            elif texture == "stripes":
                p.save(); p.translate(rf.topLeft()); p.rotate(-20)
                x = -H
                while x < W + H:
                    p.setBrush(white(rng.randint(8, 16)))
                    p.drawRect(QRectF(x, -H, 26, H * 3)); x += 60
                p.restore()
            elif texture == "dots":
                yy = 10
                while yy < H:
                    xx = 10
                    while xx < W:
                        p.setBrush(white(20)); p.drawEllipse(QPointF(xx, yy), 4, 4); xx += 46
                    yy += 46
            elif texture == "waves":
                p.setBrush(Qt.NoBrush)
                for k in range(4):
                    p.setPen(QPen(white(18), 3))
                    path = QPainterPath(); base = H * (0.25 + 0.2 * k); path.moveTo(0, base)
                    xx = 0
                    while xx <= W:
                        path.quadTo(xx + 30, base - 22, xx + 60, base); xx += 60
                    p.drawPath(path)
                p.setPen(Qt.NoPen)
            elif texture == "grid":
                p.setPen(QPen(white(16), 2))
                gx = 0
                while gx < W: p.drawLine(QPointF(gx, 0), QPointF(gx, H)); gx += 48
                gy = 0
                while gy < H: p.drawLine(QPointF(0, gy), QPointF(W, gy)); gy += 48
                p.setPen(Qt.NoPen)

    class FileTile(QWidget):
        def __init__(self, label, on_click, is_new=False, color=None, symbol=None):
            super().__init__()
            self.label = label; self.on_click = on_click; self.is_new = is_new
            self.color = color or CURRENT["ACCENT"]
            self.symbol = symbol or ""
            self._hover = False
            self.setFixedSize(150, 160)
            self.setCursor(Qt.PointingHandCursor)

        def enterEvent(self, e): self._hover = True; self.update()
        def leaveEvent(self, e): self._hover = False; self.update()
        def mousePressEvent(self, e):
            if self.on_click: self.on_click()

        def paintEvent(self, _):
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            col = QColor(self.color)
            text = QColor(CURRENT["TEXT"])
            fill = QColor(self.color); fill.setAlpha(70 if self._hover else 38)
            lines = QColor(self.color); lines.setAlpha(150)
            w = self.width()
            fw, fh = 74, 92
            x = (w - fw) / 2; y = 8
            fold = 22
            path = QPainterPath()
            path.moveTo(x, y)
            path.lineTo(x + fw - fold, y)
            path.lineTo(x + fw, y + fold)
            path.lineTo(x + fw, y + fh)
            path.lineTo(x, y + fh)
            path.closeSubpath()
            if self.is_new:
                pen = QPen(col); pen.setWidth(2); pen.setStyle(Qt.DashLine); p.setPen(pen)
                p.setBrush(QBrush(fill)); p.drawPath(path)
                p.setPen(QPen(col, 3))
                cx, cy = x + fw / 2, y + fh / 2
                p.drawLine(cx - 12, cy, cx + 12, cy)
                p.drawLine(cx, cy - 12, cx, cy + 12)
            else:
                pen = QPen(col); pen.setWidth(3 if self._hover else 2); p.setPen(pen)
                p.setBrush(QBrush(fill)); p.drawPath(path)
                # folded corner accent
                corner = QPainterPath()
                corner.moveTo(x + fw - fold, y)
                corner.lineTo(x + fw - fold, y + fold)
                corner.lineTo(x + fw, y + fold)
                p.setPen(QPen(col, 2)); p.setBrush(Qt.NoBrush); p.drawPath(corner)
                # each project's own symbol: its monogram
                p.setPen(QPen(col))
                mf = QFont("Segoe UI"); mf.setPointSize(20); mf.setBold(True); p.setFont(mf)
                p.drawText(QRectF(x, y + 22, fw, fh - 30), Qt.AlignCenter, self.symbol)
            # label
            p.setPen(QPen(text))
            f = QFont("Segoe UI"); f.setPointSize(9); f.setBold(True); p.setFont(f)
            name = self.label
            metrics = p.fontMetrics()
            name = metrics.elidedText(name, Qt.ElideRight, w - 8)
            p.drawText(QRectF(0, y + fh + 6, w, 24), Qt.AlignHCenter | Qt.AlignTop, name)
            p.end()

    # ---- onboarding ------------------------------------------------------
    class Onboarding(QDialog):
        def __init__(self, name="", role=ROLES[0], location=""):
            super().__init__()
            self.setWindowTitle("Beacon — Set up"); self.setMinimumWidth(480)
            self.name = name; self.role = role
            self.location = location or str(default_root())
            v = QVBoxLayout(self); v.setContentsMargins(30, 30, 30, 30); v.setSpacing(10)
            b = QLabel("◆ BEACON"); b.setObjectName("Brand")
            t = QLabel("Simplifying Overhead"); t.setObjectName("Muted")
            h1 = QLabel("Let's set you up"); h1.setObjectName("H1")
            self.name_in = QLineEdit(name); self.name_in.setPlaceholderText("Your name")
            self.role_in = QComboBox(); self.role_in.addItems(ROLES); self.role_in.setCurrentText(role)
            v.addWidget(b); v.addWidget(t); v.addWidget(h1)
            v.addWidget(QLabel("Name")); v.addWidget(self.name_in)
            v.addWidget(QLabel("Role")); v.addWidget(self.role_in)
            v.addWidget(QLabel("Beacon project location"))
            locrow = QHBoxLayout()
            self.loc_in = QLineEdit(self.location); self.loc_in.setPlaceholderText("Where projects & files are kept")
            browse = QPushButton("Browse…"); browse.clicked.connect(self._browse)
            locrow.addWidget(self.loc_in, 1); locrow.addWidget(browse)
            v.addLayout(locrow)
            go = QPushButton("Start"); go.setObjectName("primary"); go.clicked.connect(self._go)
            v.addWidget(go)

        def _browse(self):
            from PySide6.QtWidgets import QFileDialog
            d = QFileDialog.getExistingDirectory(self, "Choose Beacon project location", self.loc_in.text())
            if d:
                self.loc_in.setText(str(Path(d) / "Beacon"))

        def _go(self):
            if not self.name_in.text().strip():
                self.name_in.setPlaceholderText("Please enter your name"); return
            self.name = self.name_in.text().strip(); self.role = self.role_in.currentText()
            self.location = self.loc_in.text().strip() or str(default_root()); self.accept()

    # ---- project icon list: click=open, right-click=menu, drag-onto-other=swap ---
    class SwapListWidget(QListWidget):
        def __init__(self, on_open, on_menu, on_swap):
            super().__init__()
            self._on_open = on_open; self._on_menu = on_menu; self._on_swap = on_swap
            self._press_row = -1
            self.setViewMode(QListWidget.IconMode)
            self.setIconSize(QSize(96, 96))
            self.setGridSize(QSize(152, 150))
            self.setResizeMode(QListWidget.Adjust)
            self.setMovement(QListWidget.Static)      # icons stay in the grid
            self.setWrapping(True); self.setFlow(QListWidget.LeftToRight)
            self.setDragDropMode(QAbstractItemView.NoDragDrop)
            self.setDragEnabled(False)
            self.setSpacing(8); self.setWordWrap(True)
            self.setFrameShape(QFrame.NoFrame)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setSelectionMode(QAbstractItemView.SingleSelection)
            self.setObjectName("ProjCanvas")
            self.setContextMenuPolicy(Qt.DefaultContextMenu)

        def mousePressEvent(self, e):
            if e.button() == Qt.LeftButton:
                self._press_row = self.indexAt(e.pos()).row()
            super().mousePressEvent(e)

        def mouseReleaseEvent(self, e):
            up = self.indexAt(e.pos()).row()
            src = self._press_row
            super().mouseReleaseEvent(e)
            if e.button() != Qt.LeftButton or src < 0:
                return
            it = self.item(src)
            if it is None or it.data(Qt.UserRole) is None:
                return
            if up == src:
                self._on_open(it.data(Qt.UserRole))                     # left click -> open
            elif up >= 0 and self.item(up) and self.item(up).data(Qt.UserRole) is not None:
                self._on_swap(src, up)                                  # drag onto other -> swap

        def contextMenuEvent(self, e):
            row = self.indexAt(e.pos()).row()
            if row >= 0 and self.item(row) and self.item(row).data(Qt.UserRole) is not None:
                self._on_menu(row, e.globalPos())                       # right click -> menu

    # ---- remove confirmation (type the exact sentence) ------------------
    class RemoveConfirmDialog(QDialog):
        PHRASE = "I Agree to Remove"
        def __init__(self, project_name):
            super().__init__()
            self.setWindowTitle("Remove project"); self.setMinimumWidth(460)
            v = QVBoxLayout(self); v.setContentsMargins(24, 22, 24, 22); v.setSpacing(10)
            warn = QLabel(f"<b>“{project_name}” and all its contents will be deleted "
                          f"permanently.</b>")
            warn.setWordWrap(True); v.addWidget(warn)
            v.addWidget(QLabel(f'To confirm, type:  <b>{self.PHRASE}</b>'))
            self.entry = QLineEdit(); self.entry.setPlaceholderText(self.PHRASE)
            self.entry.textChanged.connect(self._check); v.addWidget(self.entry)
            row = QHBoxLayout(); row.addStretch(1)
            c = QPushButton("Cancel"); c.clicked.connect(self.reject)
            self.rm = QPushButton("Remove permanently"); self.rm.setObjectName("primary")
            self.rm.setEnabled(False); self.rm.clicked.connect(self.accept)
            row.addWidget(c); row.addWidget(self.rm); v.addLayout(row)

        def _check(self, txt):
            self.rm.setEnabled(txt.strip() == self.PHRASE)

    # ---- closed projects (Settings) -------------------------------------
    class ClosedProjectsDialog(QDialog):
        def __init__(self, conn, on_change):
            super().__init__()
            self.conn = conn; self.on_change = on_change
            self.setWindowTitle("Closed projects"); self.setMinimumWidth(440)
            v = QVBoxLayout(self); v.setContentsMargins(24, 22, 24, 22); v.setSpacing(10)
            v.addWidget(QLabel("<b>Closed projects</b>"))
            sub = QLabel("Closed projects are hidden from the canvas but keep their files.")
            sub.setObjectName("Muted"); sub.setWordWrap(True); v.addWidget(sub)
            self.lst = QListWidget(); v.addWidget(self.lst, 1)
            row = QHBoxLayout()
            reopen = QPushButton("Reopen selected"); reopen.setObjectName("primary")
            reopen.clicked.connect(self._reopen)
            close = QPushButton("Done"); close.clicked.connect(self.accept)
            row.addWidget(reopen); row.addStretch(1); row.addWidget(close)
            v.addLayout(row)
            self._reload()

        def _reload(self):
            from PySide6.QtWidgets import QListWidgetItem
            self.lst.clear()
            rows = list_closed_projects(self.conn)
            if not rows:
                self.lst.addItem("(none)")
                return
            for pid, name, _path in rows:
                it = QListWidgetItem(name); it.setData(Qt.UserRole, pid)
                self.lst.addItem(it)

        def _reopen(self):
            it = self.lst.currentItem()
            if not it or it.data(Qt.UserRole) is None:
                return
            set_project_closed(self.conn, it.data(Qt.UserRole), 0)
            self._reload(); self.on_change()

    # ---- winning certificate (levels 6 & 7) ------------------------------
    class CertificateDialog(QDialog):
        def __init__(self, player, level, score, when):
            super().__init__()
            self.player = player; self.level = level; self.score = score; self.when = when
            self.setWindowTitle("Certificate of Achievement")
            self.setMinimumSize(720, 520)
            v = QVBoxLayout(self); v.setContentsMargins(18, 18, 18, 18); v.setSpacing(12)
            self.card = self._Card(player, level, score, when)
            v.addWidget(self.card, 1)
            row = QHBoxLayout(); row.addStretch(1)
            png = QPushButton("Save as Image"); png.clicked.connect(lambda: self._save("png"))
            pdf = QPushButton("Save as PDF"); pdf.setObjectName("primary")
            pdf.clicked.connect(lambda: self._save("pdf"))
            close = QPushButton("Close"); close.clicked.connect(self.accept)
            for b_ in (png, pdf, close): row.addWidget(b_)
            v.addLayout(row)

        class _Card(QWidget):
            def __init__(self, player, level, score, when):
                super().__init__()
                self.player = player; self.level = level; self.score = score; self.when = when
                self.setMinimumSize(660, 420)

            def paintEvent(self, _):
                p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
                r = QRectF(self.rect()).adjusted(6, 6, -6, -6)
                g = QLinearGradient(r.topLeft(), r.bottomRight())
                g.setColorAt(0.0, QColor("#fffdf6")); g.setColorAt(1.0, QColor("#fdf3e3"))
                p.setPen(Qt.NoPen); p.setBrush(QBrush(g))
                p.drawRoundedRect(r, 14, 14)
                gold = QColor("#c9a227")
                p.setPen(QPen(gold, 5)); p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(r.adjusted(10, 10, -10, -10), 10, 10)
                p.setPen(QPen(QColor("#e0c975"), 1.5))
                p.drawRoundedRect(r.adjusted(20, 20, -20, -20), 8, 8)

                cx = r.center().x()
                def draw(text, y, size, color, bold=True, italic=False):
                    f = QFont("Georgia"); f.setPointSize(size); f.setBold(bold); f.setItalic(italic)
                    p.setFont(f); p.setPen(QColor(color))
                    p.drawText(QRectF(r.left(), y, r.width(), size * 2.4), Qt.AlignHCenter, text)

                draw("BEACON", r.top() + 36, 13, "#8a7a3d")
                draw("Certificate of Achievement", r.top() + 60, 22, "#1f2b45")
                p.setPen(QPen(gold, 2))
                p.drawLine(QPointF(cx - 110, r.top() + 112), QPointF(cx + 110, r.top() + 112))
                draw("This is proudly presented to", r.top() + 126, 11, "#6b7280", False, True)
                draw(self.player or "Player", r.top() + 152, 26, "#0f3d6e")
                draw(f"for clearing Level {self.level} of Catch the Colour",
                     r.top() + 202, 13, "#1f2b45", False)
                draw("— an extremely hard level —", r.top() + 226, 11, "#8a7a3d", False, True)
                draw(f"Score: {self.score}", r.top() + 254, 15, "#1f2b45")
                draw("Congratulations!", r.top() + 292, 20, "#0f7a4d")
                p.setPen(QPen(QColor("#c9a227"), 1))
                p.drawLine(QPointF(cx - 150, r.bottom() - 96), QPointF(cx + 150, r.bottom() - 96))
                draw(self.when, r.bottom() - 88, 11, "#6b7280", False)
                draw("BMS SW R&D", r.bottom() - 62, 10, "#9aa3b0", False)
                p.end()

        def _save(self, kind):
            base = f"Beacon_Certificate_L{self.level}_{safe_name(self.player) or 'player'}"
            if kind == "png":
                out, _ = QFileDialog.getSaveFileName(self, "Save certificate",
                                                     f"{base}.png", "PNG (*.png)")
                if not out:
                    return
                self.card.grab().save(out, "PNG")
            else:
                out, _ = QFileDialog.getSaveFileName(self, "Save certificate",
                                                     f"{base}.pdf", "PDF (*.pdf)")
                if not out:
                    return
                from PySide6.QtGui import QPdfWriter, QPageSize, QPageLayout
                from PySide6.QtCore import QMarginsF
                w = QPdfWriter(out); w.setPageSize(QPageSize(QPageSize.A4))
                w.setPageOrientation(QPageLayout.Landscape)
                w.setResolution(150)
                w.setPageMargins(QMarginsF(14, 14, 14, 14), QPageLayout.Millimeter)
                pm = self.card.grab()
                painter = QPainter(w)
                rect = painter.viewport()
                scaled = pm.scaled(rect.width(), rect.height(),
                                   Qt.KeepAspectRatio, Qt.SmoothTransformation)
                x = (rect.width() - scaled.width()) // 2
                y = (rect.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
                painter.end()

    # ---- Relax: Catch the Colour ----------------------------------------
    class GameCanvas(QWidget):
        def __init__(self, on_end, on_status):
            super().__init__()
            self.on_end = on_end; self.on_status = on_status
            self.setMinimumSize(700, 460)
            self.setFocusPolicy(Qt.StrongFocus)
            self.setMouseTracking(True)
            self.setCursor(Qt.OpenHandCursor)   # visible: you're holding the board
            self.level = 1
            self.reset_level(1)
            self.running = False
            self.elapsed_ms = 0
            self.played_ms = 0
            self.timer = QTimer(self)
            self.timer.timeout.connect(self._tick)

        # --- level lifecycle ---
        def reset_level(self, n):
            self.level = n
            self.cfg = level_config(n)
            self.pool = level_pool(self.cfg)
            self.spawn_ms = spawn_interval_ms(self.cfg)
            self.burst = spawn_burst(self.cfg)
            self.balls = []
            self.score = 0
            self.catches = 0
            self.misses = 0
            self.elapsed_ms = 0
            self.spawn_acc = 0
            self.swap_acc = 0
            self.board_w = self.cfg["board"]
            self.board_x = max(0, (self.width() - self.board_w) / 2)
            self.board_color = random.choice(BALL_COLORS[:self.cfg["colors"]])
            self.flash = None
            self.update()

        def start(self):
            self.running = True; self.setFocus(); self._sync_cursor(); self.timer.start(16)

        def stop(self):
            self.running = False; self.timer.stop()

        def resizeEvent(self, e):
            self.board_x = max(0, min(self.width() - self.board_w, self.board_x))
            super().resizeEvent(e)

        # --- input ---
        def _board_y(self):
            return self.height() - 42

        def _sync_cursor(self):
            """Keep the pointer on the board so it looks like you're holding it."""
            from PySide6.QtGui import QCursor
            y = int(self._board_y() + 8)
            x = int(self.board_x + self.board_w / 2)
            self._warping = True
            QCursor.setPos(self.mapToGlobal(QPoint(x, y)))
            self._warping = False

        def mouseMoveEvent(self, e):
            if getattr(self, "_warping", False):
                return
            self.board_x = max(0, min(self.width() - self.board_w,
                                      e.position().x() - self.board_w / 2))
            if self.running:
                self._sync_cursor()      # snap the hand back down onto the board
            self.update()

        def keyPressEvent(self, e):
            step = 42
            if e.key() == Qt.Key_Left:
                self.board_x = max(0, self.board_x - step)
            elif e.key() == Qt.Key_Right:
                self.board_x = min(self.width() - self.board_w, self.board_x + step)
            if self.running:
                self._sync_cursor()
            self.update()

        # --- loop ---
        def _tick(self):
            if not self.running:
                return
            dt_ms = 16
            self.elapsed_ms += dt_ms
            self.played_ms += dt_ms
            self.spawn_acc += dt_ms
            board_y = self._board_y()

            if self.spawn_acc >= self.spawn_ms and self.pool:
                self.spawn_acc = 0
                for _ in range(self.burst):
                    if not self.pool:
                        break
                    self.balls.append(new_ball(self.cfg, self.width(), color=self.pool.pop()))

            # levels 5-7 swap the board colour mid-play
            if self.cfg["swap_ms"]:
                self.swap_acc += dt_ms
                if self.swap_acc >= self.cfg["swap_ms"]:
                    self.swap_acc = 0
                    self.board_color = random.choice(BALL_COLORS[:self.cfg["colors"]])

            keep = []
            for b in self.balls:
                step_ball(b, self.cfg, self.width())
                if ball_caught(b, self.board_x, self.board_w, board_y):
                    pts = score_for(b["color"], self.board_color)
                    self.score += pts
                    if pts > 0:
                        self.catches += 1
                        self.flash = (f"+{pts}", "#2a9d8f")
                    else:
                        self.flash = (str(pts), "#e63946")
                    continue
                if b["y"] - b["r"] > self.height():
                    pen = score_for_miss(b["color"], self.board_color)
                    if pen:
                        self.misses += 1
                        self.score += pen
                        self.flash = (str(pen), "#f4a261")
                    continue
                keep.append(b)
            self.balls = keep

            if self.on_status:
                self.on_status(self.level, self.score, self.catches,
                               max(0, (LEVEL_SECONDS * 1000 - self.elapsed_ms) // 1000))

            if level_cleared(self.catches, self.score):
                self.stop(); self.on_end("cleared", self.level, self.score); return
            if self.elapsed_ms >= LEVEL_SECONDS * 1000 or (not self.pool and not self.balls):
                self.stop(); self.on_end("timeup", self.level, self.score); return
            self.update()

        # --- paint ---
        def paintEvent(self, _):
            p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
            r = self.rect()
            g = QLinearGradient(0, 0, 0, r.height())
            g.setColorAt(0.0, QColor("#0f1728")); g.setColorAt(1.0, QColor("#1b2740"))
            p.fillRect(r, QBrush(g))
            # balls
            for b in self.balls:
                col = QColor(b["color"])
                glow = QRadialGradient(QPointF(b["x"], b["y"]), b["r"] * 2.2)
                gc = QColor(col); gc.setAlpha(70)
                glow.setColorAt(0.0, gc); glow.setColorAt(1.0, QColor(0, 0, 0, 0))
                p.setPen(Qt.NoPen); p.setBrush(QBrush(glow))
                p.drawEllipse(QPointF(b["x"], b["y"]), b["r"] * 2.2, b["r"] * 2.2)
                p.setBrush(col); p.drawEllipse(QPointF(b["x"], b["y"]), b["r"], b["r"])
                p.setBrush(QColor(255, 255, 255, 90))
                p.drawEllipse(QPointF(b["x"] - b["r"] * .3, b["y"] - b["r"] * .35),
                              b["r"] * .34, b["r"] * .34)
            # board
            by = self._board_y()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 26))
            p.drawRoundedRect(QRectF(self.board_x - 3, by - 3, self.board_w + 6, 22), 11, 11)
            p.setBrush(QColor(self.board_color))
            p.drawRoundedRect(QRectF(self.board_x, by, self.board_w, 16), 8, 8)
            # target colour swatch + flash
            p.setBrush(QColor(self.board_color))
            p.drawEllipse(QRectF(14, 14, 18, 18))
            p.setPen(QColor("#c7d2e6"))
            f = QFont("Segoe UI"); f.setPointSize(10); f.setBold(True); p.setFont(f)
            p.drawText(QRectF(40, 12, 300, 22), Qt.AlignVCenter | Qt.AlignLeft,
                       "catch this colour")
            if self.flash:
                txt, col = self.flash
                p.setPen(QColor(col))
                f2 = QFont("Segoe UI"); f2.setPointSize(18); f2.setBold(True); p.setFont(f2)
                p.drawText(QRectF(self.board_x, by - 46, self.board_w, 30),
                           Qt.AlignCenter, txt)
            p.end()

    class RelaxDialog(QDialog):
        def __init__(self, conn):
            super().__init__()
            self.conn = conn
            self.setWindowTitle("Relax — Catch the Colour")
            self.setMinimumSize(760, 600)
            v = QVBoxLayout(self); v.setContentsMargins(18, 16, 18, 16); v.setSpacing(10)

            hud = QHBoxLayout()
            self.l_level = QLabel("Level 1"); self.l_level.setObjectName("CardTitle")
            self.l_score = QLabel("Score 0")
            self.l_catch = QLabel(f"Caught 0/{CLEAR_CATCHES}")
            self.l_time = QLabel(f"{LEVEL_SECONDS}s")
            self.l_budget = QLabel("")
            for x in (self.l_level, self.l_score, self.l_catch, self.l_time):
                hud.addWidget(x)
            hud.addStretch(1); hud.addWidget(self.l_budget)
            hud.addSpacing(14)
            # window controls, top-right
            self.min_btn = QPushButton("—"); self.min_btn.setFixedSize(30, 26)
            self.min_btn.setToolTip("Minimize"); self.min_btn.clicked.connect(self.showMinimized)
            self.max_btn = QPushButton("▢"); self.max_btn.setFixedSize(30, 26)
            self.max_btn.setToolTip("Maximize / Restore"); self.max_btn.clicked.connect(self._toggle_max)
            self.close_btn = QPushButton("✕"); self.close_btn.setFixedSize(30, 26)
            self.close_btn.setToolTip("Close"); self.close_btn.clicked.connect(self.close)
            for b_ in (self.min_btn, self.max_btn, self.close_btn):
                hud.addWidget(b_)
            v.addLayout(hud)

            self.canvas = GameCanvas(self._level_over, self._status)
            v.addWidget(self.canvas, 1)

            row = QHBoxLayout()
            self.msg = QLabel("Catch the balls matching the board's colour.  "
                              "Wrong colour: −5.  Move with the mouse or ← →.")
            self.msg.setObjectName("Muted"); self.msg.setWordWrap(True)
            row.addWidget(self.msg, 1)
            self.btn = QPushButton("Start"); self.btn.setObjectName("primary")
            self.btn.clicked.connect(self._start)
            quit_b = QPushButton("Close"); quit_b.clicked.connect(self.close)
            row.addWidget(self.btn); row.addWidget(quit_b)
            v.addLayout(row)

            self.budget_timer = QTimer(self)
            self.budget_timer.timeout.connect(self._check_budget)
            self.budget_timer.start(1000)
            self._played_flush = 0
            self._update_budget()

        def _toggle_max(self):
            if self.isMaximized() or self.isFullScreen():
                self.showNormal()
            else:
                self.showMaximized()

        def showEvent(self, e):
            """Open filling the monitor (Req: auto-fit to laptop screen)."""
            super().showEvent(e)
            if not getattr(self, "_sized", False):
                self._sized = True
                scr = self.screen() or QApplication.primaryScreen()
                if scr:
                    a = scr.availableGeometry()
                    self.resize(int(a.width() * 0.92), int(a.height() * 0.92))
                    self.move(a.center() - self.rect().center())
                self.showMaximized()

        def keyPressEvent(self, e):
            if e.key() == Qt.Key_Escape and (self.isMaximized() or self.isFullScreen()):
                self._toggle_max(); return
            if e.key() == Qt.Key_F11:
                self._toggle_max(); return
            super().keyPressEvent(e)

        # --- daily budget ---
        def _update_budget(self):
            left = relax_remaining(self.conn)
            self.l_budget.setText(f"Daily time left: {left // 60}:{left % 60:02d}")
            return left

        def _check_budget(self):
            if self.canvas.running:
                self._played_flush += 1
                if self._played_flush >= 5:            # persist every 5s
                    add_relax_seconds(self.conn, self._played_flush, self.canvas.level)
                    self._played_flush = 0
            left = self._update_budget()
            if left <= 0 and self.canvas.running:
                self.canvas.stop()
                self.btn.setEnabled(False)
                self.msg.setText("Daily 15 minutes are up — back to work. See you tomorrow!")

        def _start(self):
            if relax_remaining(self.conn) <= 0:
                self.msg.setText("Daily 15 minutes are up — back to work. See you tomorrow!")
                return
            lvl = self.canvas.level if self.canvas.level else 1
            self.canvas.reset_level(lvl)
            self.canvas.start()
            self.btn.setEnabled(False)
            self.msg.setText(f"Level {lvl} — {CLEAR_CATCHES} catches or {CLEAR_SCORE} points "
                             f"in {LEVEL_SECONDS}s.")

        def _status(self, level, score, catches, secs_left):
            self.l_level.setText(f"Level {level}")
            self.l_score.setText(f"Score {score}")
            self.l_catch.setText(f"Caught {catches}/{CLEAR_CATCHES}")
            self.l_time.setText(f"{secs_left}s")

        def _level_over(self, reason, level, score):
            add_relax_seconds(self.conn, self._played_flush, level); self._played_flush = 0
            self.btn.setEnabled(True)
            if reason == "cleared":
                if level >= len(GAME_LEVELS):
                    self.msg.setText(f"All {len(GAME_LEVELS)} levels cleared — outstanding! "
                                     f"Final score {score}.")
                    self.btn.setText("Play again"); self.canvas.level = 1
                else:
                    self.canvas.level = level + 1
                    self.msg.setText(f"Level {level} cleared with {score} points! "
                                     f"Next: level {self.canvas.level}"
                                     + ("  — brace yourself." if self.canvas.level >= 6 else "."))
                    self.btn.setText(f"Start level {self.canvas.level}")
                if level >= 6:                       # certificate for the hard levels
                    self._award_certificate(level, score)
            else:
                self.msg.setText(f"Time up on level {level} — {score} points. Try again.")
                self.btn.setText(f"Retry level {level}")

        def _award_certificate(self, level, score):
            prof = get_profile(self.conn)
            player = prof["name"] if prof else "Player"
            when = f"{fmt_date(datetime.now())} at {datetime.now().strftime('%I:%M %p').lstrip('0')}"
            CertificateDialog(player, level, score, when).exec()

        def closeEvent(self, e):
            if self._played_flush:
                add_relax_seconds(self.conn, self._played_flush, self.canvas.level)
                self._played_flush = 0
            self.canvas.stop(); self.budget_timer.stop()
            super().closeEvent(e)

    # ---- installed-app picker (searchable) ------------------------------
    class AppPickerDialog(QDialog):
        def __init__(self, apps, existing):
            super().__init__()
            self.setWindowTitle("Add Application"); self.setMinimumSize(520, 460)
            self.chosen = None; self.browse = False
            self._apps = [(n, t, k) for n, t, k in apps if n.lower() not in existing]
            v = QVBoxLayout(self); v.setContentsMargins(22, 20, 22, 20); v.setSpacing(10)
            v.addWidget(QLabel("<b>Installed applications on this laptop</b>"))
            sub = QLabel(f"{len(self._apps)} found. Type to search, then select one.")
            sub.setObjectName("Muted"); v.addWidget(sub)
            self.search = QLineEdit(); self.search.setPlaceholderText("Search applications…")
            self.search.textChanged.connect(self._filter)
            v.addWidget(self.search)
            self.list = QListWidget()
            self.list.itemDoubleClicked.connect(lambda _i: self._ok())
            v.addWidget(self.list, 1)
            row = QHBoxLayout()
            br = QPushButton("Browse for a file…"); br.clicked.connect(self._do_browse)
            row.addWidget(br); row.addStretch(1)
            c = QPushButton("Cancel"); c.clicked.connect(self.reject)
            a = QPushButton("Add"); a.setObjectName("primary"); a.clicked.connect(self._ok)
            row.addWidget(c); row.addWidget(a); v.addLayout(row)
            self._filter("")

        def _filter(self, text):
            from PySide6.QtWidgets import QListWidgetItem
            q = text.strip().lower()
            self.list.clear()
            for n, t, k in self._apps:
                if q and q not in n.lower():
                    continue
                it = QListWidgetItem(n); it.setData(Qt.UserRole, (n, t, k))
                it.setToolTip(t); self.list.addItem(it)
            if self.list.count():
                self.list.setCurrentRow(0)

        def _ok(self):
            it = self.list.currentItem()
            if it:
                self.chosen = it.data(Qt.UserRole); self.accept()

        def _do_browse(self):
            self.browse = True; self.accept()

    # ---- unassigned downloads (shown at startup) ------------------------
    class PendingDownloadsDialog(QDialog):
        def __init__(self, conn, on_file):
            super().__init__()
            self.conn = conn; self.on_file = on_file
            self.setWindowTitle("Unassigned downloads"); self.setMinimumWidth(560)
            v = QVBoxLayout(self); v.setContentsMargins(24, 22, 24, 22); v.setSpacing(10)
            v.addWidget(QLabel("<b>These downloaded files aren't in a project yet</b>"))
            sub = QLabel("Assign each to a project, or dismiss it.")
            sub.setObjectName("Muted"); v.addWidget(sub)
            self.table = QTableWidget(0, 3)
            self.table.setHorizontalHeaderLabels(["File", "Downloaded", "Action"])
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            v.addWidget(self.table, 1)
            row = QHBoxLayout(); row.addStretch(1)
            later = QPushButton("Later"); later.clicked.connect(self.accept)
            dismiss = QPushButton("Dismiss all"); dismiss.clicked.connect(self._dismiss_all)
            row.addWidget(dismiss); row.addWidget(later); v.addLayout(row)
            self._reload()

        def _reload(self):
            files = list_pending(self.conn)
            self.table.setRowCount(len(files))
            for i, f in enumerate(files):
                self.table.setItem(i, 0, QTableWidgetItem(f.name))
                try:
                    when = fmt_dt(datetime.fromtimestamp(f.stat().st_mtime))
                except OSError:
                    when = ""
                self.table.setItem(i, 1, QTableWidgetItem(when))
                btn = QPushButton("Assign Project…")
                btn.clicked.connect(lambda _=False, p=f: self._assign(p))
                self.table.setCellWidget(i, 2, btn)
            if not files:
                self.accept()

        def _assign(self, path):
            projects = [(p[0], p[1]) for p in list_projects(self.conn)]
            if not projects:
                QMessageBox.information(self, "Assign Project",
                                        "No projects yet — create one first."); return
            names = [n for _i, n in projects]
            name, ok = QInputDialog.getItem(self, "Assign Project",
                                            f"Put “{path.name}” into which project?",
                                            names, 0, False)
            if not ok:
                return
            pid = projects[names.index(name)][0]
            prow = self.conn.execute("SELECT path FROM projects WHERE id=?", (pid,)).fetchone()
            if not prow:
                return
            try:
                _d, dest = import_file(prow[0], str(path), move=True)
            except Exception as e:
                QMessageBox.warning(self, "Assign Project", f"Could not move the file:\n{e}"); return
            clear_pending(self.conn, path)
            if self.on_file:
                self.on_file()
            self._reload()

        def _dismiss_all(self):
            for f in list_pending(self.conn):
                dismiss_pending(self.conn, f)
            self.accept()

    # ---- new project (name + unique 3-char code) ------------------------
    class NewProjectDialog(QDialog):
        def __init__(self, conn):
            super().__init__()
            self.conn = conn; self.pname = ""; self.pcode = ""
            self.setWindowTitle("New Project"); self.setMinimumWidth(420)
            v = QVBoxLayout(self); v.setContentsMargins(24, 22, 24, 22); v.setSpacing(10)
            v.addWidget(QLabel("<b>Create a project</b>"))
            v.addWidget(QLabel("Name"))
            self.name_in = QLineEdit(); self.name_in.setPlaceholderText("Project name")
            self.name_in.textChanged.connect(self._suggest)
            v.addWidget(self.name_in)
            v.addWidget(QLabel("3-character code (unique ID)"))
            self.code_in = QLineEdit(); self.code_in.setMaxLength(3)
            self.code_in.setPlaceholderText("e.g. BMS")
            v.addWidget(self.code_in)
            self.err = QLabel(""); self.err.setObjectName("Muted"); v.addWidget(self.err)
            row = QHBoxLayout(); row.addStretch(1)
            c = QPushButton("Cancel"); c.clicked.connect(self.reject)
            ok = QPushButton("Create"); ok.setObjectName("primary"); ok.clicked.connect(self._ok)
            row.addWidget(c); row.addWidget(ok); v.addLayout(row)

        def _suggest(self, text):
            if not self.code_in.text().strip():
                self.code_in.setText(suggest_code(text))

        def _ok(self):
            name = self.name_in.text().strip()
            code = self.code_in.text().strip().upper()
            if not name:
                self.err.setText("Enter a project name."); return
            if len(code) != 3 or not code.isalnum():
                self.err.setText("Code must be exactly 3 letters/digits."); return
            if code_exists(self.conn, code):
                self.err.setText(f"Code '{code}' is already used — pick another."); return
            self.pname = name; self.pcode = code; self.accept()

    # ---- file-into-project prompt (download watcher) --------------------
    class FileIntoDialog(QDialog):
        def __init__(self, filename, projects):
            super().__init__()
            self.setWindowTitle("New file detected"); self.setMinimumWidth(440)
            self.project_id = None; self.keep_copy = False
            v = QVBoxLayout(self); v.setContentsMargins(24, 22, 24, 22); v.setSpacing(10)
            v.addWidget(QLabel("<b>A new file appeared</b>"))
            fn = QLabel(filename); fn.setObjectName("Muted"); fn.setWordWrap(True); v.addWidget(fn)
            v.addWidget(QLabel("File it into project:"))
            self.combo = QComboBox()
            self._ids = []
            for pid, name in projects:
                self.combo.addItem(name); self._ids.append(pid)
            v.addWidget(self.combo)
            self.keep = QCheckBox("Keep a copy in the source folder"); v.addWidget(self.keep)
            row = QHBoxLayout(); row.addStretch(1)
            ig = QPushButton("Ignore"); ig.clicked.connect(self.reject)
            ok = QPushButton("File it"); ok.setObjectName("primary"); ok.clicked.connect(self._ok)
            if not projects:
                ok.setEnabled(False); self.combo.addItem("(create a project first)")
            row.addWidget(ig); row.addWidget(ok); v.addLayout(row)

        def _ok(self):
            i = self.combo.currentIndex()
            if 0 <= i < len(self._ids):
                self.project_id = self._ids[i]
                self.keep_copy = self.keep.isChecked()
                self.accept()

    # ---- watched-folders settings ---------------------------------------
    class WatchFoldersDialog(QDialog):
        def __init__(self, conn):
            super().__init__()
            self.conn = conn
            self.setWindowTitle("Watched folders"); self.setMinimumWidth(440)
            v = QVBoxLayout(self); v.setContentsMargins(24, 22, 24, 22); v.setSpacing(8)
            v.addWidget(QLabel("<b>Watch these folders for new downloads</b>"))
            sub = QLabel("Beacon offers to file new files into a project.")
            sub.setObjectName("Muted"); v.addWidget(sub)
            self.checks = {}
            for key, label, getter, default in WATCH_DEFS:
                folder = getter()
                cb = QCheckBox(label + (f"   ({folder})" if folder else "   (not found)"))
                cb.setChecked(get_setting(conn, key, default) == "1")
                if not folder:
                    cb.setEnabled(False); cb.setChecked(False)
                v.addWidget(cb); self.checks[key] = cb
            row = QHBoxLayout(); row.addStretch(1)
            c = QPushButton("Cancel"); c.clicked.connect(self.reject)
            s = QPushButton("Save"); s.setObjectName("primary"); s.clicked.connect(self._save)
            row.addWidget(c); row.addWidget(s); v.addLayout(row)

        def _save(self):
            for key, cb in self.checks.items():
                set_setting(self.conn, key, "1" if cb.isChecked() else "0")
            self.accept()

    # ---- requirement editor ---------------------------------------------
    class ReqDialog(QDialog):
        def __init__(self, key, data=None):
            super().__init__()
            self.setWindowTitle(f"Requirement {key}"); self.setMinimumWidth(480)
            d = data or {}
            v = QVBoxLayout(self); v.setContentsMargins(24, 24, 24, 24); v.setSpacing(8)
            v.addWidget(QLabel(f"<b>{key}</b>"))
            self.title = QLineEdit(d.get("title", "")); self.title.setPlaceholderText("Title")
            self.desc = QPlainTextEdit(d.get("description", ""))
            self.desc.setPlaceholderText("Requirement text — 'The system shall …'")
            self.desc.setMinimumHeight(90)
            self.rtype = QComboBox(); self.rtype.addItems(REQ_TYPES)
            self.status = QComboBox(); self.status.addItems(REQ_STATUS)
            self.verify = QComboBox(); self.verify.addItems(VERIFY)
            self.assignee = QLineEdit(d.get("assignee", "")); self.assignee.setPlaceholderText("Assignee")
            if d.get("rtype") in REQ_TYPES: self.rtype.setCurrentText(d["rtype"])
            if d.get("status") in REQ_STATUS: self.status.setCurrentText(d["status"])
            if d.get("verification") in VERIFY: self.verify.setCurrentText(d["verification"])
            for lbl, w in [("Title", self.title), ("Description", self.desc), ("Type", self.rtype),
                           ("Status", self.status), ("Verification", self.verify), ("Assignee", self.assignee)]:
                v.addWidget(QLabel(lbl)); v.addWidget(w)
            row = QHBoxLayout(); row.addStretch(1)
            c = QPushButton("Cancel"); c.clicked.connect(self.reject)
            s = QPushButton("Save"); s.setObjectName("primary"); s.clicked.connect(self._ok)
            row.addWidget(c); row.addWidget(s); v.addLayout(row)

        def _ok(self):
            if not self.title.text().strip():
                self.title.setPlaceholderText("Title is required"); return
            self.result_data = {"title": self.title.text().strip(),
                                "description": self.desc.toPlainText().strip(),
                                "rtype": self.rtype.currentText(), "status": self.status.currentText(),
                                "verification": self.verify.currentText(),
                                "assignee": self.assignee.text().strip()}
            self.accept()

    # ---- main window -----------------------------------------------------
    class Home(QMainWindow):
        def __init__(self, conn, profile, app):
            super().__init__()
            self.conn = conn; self.profile = profile; self.app = app
            self.caps = caps_for(profile["role"]); self._req_ids = []
            self.setWindowTitle("Beacon — Simplifying Overhead")
            self.setMinimumSize(1060, 680)
            self._build_central()
            self._ui_index = LAUNCH_UI_INDEX
            self._ui_block = time_block()
            t = QTimer(self); t.timeout.connect(self._refresh_home); t.start(30_000)
            self._dialog_open = False
            self._watch_pending = {}
            self._start_watcher()
            self._alarm_timer = QTimer(self)
            self._alarm_timer.timeout.connect(self._check_reminders)
            self._alarm_timer.start(20_000)   # check plan reminders every 20s
            QTimer.singleShot(600, self._show_pending_downloads)

        def _show_pending_downloads(self):
            """On open: list downloads that aren't in a project yet (Req)."""
            cutoff = datetime.now().timestamp() - 14 * 24 * 3600      # last 14 days
            for folder in watched_folders(self.conn):
                try:
                    for f in folder.iterdir():
                        if not f.is_file() or f.suffix.lower() in TEMP_DOWNLOAD_EXT:
                            continue
                        try:
                            if f.stat().st_mtime < cutoff:
                                continue
                        except OSError:
                            continue
                        add_pending(self.conn, f)
                except OSError:
                    continue
            if not list_pending(self.conn):
                return
            self._dialog_open = True
            try:
                PendingDownloadsDialog(self.conn, self._reload_recent).exec()
            finally:
                self._dialog_open = False

        def _build_central(self):
            self.caps = caps_for(self.profile["role"])
            role = self.profile["role"]
            self.show_status = role in ("Head", "Program Manager", "Manager", "System Engineer")
            self.show_requirement = role != "Head"
            central = SoftBg(); self.central = central
            self.setCentralWidget(central)
            root = QVBoxLayout(central); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
            root.addWidget(self._build_topbar())
            self.stack = QStackedWidget(); root.addWidget(self.stack, 1)

            self.page_home = self._page_home();        self.stack.addWidget(self.page_home)
            self.page_detail = QWidget();              self.stack.addWidget(self.page_detail)
            self.page_notes = self._page_notes();      self.stack.addWidget(self.page_notes)
            if self.show_status:
                self.page_status = self._page_status();  self.stack.addWidget(self.page_status)
            if self.show_requirement:
                self.page_reqs = self._page_reqs();      self.stack.addWidget(self.page_reqs)
            self.page_links = self._page_links();      self.stack.addWidget(self.page_links)
            self.page_apps = self._page_apps();        self.stack.addWidget(self.page_apps)
            self.page_shots = self._page_shots();      self.stack.addWidget(self.page_shots)

            sb = self.statusBar()
            # remove any prior footer widgets on rebuild
            for attr in ("_foot_left", "_foot_right"):
                old = getattr(self, attr, None)
                if old is not None:
                    sb.removeWidget(old); old.deleteLater()
            self._foot_left = QLabel("Beacon developed by BMS R&D"); self._foot_left.setObjectName("Muted")
            self._foot_right = QLabel(
                '<a href="mailto:Sudhanshuk782@gmail.com" style="color:#6b7688;text-decoration:none;">'
                'Issue? Email to Sudhanshuk782@gmail.com</a>')
            self._foot_right.setObjectName("Muted"); self._foot_right.setOpenExternalLinks(True)
            sb.addWidget(self._foot_left)
            sb.addPermanentWidget(self._foot_right)
            self._nav("home")

        # top bar
        def _build_topbar(self):
            bar = QFrame(); bar.setObjectName("TopBar"); bar.setFixedHeight(56)
            h = QHBoxLayout(bar); h.setContentsMargins(20, 0, 16, 0); h.setSpacing(4)
            brand = QLabel("◆ BEACON"); brand.setObjectName("Brand"); h.addWidget(brand)
            h.addSpacing(24)
            self.nav_btns = {}
            nav = [("home", "Home"), ("notes", "Notes")]
            if self.show_status: nav.append(("status", "Status"))
            if self.show_requirement: nav.append(("reqs", "Requirement"))
            nav.append(("links", "Links"))
            nav.append(("apps", "Apps"))
            nav.append(("shots", "Screenshots"))
            for key, label in nav:
                b = QPushButton(label); b.setObjectName("navlink"); b.setCheckable(True)
                b.clicked.connect(lambda _, k=key: self._nav(k))
                h.addWidget(b); self.nav_btns[key] = b
            h.addStretch(1)
            gear = QPushButton("⚙  Settings"); gear.setObjectName("gear")
            menu = QMenu(gear)
            menu.addAction(QAction("Reset Profile (Name, Role)", self, triggered=self._reset_profile))
            menu.addAction(QAction("Change Project Location", self, triggered=self._change_location))
            menu.addAction(QAction("Closed Projects…", self, triggered=self._closed_projects))
            menu.addAction(QAction("Watched Folders…", self, triggered=self._watch_settings))
            menu.addSeparator()
            menu.addAction(QAction("Relax  🎮", self, triggered=self._open_relax))
            theme_menu = menu.addMenu("Change Theme")
            for tname in THEMES:
                theme_menu.addAction(QAction(tname, self, triggered=lambda _=False, n=tname: self._change_theme(n)))
            menu.addSeparator()
            menu.addAction(QAction("Help", self, triggered=self._help))
            gear.setMenu(menu)
            h.addWidget(gear)
            return bar

        def _nav(self, key):
            for k, b in self.nav_btns.items(): b.setChecked(k == key)
            if key == "home": self._refresh_home(); self.stack.setCurrentWidget(self.page_home)
            elif key == "notes": self._open_notes(); self.stack.setCurrentWidget(self.page_notes)
            elif key == "status": self._reload_status(); self.stack.setCurrentWidget(self.page_status)
            elif key == "reqs": self._reload_req_projects(); self.stack.setCurrentWidget(self.page_reqs)
            elif key == "links": self._reload_links(); self.stack.setCurrentWidget(self.page_links)
            elif key == "apps": self._reload_apps(); self.stack.setCurrentWidget(self.page_apps)
            elif key == "shots": self._reload_shots(); self.stack.setCurrentWidget(self.page_shots)

        # ---- settings actions ----
        def _reset_profile(self):
            if QMessageBox.question(self, "Reset Profile",
                    "Re-enter your name and role? Your projects are kept.") != QMessageBox.Yes:
                return
            dlg = Onboarding(self.profile["name"], self.profile["role"])
            if dlg.exec() != QDialog.Accepted:
                return
            save_profile(self.conn, dlg.name, dlg.role)
            self.profile = get_profile(self.conn)
            self._build_central()   # rebuild in place (nav/tabs follow new role)

        def _change_theme(self, name):
            set_setting(self.conn, "theme", name)
            apply_theme(self.app, name)          # live — restyles every widget now
            self.central.update()                # repaint the SoftBg backdrop
            self._refresh_tiles()                # repaint tiles with the new accent

        def _change_location(self):
            start = str(files_root())
            d = QFileDialog.getExistingDirectory(self, "Choose Beacon project location", start)
            if not d:
                return
            new_root = str(Path(d) / "Beacon") if Path(d).name.lower() != "beacon" else d
            set_setting(self.conn, "files_root", new_root)
            set_project_root(new_root)
            files_root()  # create the folder tree there
            self._build_central()
            self._start_watcher()
            QMessageBox.information(self, "Project location",
                f"New projects and filed downloads will be saved under:\n{new_root}\n\n"
                "Existing projects stay where they already are.")

        def _open_relax(self):
            left = relax_remaining(self.conn)
            if left <= 0:
                QMessageBox.information(
                    self, "Relax",
                    "You've used your 15 minutes of Relax today.\nIt resets tomorrow.")
                return
            self._dialog_open = True
            try:
                RelaxDialog(self.conn).exec()
            finally:
                self._dialog_open = False

        def _watch_settings(self):
            dlg = WatchFoldersDialog(self.conn)
            if dlg.exec() == QDialog.Accepted:
                self._start_watcher()   # apply the new folder set

        # ---- download watcher (Req1) ----
        def _start_watcher(self):
            if getattr(self, "_watch_timer", None):
                self._watch_timer.stop()
            self._watch_seen = {}
            for folder in watched_folders(self.conn):
                try:
                    self._watch_seen[str(folder)] = {p.name for p in folder.iterdir() if p.is_file()}
                except OSError:
                    self._watch_seen[str(folder)] = set()
            self._watch_timer = QTimer(self)
            self._watch_timer.timeout.connect(self._poll_downloads)
            self._watch_timer.start(5000)   # every 5s

        def _poll_downloads(self):
            if self._dialog_open:
                return
            for folder in watched_folders(self.conn):
                seen = self._watch_seen.setdefault(str(folder), set())
                try:
                    current = {p.name: p for p in folder.iterdir() if p.is_file()}
                except OSError:
                    continue
                for name in set(current) - seen:
                    p = current[name]
                    if p.suffix.lower() in TEMP_DOWNLOAD_EXT:
                        continue  # still downloading
                    try:
                        size = p.stat().st_size
                    except OSError:
                        continue
                    key = str(p)
                    if self._watch_pending.get(key) != size:
                        self._watch_pending[key] = size   # wait one cycle for it to settle
                        continue
                    seen.add(name); self._watch_pending.pop(key, None)
                    self._prompt_file(p)
                    return  # one at a time

        def _prompt_file(self, path):
            self._dialog_open = True
            try:
                projects = [(p[0], p[1]) for p in list_projects(self.conn)]
                dlg = FileIntoDialog(path.name, projects)
                if dlg.exec() == QDialog.Accepted and dlg.project_id is not None:
                    prow = self.conn.execute("SELECT path FROM projects WHERE id=?",
                                             (dlg.project_id,)).fetchone()
                    if prow:
                        try:
                            _d, dest = import_file(prow[0], str(path), move=not dlg.keep_copy)
                            clear_pending(self.conn, path)
                            self._reload_recent()
                            self.statusBar().showMessage(f"Filed {dest.name} into project.", 4000)
                        except Exception as e:
                            QMessageBox.warning(self, "Could not file", str(e))
                else:
                    add_pending(self.conn, path)   # remember it for the startup list
            finally:
                self._dialog_open = False

        def _help(self):
            QMessageBox.information(self, "Beacon — Help",
                "Beacon — offline engineering secretary.\n\n"
                "• Home: your greeting and projects (shown as file tiles). Click a tile to open it.\n"
                "• New tile (+): create a project; a folder tree is made under your Files root.\n"
                "• Files tab: import downloads (auto-sorted by format) and search by name/format/date.\n"
                "• Requirements: write and track requirements per project (role-dependent).\n"
                "• Settings ⚙: reset your profile, change theme, or open this help.\n\n"
                f"Database: {db_path()}\nFiles: {files_root()}")

        # ---- home page: hero (30%) + file tiles (65%) ----
        def _page_home(self):
            w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(28, 24, 28, 24); v.setSpacing(18)

            hero = HeroBanner()
            hv = QVBoxLayout(hero); hv.setContentsMargins(34, 24, 34, 24); hv.setSpacing(10)
            self.h_mono = QLabel(); self.h_mono.setObjectName("Mono")
            self.h_salute = QLabel(); self.h_salute.setObjectName("Salute")
            self.h_line = QLabel(); self.h_line.setObjectName("Line"); self.h_line.setWordWrap(True)
            for lbl in (self.h_mono, self.h_salute, self.h_line):
                lbl.setAlignment(Qt.AlignHCenter)
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            for lbl, blur in ((self.h_salute, 18), (self.h_line, 10), (self.h_mono, 8)):
                sh = QGraphicsDropShadowEffect(lbl)
                sh.setBlurRadius(blur); sh.setColor(QColor(0, 0, 0, 170)); sh.setOffset(0, 1)
                lbl.setGraphicsEffect(sh)
            hv.addStretch(1)
            hv.addWidget(self.h_mono)
            hv.addWidget(self.h_salute)
            hv.addWidget(self.h_line)
            hv.addStretch(1)
            v.addWidget(hero, 35)

            # ---- lower area: projects (70%) | right column (30%) ----
            lower_row = QHBoxLayout(); lower_row.setSpacing(16)

            # LEFT — projects as a reorderable icon list (70%)
            left = QVBoxLayout(); left.setSpacing(10)
            hrow = QHBoxLayout()
            sh = QLabel("PROJECTS"); sh.setObjectName("SectionH"); hrow.addWidget(sh)
            hrow.addStretch(1)
            newb = QPushButton("＋ New Project"); newb.setObjectName("primary")
            newb.clicked.connect(self._new_project); hrow.addWidget(newb)
            left.addLayout(hrow)

            self.proj_list = SwapListWidget(self._open_project, self._project_menu, self._swap_projects)
            left.addWidget(self.proj_list, 1)
            left_w = QWidget(); left_w.setLayout(left)
            lower_row.addWidget(left_w, 70)

            # RIGHT — Today's Plan (top) + Recent Files (bottom, larger)
            right = QVBoxLayout(); right.setSpacing(16)
            right.addWidget(self._build_plan_card(), 42)
            right.addWidget(self._build_recent_card(), 58)
            right_w = QWidget(); right_w.setLayout(right)
            lower_row.addWidget(right_w, 32)

            low_w = QWidget(); low_w.setLayout(lower_row)
            v.addWidget(low_w, 60)
            return w

        # ---- Today's Plan panel (editable; Enter adds a line; reminders) ----
        def _build_plan_card(self):
            card = QFrame(); card.setObjectName("Card")
            cv = QVBoxLayout(card); cv.setContentsMargins(16, 14, 16, 14); cv.setSpacing(8)
            head = QHBoxLayout()
            t = QLabel("TODAY'S PLAN"); t.setObjectName("CardTitle"); head.addWidget(t); head.addStretch(1)
            rem = QPushButton("⏰ Reminder"); rem.clicked.connect(self._set_plan_reminder)
            clr = QPushButton("Clear done"); clr.clicked.connect(self._clear_done_plan)
            head.addWidget(rem); head.addWidget(clr); cv.addLayout(head)
            self.plan_list = QListWidget()
            self.plan_list.setEditTriggers(
                QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked |
                QAbstractItemView.EditKeyPressed)
            self.plan_list.itemChanged.connect(self._plan_changed)
            cv.addWidget(self.plan_list, 1)
            self._reload_plan()
            return card

        def _today(self):
            from datetime import date as _d
            return _d.today().isoformat()

        def _plan_item(self, pid, text, done, remind):
            from PySide6.QtWidgets import QListWidgetItem
            label = text + (f"   ⏰ {remind}" if remind else "")
            it = QListWidgetItem(label if text else "")
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEditable)
            it.setCheckState(Qt.Checked if done else Qt.Unchecked)
            it.setData(Qt.UserRole, pid)          # plan id, or None for the new-row
            it.setData(Qt.UserRole + 1, remind)   # remind_time
            if done:                              # completed -> highlight the sentence
                it.setBackground(QColor(CURRENT["ACCENT"]))
                it.setForeground(QColor("#ffffff"))
                f = it.font()
                if f.pointSize() <= 0:
                    f.setPointSize(9)
                f.setBold(True); it.setFont(f)
            return it

        def _reload_plan(self):
            self.plan_list.blockSignals(True)
            self.plan_list.clear()
            for pid, text, done, remind in list_plan(self.conn, self._today()):
                self.plan_list.addItem(self._plan_item(pid, text, done, remind))
            self.plan_list.addItem(self._plan_item(None, "", False, None))  # trailing empty row
            self.plan_list.blockSignals(False)

        def _plan_changed(self, item):
            pid = item.data(Qt.UserRole)
            remind = item.data(Qt.UserRole + 1)
            # editing shows "text   ⏰ time"; recover the raw task text
            raw = item.text()
            if remind and raw.endswith(f"   ⏰ {remind}"):
                raw = raw[: -len(f"   ⏰ {remind}")]
            raw = raw.strip()
            done = item.checkState() == Qt.Checked
            if pid is None:
                if raw:
                    add_plan(self.conn, self._today(), raw)
                    self._reload_plan()
                    # jump to editing a fresh trailing row -> feels like a new line
                    last = self.plan_list.item(self.plan_list.count() - 1)
                    self.plan_list.setCurrentItem(last); self.plan_list.editItem(last)
            else:
                if raw == "":
                    delete_plan(self.conn, pid); self._reload_plan()
                else:
                    update_plan_text(self.conn, pid, raw)
                    set_plan_done(self.conn, pid, done)
                    self._reload_plan()

        def _set_plan_reminder(self):
            it = self.plan_list.currentItem()
            if not it or it.data(Qt.UserRole) is None:
                QMessageBox.information(self, "Reminder", "Select a task first."); return
            cur = it.data(Qt.UserRole + 1) or ""
            t, ok = QInputDialog.getText(self, "Set reminder", "Time (HH:MM, 24h):", text=cur)
            if not ok:
                return
            t = t.strip()
            if t and (len(t) != 5 or t[2] != ":" or not t.replace(":", "").isdigit()):
                QMessageBox.warning(self, "Reminder", "Use 24-hour HH:MM, e.g. 14:30."); return
            set_plan_reminder(self.conn, it.data(Qt.UserRole), t)
            self._reload_plan()

        def _clear_done_plan(self):
            clear_done_plan(self.conn, self._today()); self._reload_plan()

        def _play_alarm(self):
            """A soft flute-like phrase, ~8 seconds."""
            def ring():
                try:
                    if sys.platform.startswith("win"):
                        import winsound
                        # gentle flute-register phrase (C5–C6), totalling ~8 s
                        C5, D5, E5, G5, A5, C6 = 523, 587, 659, 784, 880, 1047
                        phrase = [
                            (G5, 450), (A5, 350), (C6, 600), (A5, 350), (G5, 500),
                            (E5, 400), (G5, 350), (A5, 450), (C6, 650),
                            (A5, 400), (G5, 450), (E5, 400), (D5, 400), (G5, 500),
                            (C5, 900), (E5, 400), (C5, 450),
                        ]
                        for freq, dur in phrase:
                            winsound.Beep(freq, dur)
                    else:
                        print("\a", end="", flush=True)
                except Exception:
                    pass
            import threading
            threading.Thread(target=ring, daemon=True).start()

        def _check_reminders(self):
            now_hhmm = datetime.now().strftime("%H:%M")
            due = due_plan_reminders(self.conn, self._today(), now_hhmm)
            for pid, text, rt in due:
                mark_plan_reminded(self.conn, pid)
                self._play_alarm()
                QMessageBox.information(self, "⏰ Reminder", f"{rt} — {text}")

        # ---- Recent Files panel (last opened; opens in the file's own app) ----
        def _build_recent_card(self):
            card = QFrame(); card.setObjectName("Card")
            cv = QVBoxLayout(card); cv.setContentsMargins(16, 14, 16, 14); cv.setSpacing(8)
            t = QLabel("RECENT FILES"); t.setObjectName("CardTitle"); cv.addWidget(t)
            self.recent_list = QListWidget()
            self.recent_list.setObjectName("RecentCanvas")
            self.recent_list.itemDoubleClicked.connect(self._open_recent)
            cv.addWidget(self.recent_list, 1)
            hint = QLabel("Double-click to open in its app."); hint.setObjectName("Muted"); cv.addWidget(hint)
            self._reload_recent()
            return card

        def _reload_recent(self):
            from PySide6.QtWidgets import QListWidgetItem
            self.recent_list.clear()
            LIMIT = 5
            files = list_recent_opens(self.conn, LIMIT)
            if len(files) < LIMIT:      # top up with recently-modified project files
                for f in recent_files(LIMIT * 3):
                    if f not in files:
                        files.append(f)
                    if len(files) >= LIMIT:
                        break
            files = files[:LIMIT]
            if not files:
                self.recent_list.addItem("(no files yet)")
                return
            for f in files:
                it = QListWidgetItem(f"{f.name}   ·   {f.parent.name}")
                it.setData(Qt.UserRole, str(f))
                self.recent_list.addItem(it)

        def _open_recent(self, item):
            path = item.data(Qt.UserRole)
            if not path:
                return
            self._open_file(Path(path))

        def _open_file(self, path):
            """Open a file in its associated app and log it to Recent Files."""
            path = Path(path)
            if not path.exists():
                QMessageBox.warning(self, "Open", f"File not found:\n{path}"); return
            record_open(self.conn, path)
            try:
                if sys.platform.startswith("win"):
                    os.startfile(str(path))          # noqa: Windows only
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(path)])
                else:
                    subprocess.Popen(["xdg-open", str(path)])
            except PermissionError as e:
                QMessageBox.warning(
                    self, "Open",
                    f"Windows refused to open:\n{path}\n\n"
                    "This usually means the file is blocked by policy or marked read-only.\n"
                    f"Opening its folder instead.\n\n({e})")
                open_in_explorer(path.parent)
            except OSError as e:
                QMessageBox.warning(self, "Open", f"Could not open:\n{path}\n\n({e})")
                open_in_explorer(path.parent)
            self._reload_recent()

        def _refresh_home(self):
            g = greeting(self.profile["name"])
            self._check_ui_rotation()
            self.h_mono.setText(f"{g['date_str']}   ·   {g['time_str']}")
            self.h_salute.setText(g["salute"])
            self.h_line.setText(CURRENT_PUNCH)
            self._refresh_tiles()
            self._reload_recent()

        def _check_ui_rotation(self):
            # advance the design + punchline when the 6-hour clock block changes
            blk = time_block()
            if getattr(self, "_ui_block", None) is None:
                self._ui_block = blk
                return
            if blk != self._ui_block:
                self._ui_block = blk
                self._ui_index = getattr(self, "_ui_index", 0) + 1
                apply_ui_rotation(self._ui_index)
                self.central.update()   # repaint hero + backdrop with new design

        # ---- Notes (rich text, purpose/place, grouped by date) ----
        def _note_template(self):
            today = fmt_date(datetime.now())
            return (
                "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
                "<td width='38%' align='left'><b>Purpose:</b> </td>"
                "<td width='32%' align='left'><b>Place:</b> </td>"
                f"<td width='30%' align='right'><b>Date:</b> {today}</td>"
                "</tr></table>"
                "<p><br></p>")

        def _page_notes(self):
            from PySide6.QtWidgets import (QTreeWidget, QTextEdit, QToolButton, QColorDialog)
            from PySide6.QtGui import QTextListFormat, QTextCharFormat
            w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(28, 24, 28, 24); v.setSpacing(10)
            top = QHBoxLayout()
            h = QLabel("Notes"); h.setObjectName("H1"); top.addWidget(h); top.addStretch(1)
            newb = QPushButton("＋ New Note"); newb.setObjectName("primary"); newb.clicked.connect(self._new_note)
            contb = QPushButton("↵ Continue"); contb.clicked.connect(self._continue_note)
            contb.setToolTip("Add another Purpose / Place / Date heading inside this note")
            saveb = QPushButton("Save"); saveb.clicked.connect(self._save_note)
            pdfb = QPushButton("Download PDF"); pdfb.clicked.connect(lambda: self._download_note("pdf"))
            docb = QPushButton("Download Word"); docb.clicked.connect(lambda: self._download_note("doc"))
            for b in (newb, contb, saveb, pdfb, docb): top.addWidget(b)
            v.addLayout(top)

            # formatting toolbar
            fmt_bar = QFrame(); fmt_bar.setObjectName("FmtBar")
            fmt = QHBoxLayout(fmt_bar); fmt.setContentsMargins(10, 6, 10, 6); fmt.setSpacing(6)
            self.note_edit = QTextEdit(); self.note_edit.setMinimumHeight(300)

            def mk(txt, fn, tip=""):
                bt = QToolButton(); bt.setText(txt); bt.setToolTip(tip or txt)
                bt.setObjectName("fmtbtn"); bt.setMinimumSize(34, 28)
                bt.clicked.connect(fn)
                return bt

            def sep():
                ln = QFrame(); ln.setFrameShape(QFrame.VLine)
                ln.setObjectName("FmtSep"); ln.setFixedHeight(24)
                return ln

            def toggle_bold():
                e = self.note_edit
                cf = QTextCharFormat()
                from PySide6.QtGui import QFont as _F
                cf.setFontWeight(_F.Normal if e.fontWeight() > _F.Normal else _F.Bold)
                e.mergeCurrentCharFormat(cf)

            def pick_color():
                c = QColorDialog.getColor()
                if c.isValid():
                    cf = QTextCharFormat(); cf.setForeground(c)
                    self.note_edit.mergeCurrentCharFormat(cf)

            def apply_list(style):
                cur = self.note_edit.textCursor()
                lf = QTextListFormat(); lf.setStyle(style); cur.createList(lf)

            lab = QLabel("Format"); lab.setObjectName("FmtLabel"); fmt.addWidget(lab)
            fmt.addWidget(sep())
            fmt.addWidget(mk("B", toggle_bold, "Bold"))
            fmt.addWidget(mk("A▾", pick_color, "Text colour"))
            fmt.addWidget(sep())
            lab2 = QLabel("Lists"); lab2.setObjectName("FmtLabel"); fmt.addWidget(lab2)
            fmt.addWidget(mk("•", lambda: apply_list(QTextListFormat.ListDisc), "Bullets"))
            fmt.addWidget(mk("1.", lambda: apply_list(QTextListFormat.ListDecimal), "Numbered 1, 2, 3"))
            fmt.addWidget(mk("a.", lambda: apply_list(QTextListFormat.ListLowerAlpha), "a, b, c"))
            fmt.addWidget(mk("A.", lambda: apply_list(QTextListFormat.ListUpperAlpha), "A, B, C"))
            fmt.addWidget(mk("i.", lambda: apply_list(QTextListFormat.ListLowerRoman), "i, ii, iii"))
            fmt.addWidget(mk("I.", lambda: apply_list(QTextListFormat.ListUpperRoman), "I, II, III"))
            fmt.addWidget(sep())
            fmt.addWidget(mk("⌫", lambda: apply_list(QTextListFormat.ListStyleUndefined),
                             "Remove list formatting"))
            fmt.addStretch(1)

            body = QHBoxLayout(); body.setSpacing(12)
            self.note_tree = QTreeWidget(); self.note_tree.setHeaderHidden(True)
            self.note_tree.setMaximumWidth(240)
            self.note_tree.itemClicked.connect(self._note_tree_click)
            body.addWidget(self.note_tree)
            right = QVBoxLayout(); right.addWidget(fmt_bar); right.addWidget(self.note_edit, 1)
            rw = QWidget(); rw.setLayout(right); body.addWidget(rw, 1)
            v.addLayout(body, 1)
            self._current_note_id = None
            return w

        def _open_notes(self):
            self._reload_note_tree()
            if self._current_note_id is None:
                self._new_note()

        def _new_note(self):
            self._current_note_id = None
            self.note_edit.setHtml(self._note_template())

        def _continue_note(self):
            """Append another dated Purpose/Place/Date section to this same note."""
            from PySide6.QtGui import QTextCursor
            cur = self.note_edit.textCursor()
            cur.movePosition(QTextCursor.End)
            self.note_edit.setTextCursor(cur)
            cur.insertHtml(
                "<p><br></p><hr>" + self._note_template())
            self.note_edit.setTextCursor(cur)
            self.note_edit.ensureCursorVisible()

        def _reload_note_tree(self):
            from PySide6.QtWidgets import QTreeWidgetItem
            self.note_tree.clear()
            for d in note_dates(self.conn):
                # d is ISO yyyy-mm-dd; show DD-Sept-YYYY
                try:
                    dt = datetime.strptime(d, "%Y-%m-%d")
                    label = fmt_date(dt)
                except ValueError:
                    label = d
                parent = QTreeWidgetItem([label]); parent.setData(0, Qt.UserRole, None)
                for nid, purpose in notes_for_date(self.conn, d):
                    child = QTreeWidgetItem([purpose.strip() or "(untitled)"])
                    child.setData(0, Qt.UserRole, nid)
                    parent.addChild(child)
                self.note_tree.addTopLevelItem(parent)

        def _note_tree_click(self, item, _col):
            nid = item.data(0, Qt.UserRole)
            if nid is None:
                item.setExpanded(not item.isExpanded()); return   # date header -> expand/collapse
            row = get_note_row(self.conn, nid)
            if not row:
                return
            self._current_note_id = nid
            self.note_edit.setHtml(row[4] or "")

        def _parse_note_fields(self):
            """Pull Purpose/Place from the note regardless of line/table layout."""
            import re
            text = self.note_edit.toPlainText()
            def grab(label, nxt):
                m = re.search(label + r"\s*:?\s*(.*)", text, re.IGNORECASE)
                if not m:
                    return ""
                val = m.group(1)
                # stop at the next label if it's on the same line
                if nxt:
                    val = re.split(nxt + r"\s*:", val, flags=re.IGNORECASE)[0]
                return val.splitlines()[0].strip() if val else ""
            purpose = grab("Purpose", "Place")
            place = grab("Place", "Date")
            return purpose or "(untitled)", place

        def _save_note(self):
            html = self.note_edit.toHtml()
            purpose, place = self._parse_note_fields()
            today = self._today()
            if self._current_note_id is None:
                self._current_note_id = add_note(self.conn, today, purpose, place, html)
            else:
                update_note(self.conn, self._current_note_id, purpose, place, html)
            self._reload_note_tree()
            self.statusBar().showMessage(f"Saved note ({fmt_date(datetime.now())}).", 3000)

        WATERMARK = "BMS SW R&amp;D"

        def _download_note(self, kind):
            html = self.note_edit.toHtml()
            purpose, _place = self._parse_note_fields()
            base = safe_name(purpose)[:30] or "note"
            footer = ("<hr style='border:none;border-top:1px solid #cccccc;margin-top:26px;'>"
                      "<p style='text-align:center;color:#9aa3b0;font-size:9pt;"
                      "letter-spacing:2px;'>" + self.WATERMARK + "</p>")
            if kind == "pdf":
                out, _ = QFileDialog.getSaveFileName(self, "Save PDF", f"{base}.pdf", "PDF (*.pdf)")
                if not out:
                    return
                from PySide6.QtGui import QTextDocument, QPdfWriter, QPageSize, QPageLayout, QFont
                from PySide6.QtCore import QMarginsF, QSizeF
                writer = QPdfWriter(out)
                writer.setPageSize(QPageSize(QPageSize.A4))
                writer.setResolution(96)
                writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Millimeter)
                doc = QTextDocument(); doc.setDefaultFont(QFont("Segoe UI", 11))
                doc.setHtml(html + footer)
                # size the document text area to the printable rect so content fits the page
                rect = writer.pageLayout().paintRectPixels(writer.resolution())
                doc.setPageSize(QSizeF(rect.width(), rect.height()))
                doc.print_(writer)
            else:
                out, _ = QFileDialog.getSaveFileName(self, "Save Word", f"{base}.doc", "Word (*.doc)")
                if not out:
                    return
                # Word opens HTML saved with a .doc extension
                with open(out, "w", encoding="utf-8") as f:
                    f.write("<html><head><meta charset='utf-8'></head><body>"
                            + html + footer + "</body></html>")
            self.statusBar().showMessage(f"Downloaded {Path(out).name}.", 4000)

        def _project_icon(self, code, color, faded=False):
            """An attractive rounded badge icon with the project's 3-char code."""
            from PySide6.QtGui import QPixmap, QIcon
            size = 96
            rad = int(size * 0.24)
            pm = QPixmap(size, size); pm.fill(Qt.transparent)
            p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
            r = QRectF(3, 3, size - 6, size - 6)
            path = QPainterPath(); path.addRoundedRect(r, rad, rad)
            base = QColor(color)
            grad = QLinearGradient(r.topLeft(), r.bottomRight())
            grad.setColorAt(0.0, base.lighter(118)); grad.setColorAt(1.0, base.darker(112))
            p.setPen(Qt.NoPen); p.setBrush(QBrush(grad)); p.drawPath(path)
            hp = QPainterPath(); hp.addRoundedRect(QRectF(3, 3, size - 6, (size - 6) / 2), rad, rad)
            p.setClipPath(path); p.setBrush(QColor(255, 255, 255, 34)); p.drawPath(hp)
            p.setClipping(False)
            p.setPen(QColor("#ffffff"))
            f = QFont("Segoe UI"); f.setPointSize(25); f.setBold(True); p.setFont(f)
            p.drawText(r, Qt.AlignCenter, code)
            if faded:
                p.setClipPath(path); p.fillRect(QRectF(0, 0, size, size), QColor(255, 255, 255, 165))
            p.end()
            return QIcon(pm)

        def _refresh_tiles(self):
            from PySide6.QtWidgets import QListWidgetItem
            self.proj_list.blockSignals(True)
            self.proj_list.clear()
            for p in list_projects(self.conn):
                pid, name = p[0], p[1]
                held = bool(p[8]) if len(p) > 8 else False
                code = project_code(p)
                color = TILE_COLORS[pid % len(TILE_COLORS)]
                shown = name if len(name) <= 15 else name[:14] + "…"   # Req5: max 15
                it = QListWidgetItem(self._project_icon(code, color, faded=held), shown)
                it.setData(Qt.UserRole, pid)
                it.setToolTip(name + ("  (on hold)" if held else ""))
                it.setTextAlignment(Qt.AlignHCenter)
                if held:
                    it.setForeground(QColor(CURRENT["MUTED"]))
                self.proj_list.addItem(it)
            self.proj_list.blockSignals(False)

        # ---- reorder (swap) + per-project menu ----
        def _swap_projects(self, src, tgt):
            ids = [self.proj_list.item(i).data(Qt.UserRole) for i in range(self.proj_list.count())]
            if not (0 <= src < len(ids) and 0 <= tgt < len(ids)):
                return
            ids[src], ids[tgt] = ids[tgt], ids[src]
            set_project_order(self.conn, ids)
            self._refresh_tiles()

        def _project_menu(self, row, gpos):
            it = self.proj_list.item(row)
            if not it:
                return
            pid = it.data(Qt.UserRole)
            r = self.conn.execute("SELECT held FROM projects WHERE id=?", (pid,)).fetchone()
            held = bool(r[0]) if r else False
            m = QMenu(self)
            a_hold = m.addAction("Resume" if held else "Pause")
            a_close = m.addAction("Close")
            m.addSeparator()
            a_remove = m.addAction("Remove…")
            act = m.exec(gpos)
            if act == a_hold:
                set_project_held(self.conn, pid, 0 if held else 1); self._refresh_tiles()
            elif act == a_close:
                set_project_closed(self.conn, pid, 1); self._refresh_tiles()
            elif act == a_remove:
                self._remove_project(pid)

        def _remove_project(self, pid):
            r = self.conn.execute("SELECT name FROM projects WHERE id=?", (pid,)).fetchone()
            if not r:
                return
            dlg = RemoveConfirmDialog(r[0])
            if dlg.exec() == QDialog.Accepted:
                delete_project(self.conn, pid)
                self._refresh_tiles(); self._reload_recent()
                self.statusBar().showMessage("Project removed.", 4000)

        def _closed_projects(self):
            dlg = ClosedProjectsDialog(self.conn, self._refresh_tiles)
            dlg.exec()

        # ---- projects (create + detail) ----
        def _new_project(self):
            dlg = NewProjectDialog(self.conn)
            if dlg.exec() != QDialog.Accepted:
                return
            pid = create_project(self.conn, dlg.pname, dlg.pcode, self.profile["name"])
            self._refresh_tiles(); self._open_project(pid)

        def _open_project(self, pid):
            p = self.conn.execute("SELECT id,name,path,status,owner,start_date,end_date "
                                  "FROM projects WHERE id=?", (pid,)).fetchone()
            if not p: return
            new = self._build_detail(p)
            idx = self.stack.indexOf(self.page_detail)
            self.stack.removeWidget(self.page_detail); self.page_detail.deleteLater()
            self.page_detail = new; self.stack.insertWidget(idx, self.page_detail)
            self.stack.setCurrentWidget(self.page_detail)

        def _build_detail(self, p):
            pid, name, path, status, owner, sd, ed = p
            w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(28, 22, 28, 22); v.setSpacing(12)
            top = QHBoxLayout()
            back = QPushButton("← Home"); back.clicked.connect(lambda: self._nav("home")); top.addWidget(back)
            h = QLabel(name); h.setObjectName("H1"); top.addWidget(h, 1)
            v.addLayout(top)
            # Files is the whole project page (Overview removed)
            v.addWidget(self._tab_files(pid, path), 1); return w

        def _tab_overview(self, p):
            pid, name, path, status, owner, sd, ed = p
            w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(18, 18, 18, 18); v.setSpacing(8)
            nreq = self.conn.execute("SELECT COUNT(*) FROM requirements WHERE project_id=?", (pid,)).fetchone()[0]
            code_row = self.conn.execute("SELECT code FROM projects WHERE id=?", (pid,)).fetchone()
            code = (code_row[0] if code_row else "") or ""
            nfiles = count_files(path) if Path(path).exists() else 0
            for k, val in [("Code", code), ("Owner", owner or "—"), ("Status", status or "Active"),
                           ("Requirements", str(nreq)), ("Files", str(nfiles)), ("Folder", path)]:
                r = QHBoxLayout(); kl = QLabel(k); kl.setObjectName("Muted"); kl.setFixedWidth(110)
                vl = QLabel(val); vl.setWordWrap(True); r.addWidget(kl); r.addWidget(vl, 1); v.addLayout(r)
            v.addStretch(1); return w

        def _tab_files(self, pid, path):
            from PySide6.QtWidgets import QListWidgetItem
            w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(18, 18, 18, 18); v.setSpacing(10)
            proot = Path(path)

            # --- mode switch: User (real folders) | Search (auto-sorted) ---
            mrow = QHBoxLayout()
            mlab = QLabel("View"); mlab.setObjectName("Muted"); mrow.addWidget(mlab)
            btn_user = QPushButton("👤  User"); btn_user.setCheckable(True)
            btn_srch = QPushButton("🔍  Search"); btn_srch.setCheckable(True)
            for b_ in (btn_user, btn_srch):
                b_.setObjectName("modebtn"); b_.setMinimumWidth(120)
                mrow.addWidget(b_)
            mode_hint = QLabel(""); mode_hint.setObjectName("Muted")
            mrow.addSpacing(10); mrow.addWidget(mode_hint); mrow.addStretch(1)
            openproj = QPushButton("📂  Open Project Folder")
            openproj.clicked.connect(lambda: open_in_explorer(proot))
            mrow.addWidget(openproj)
            v.addLayout(mrow)

            # --- actions row ---
            arow = QHBoxLayout()
            imp = QPushButton("＋ Import File"); imp.setObjectName("primary")
            hint = QLabel("Files are auto-sorted by type. Drag files onto the list to add them.")
            hint.setObjectName("Muted")
            arow.addWidget(imp); arow.addSpacing(8)
            arow.addWidget(hint); arow.addStretch(1)
            v.addLayout(arow)

            # --- search row (name + date; type is chosen in the sidebar) ---
            frow = QHBoxLayout()
            name_f = QLineEdit(); name_f.setPlaceholderText("File name contains…"); name_f.setMaximumWidth(240)
            cur_y = datetime.now().year
            year_f = QComboBox(); year_f.addItems(["All years"] + [str(y) for y in range(cur_y, cur_y - 7, -1)])
            month_f = QComboBox(); month_f.addItems(["All months"] + MONTHS)
            srch = QPushButton("Search"); clr = QPushButton("Clear")
            for label, wdg in [("Name", name_f), ("Year", year_f), ("Month", month_f)]:
                lab = QLabel(label); lab.setObjectName("Muted"); frow.addWidget(lab); frow.addWidget(wdg)
            frow.addWidget(srch); frow.addWidget(clr); frow.addStretch(1)
            v.addLayout(frow)

            # --- body: category sidebar (with counts) | results table ---
            body = QHBoxLayout(); body.setSpacing(12)
            cat_list = QListWidget(); cat_list.setMaximumWidth(190); cat_list.setObjectName("RecentCanvas")
            body.addWidget(cat_list)
            table = FileDropTable(0, 5)
            table.setHorizontalHeaderLabels(["Name", "Type", "Folder", "Modified", "Size"])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table._paths = {}
            body.addWidget(table, 1)

            # --- pages: 0 = User (real folders), 1 = Search (auto-sorted) ---
            search_page = QWidget(); search_page.setLayout(body)

            from PySide6.QtWidgets import QTreeView, QFileSystemModel
            user_page = QWidget(); up = QVBoxLayout(user_page)
            up.setContentsMargins(0, 0, 0, 0); up.setSpacing(8)
            uroot = user_dir(proot)                     # <project>/User — created on demand
            fs_model = QFileSystemModel()
            fs_model.setRootPath(str(uroot))
            fs_model.setReadOnly(True)                  # no accidental inline rename
            tree = QTreeView()
            tree.setModel(fs_model)
            tree.setRootIndex(fs_model.index(str(uroot)))
            tree.setColumnWidth(0, 320)
            tree.setSortingEnabled(True)
            tree.sortByColumn(0, Qt.AscendingOrder)
            tree.setAlternatingRowColors(False)
            tree.setSelectionBehavior(QAbstractItemView.SelectRows)
            tree.setAnimated(False)                     # snappier on network folders
            tree.setExpandsOnDoubleClick(False)         # single click already toggles
            tree.setItemsExpandable(True)
            tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
            tree.setContextMenuPolicy(Qt.CustomContextMenu)

            def tree_clicked(idx):
                """Single click on a folder opens (expands) it — no need to hit the arrow."""
                if not idx.isValid() or idx.column() != 0:
                    return
                if fs_model.isDir(idx):
                    tree.setExpanded(idx, not tree.isExpanded(idx))
            tree.clicked.connect(tree_clicked)
            up.addWidget(tree, 1)
            ubar = QHBoxLayout()
            nf = QPushButton("＋ New Folder"); nf.setObjectName("primary")
            addhere = QPushButton("Import Files")
            addfolder = QPushButton("Import Folder")
            openhere = QPushButton("Open in Explorer")
            ubar.addWidget(nf); ubar.addWidget(addhere)
            ubar.addWidget(addfolder); ubar.addWidget(openhere)
            uhint = QLabel("Your own folders, exactly as you saved them. "
                           "Double-click a file to open it.")
            uhint.setObjectName("Muted")
            ubar.addSpacing(8); ubar.addWidget(uhint); ubar.addStretch(1)
            up.addLayout(ubar)

            stack = QStackedWidget()
            stack.addWidget(user_page)      # index 0
            stack.addWidget(search_page)    # index 1
            v.addWidget(stack, 1)

            # ---- User-mode helpers ----
            def sel_dir():
                """The folder selected in the tree, defaulting to the User folder."""
                idx = tree.currentIndex()
                if not idx.isValid():
                    return uroot
                pth = Path(fs_model.filePath(idx))
                d = pth if pth.is_dir() else pth.parent
                # never allow imports to escape the User folder
                try:
                    d.relative_to(uroot)
                except ValueError:
                    return uroot
                return d

            def tree_open(idx):
                if not idx.isValid():
                    return
                pth = Path(fs_model.filePath(idx))
                if pth.is_file():
                    self._open_file(pth)
                elif pth.is_dir():
                    tree.setExpanded(idx, True)     # double-click a folder = open it
            tree.doubleClicked.connect(tree_open)

            def tree_menu(pos):
                idx = tree.indexAt(pos)
                if not idx.isValid():
                    return
                pth = Path(fs_model.filePath(idx))
                m = QMenu(self)
                a_open = m.addAction("Open")
                a_expl = m.addAction("Show in Explorer")
                m.addSeparator()
                a_ren = m.addAction("Rename…")
                a_del = m.addAction("Delete…")
                act = m.exec(tree.viewport().mapToGlobal(pos))
                if act == a_open:
                    tree_open(idx)
                elif act == a_expl:
                    open_in_explorer(pth if pth.is_dir() else pth.parent)
                elif act == a_ren:
                    new, ok = text_prompt(self, "Rename", "New name:", text=pth.name)
                    if ok and new.strip() and new.strip() != pth.name:
                        target = pth.parent / safe_name(new) if pth.is_dir() else \
                            pth.parent / new.strip()
                        if target.exists():
                            QMessageBox.information(self, "Rename",
                                                    "Something with that name already exists.")
                            return
                        try:
                            pth.rename(target)
                            cache["files"] = None
                        except OSError as e:
                            QMessageBox.warning(self, "Rename", f"Could not rename:\n{e}")
                elif act == a_del:
                    what = "folder and everything in it" if pth.is_dir() else "file"
                    if QMessageBox.question(
                            self, "Delete",
                            f"Delete this {what}?\n\n{pth.name}") != QMessageBox.Yes:
                        return
                    try:
                        if pth.is_dir():
                            shutil.rmtree(pth)
                        else:
                            pth.unlink()
                        cache["files"] = None
                    except OSError as e:
                        QMessageBox.warning(self, "Delete", f"Could not delete:\n{e}")
            tree.customContextMenuRequested.connect(tree_menu)

            def new_folder():
                base = sel_dir()
                name, ok = text_prompt(self, "New Folder", f"Folder name (inside {base.name}):")
                if not ok or not name.strip():
                    return
                target = base / safe_name(name)
                try:
                    target.mkdir(parents=True, exist_ok=False)
                except FileExistsError:
                    QMessageBox.information(self, "New Folder", "That folder already exists.")
                except OSError as e:
                    QMessageBox.warning(self, "New Folder", f"Could not create:\n{e}"); return
                tree.setCurrentIndex(fs_model.index(str(target)))
                tree.expand(fs_model.index(str(base)))
            nf.clicked.connect(new_folder)

            def import_here():
                base = sel_dir()
                srcs, _ = QFileDialog.getOpenFileNames(self, f"Copy into {base.name}",
                                                       str(downloads_dir()))
                for src in srcs:
                    if not src:
                        continue
                    try:
                        dest = base / Path(src).name
                        n = 2
                        while dest.exists():
                            dest = base / f"{Path(src).stem}_{n}{Path(src).suffix}"; n += 1
                        shutil.copy2(src, dest)
                    except Exception as e:
                        QMessageBox.warning(self, "Import", f"Could not copy {Path(src).name}:\n{e}")
                if srcs:
                    cache["files"] = None                # search index is stale now
                    tree.setCurrentIndex(fs_model.index(str(base)))
            addhere.clicked.connect(import_here)

            def import_folder():
                base = sel_dir()
                src = QFileDialog.getExistingDirectory(
                    self, "Choose a folder to copy in", str(downloads_dir()))
                if not src:
                    return
                srcp = Path(src)
                dest = base / srcp.name
                n = 2
                while dest.exists():
                    dest = base / f"{srcp.name}_{n}"; n += 1
                try:
                    shutil.copytree(srcp, dest)
                except Exception as e:
                    QMessageBox.warning(self, "Import Folder", f"Could not copy:\n{e}"); return
                cache["files"] = None                    # search index is stale now
                tree.setCurrentIndex(fs_model.index(str(dest)))
                tree.expand(fs_model.index(str(base)))
                self.statusBar().showMessage(
                    f"Copied “{srcp.name}” into {base.name}.", 4000)
            addfolder.clicked.connect(import_folder)
            openhere.clicked.connect(lambda: open_in_explorer(sel_dir()))

            # ---- mode switching ----
            def set_mode(user_mode):
                btn_user.setChecked(user_mode); btn_srch.setChecked(not user_mode)
                stack.setCurrentIndex(0 if user_mode else 1)
                if not user_mode and cache["files"] is None:
                    refresh_all()          # scan only when Search is actually opened
                # the actions row belongs to Search mode only
                imp.setVisible(not user_mode); hint.setVisible(not user_mode)
                for i in range(frow.count()):
                    it = frow.itemAt(i).widget()
                    if it:
                        it.setVisible(not user_mode)
                mode_hint.setText("Showing your folders as you saved them"
                                  if user_mode else "Auto-sorted by file type")
                set_setting(self.conn, f"files_mode_{pid}", "user" if user_mode else "search")
                if user_mode:
                    tree.setRootIndex(fs_model.index(str(proot)))
            btn_user.clicked.connect(lambda: set_mode(True))
            btn_srch.clicked.connect(lambda: set_mode(False))

            cache = {"files": None}

            def scan(force=False):
                """Cached scandir walk — one walk per refresh, not one per widget."""
                if cache["files"] is None or force:
                    cache["files"] = fast_scan(proot) if proot.exists() else []
                return cache["files"]

            def current_cat():
                it = cat_list.currentItem()
                return it.data(Qt.UserRole) if it else "__all__"

            def rebuild_sidebar(files):
                counts = {}
                for _f, _n, cat, _d, _s in files:
                    counts[cat] = counts.get(cat, 0) + 1
                prev = current_cat()
                cat_list.blockSignals(True); cat_list.clear()
                allit = QListWidgetItem(f"All  ({len(files)})"); allit.setData(Qt.UserRole, "__all__")
                cat_list.addItem(allit)
                for cat in CATEGORY_ORDER + [MISC]:
                    n = counts.get(cat, 0)
                    if n == 0:
                        continue
                    it = QListWidgetItem(f"{cat}  ({n})"); it.setData(Qt.UserRole, cat)
                    cat_list.addItem(it)
                # restore selection
                sel = 0
                for i in range(cat_list.count()):
                    if cat_list.item(i).data(Qt.UserRole) == prev:
                        sel = i; break
                cat_list.setCurrentRow(sel)
                cat_list.blockSignals(False)

            def refresh_table(files=None):
                if files is None:
                    files = scan()
                nm = name_f.text().strip().lower()
                yr = year_f.currentText(); mo = month_f.currentIndex(); cat = current_cat()
                data = []
                for f, name, c, dt, size in files:
                    if cat != "__all__" and c != cat: continue
                    if nm and nm not in name.lower(): continue
                    if yr != "All years" and dt.year != int(yr): continue
                    if mo > 0 and dt.month != mo: continue
                    data.append((f, name, c, dt, size))
                data.sort(key=lambda r: r[3], reverse=True)
                table._paths = {}
                if not data:
                    table.setRowCount(1)
                    table.setItem(0, 0, QTableWidgetItem("(no matching files)"))
                    for cc in range(1, 5): table.setItem(0, cc, QTableWidgetItem(""))
                    return
                table.setRowCount(len(data))
                for i, (f, name, c, dt, size) in enumerate(data):
                    table.setItem(i, 0, QTableWidgetItem(name))
                    table.setItem(i, 1, QTableWidgetItem(c))
                    table.setItem(i, 2, QTableWidgetItem(f.parent.name))
                    table.setItem(i, 3, QTableWidgetItem(fmt_dt(dt)))
                    table.setItem(i, 4, QTableWidgetItem(human_size(size)))
                    table._paths[i] = f

            def refresh_all():
                files = scan(force=True)      # single walk, reused by both widgets
                rebuild_sidebar(files); refresh_table(files)

            def do_import(srcs=None):
                if srcs is None:
                    srcs, _ = QFileDialog.getOpenFileNames(self, "Import file(s)", str(downloads_dir()))
                last_dir = None
                for src in srcs:
                    if not src: continue
                    try:
                        last_dir, _dest = import_file(proot, src)
                    except Exception as e:
                        QMessageBox.warning(self, "Import failed", str(e))
                if last_dir:
                    refresh_all(); open_in_explorer(last_dir)

            table._on_drop = do_import
            imp.clicked.connect(lambda: do_import())
            srch.clicked.connect(refresh_table)
            name_f.returnPressed.connect(refresh_table)
            cat_list.currentItemChanged.connect(lambda *_: refresh_table())
            def clear_filters():
                name_f.clear(); year_f.setCurrentIndex(0); month_f.setCurrentIndex(0)
                cat_list.setCurrentRow(0); refresh_table()
            clr.clicked.connect(clear_filters)
            table.cellDoubleClicked.connect(
                lambda r, _c: self._open_file(table._paths[r]) if r in table._paths else None)
            # NOTE: no scan here — set_mode() scans only if Search mode is opened,
            # so opening a project in User mode touches the disk barely at all.
            saved = get_setting(self.conn, f"files_mode_{pid}", "user")
            set_mode(saved != "search")
            return w

        def _tab_people(self, pid):
            w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(18, 18, 18, 18); v.setSpacing(10)
            table = QTableWidget(0, 2); table.setHorizontalHeaderLabels(["Name", "Role on project"])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)

            def refresh():
                rows = self.conn.execute("SELECT name, role FROM project_people WHERE project_id=? ORDER BY id",
                                         (pid,)).fetchall()
                table.setRowCount(len(rows))
                for i, (n, rr) in enumerate(rows):
                    table.setItem(i, 0, QTableWidgetItem(n)); table.setItem(i, 1, QTableWidgetItem(rr or ""))

            def add_person():
                name, ok = text_prompt(self, "Add person", "Name:")
                if not ok or not name.strip(): return
                prole, _ = text_prompt(self, "Add person", "Role on project:")
                self.conn.execute("INSERT INTO project_people (project_id,name,role,added_at) VALUES (?,?,?,?)",
                                  (pid, name.strip(), (prole or "").strip(),
                                   datetime.now().isoformat(timespec="seconds")))
                self.conn.commit(); refresh()

            def remove_person():
                r = table.currentRow()
                if r < 0: return
                nm = table.item(r, 0).text()
                self.conn.execute("DELETE FROM project_people WHERE id IN "
                                  "(SELECT id FROM project_people WHERE project_id=? AND name=? LIMIT 1)",
                                  (pid, nm)); self.conn.commit(); refresh()

            row = QHBoxLayout()
            a = QPushButton("＋ Add Person"); a.setObjectName("primary"); a.clicked.connect(add_person)
            d = QPushButton("Remove Selected"); d.clicked.connect(remove_person)
            row.addWidget(a); row.addWidget(d); row.addStretch(1)
            v.addLayout(row); v.addWidget(table, 1); refresh(); return w

        def _tab_timeline(self, pid, sd, ed):
            w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(18, 18, 18, 18); v.setSpacing(12)
            row = QHBoxLayout()
            start = QDateEdit(); start.setCalendarPopup(True); end = QDateEdit(); end.setCalendarPopup(True)
            start.setDate(QDate.fromString(sd, "yyyy-MM-dd") if sd else QDate.currentDate())
            end.setDate(QDate.fromString(ed, "yyyy-MM-dd") if ed else QDate.currentDate().addMonths(3))
            save = QPushButton("Save Timeline"); save.setObjectName("primary")

            def do_save():
                self.conn.execute("UPDATE projects SET start_date=?, end_date=? WHERE id=?",
                                  (start.date().toString("yyyy-MM-dd"), end.date().toString("yyyy-MM-dd"), pid))
                self.conn.commit(); self.statusBar().showMessage("Timeline saved.", 3000)
            save.clicked.connect(do_save)
            row.addWidget(QLabel("Start")); row.addWidget(start); row.addWidget(QLabel("End"))
            row.addWidget(end); row.addWidget(save); row.addStretch(1); v.addLayout(row)
            v.addWidget(QLabel("Milestones"))
            table = QTableWidget(0, 2); table.setHorizontalHeaderLabels(["Milestone", "Due"])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)

            def refresh():
                rows = self.conn.execute("SELECT title, due_date FROM milestones WHERE project_id=? ORDER BY due_date",
                                         (pid,)).fetchall()
                table.setRowCount(len(rows))
                for i, (t, dd) in enumerate(rows):
                    table.setItem(i, 0, QTableWidgetItem(t)); table.setItem(i, 1, QTableWidgetItem(dd or ""))

            def add_ms():
                title, ok = text_prompt(self, "Milestone", "Milestone title:")
                if not ok or not title.strip(): return
                due, _ = text_prompt(self, "Milestone", "Due (yyyy-mm-dd):")
                self.conn.execute("INSERT INTO milestones (project_id,title,due_date) VALUES (?,?,?)",
                                  (pid, title.strip(), (due or "").strip())); self.conn.commit(); refresh()

            add = QPushButton("＋ Add Milestone"); add.clicked.connect(add_ms)
            v.addWidget(add); v.addWidget(table, 1); refresh(); return w

        # ---- Status: Head (project level) -> drill down to Manager level ----
        def _page_status(self):
            w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(28, 18, 28, 18); v.setSpacing(10)
            top = QHBoxLayout()
            self.status_title = QLabel("Status — Projects"); self.status_title.setObjectName("H1")
            top.addWidget(self.status_title)
            self.status_back = QPushButton("← All projects")
            self.status_back.clicked.connect(lambda: self._show_status_level(None))
            self.status_back.setVisible(False); top.addWidget(self.status_back)
            top.addStretch(1)
            role = self.profile["role"]
            self.is_head_role = (role == "Head")
            if self.is_head_role:
                mkh = QPushButton("Create Head Excel…"); mkh.clicked.connect(self._make_head_workbook)
                top.addWidget(mkh)
            else:
                mkm = QPushButton("Create Manager Excel…")
                mkm.clicked.connect(self._make_manager_workbook)
                lnk = QPushButton("Link Manager Excel…"); lnk.clicked.connect(self._link_team_excel)
                top.addWidget(mkm); top.addWidget(lnk)
            rf = QPushButton("Refresh"); rf.setObjectName("primary"); rf.clicked.connect(self._reload_status)
            top.addWidget(rf)
            v.addLayout(top)

            self.status_table = QTableWidget(0, 5)
            self.status_table.setHorizontalHeaderLabels(
                ["Code", "Project", "State", "Completion %", "Data as of"])
            self.status_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.status_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.status_table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.status_table.setMaximumHeight(190)
            v.addWidget(self.status_table)

            charts = QHBoxLayout(); charts.setSpacing(14)
            pie_card = QFrame(); pie_card.setObjectName("Card")
            pl = QVBoxLayout(pie_card); pl.setContentsMargins(14, 12, 14, 12)
            self.pie_title = QLabel("SHARE OF COMPLETION"); self.pie_title.setObjectName("CardTitle")
            pl.addWidget(self.pie_title)
            self.status_pie = PieChart(); pl.addWidget(self.status_pie, 1)
            bar_card = QFrame(); bar_card.setObjectName("Card")
            bl = QVBoxLayout(bar_card); bl.setContentsMargins(14, 12, 14, 12)
            self.bar_title = QLabel("COMPLETION BY PROJECT  (click a bar to drill down)")
            self.bar_title.setObjectName("CardTitle"); bl.addWidget(self.bar_title)
            self.status_bar = BarChart(on_click=self._bar_clicked); bl.addWidget(self.status_bar, 1)
            charts.addWidget(pie_card, 1); charts.addWidget(bar_card, 1)
            v.addLayout(charts, 1)

            self.status_note = QLabel(""); self.status_note.setObjectName("Muted")
            self.status_note.setWordWrap(True); v.addWidget(self.status_note)
            self._drill_pid = None
            self._bar_pids = []
            return w

        def _show_status_level(self, pid):
            self._drill_pid = pid
            self.status_back.setVisible(pid is not None)
            self._reload_status()

        def _bar_clicked(self, index):
            if self._drill_pid is not None:
                return                                  # already at manager level
            if 0 <= index < len(self._bar_pids):
                self._show_status_level(self._bar_pids[index])

        def _reload_status(self):
            if self._drill_pid is not None:
                self._reload_status_managers(self._drill_pid)
            else:
                self._reload_status_projects()

        def _reload_status_projects(self):
            self.status_title.setText("Status — Projects")
            self.bar_title.setText("COMPLETION BY PROJECT  (click a bar to drill down)")
            self.pie_title.setText("SHARE OF COMPLETION")
            self.status_table.setHorizontalHeaderLabels(
                ["Code", "Project", "State", "Completion %", "Data as of"])
            self._status_ids = []; self._bar_pids = []
            rows = list_projects(self.conn)          # closed/removed excluded
            self.status_table.setRowCount(len(rows))
            pie_data, bar_data, problems = [], [], []
            sources = []
            for i, p in enumerate(rows):
                pid, name = p[0], p[1]
                held = bool(p[8]) if len(p) > 8 else False
                self._status_ids.append(pid)
                res = compute_project_status(self.conn, pid)
                sources.append(res.get("source"))
                pct = res["percent"] if res["ok"] else None
                asof = fmt_dt(res["modified"]) if res.get("modified") else "—"
                for msg in res["problems"]:
                    problems.append(f"{name}: {msg}")
                state = "Paused" if held else (p[3] or "Active")
                cells = [project_code(p), name, state,
                         (f"{pct:.1f}" if pct is not None else "—"), asof]
                for j, val in enumerate(cells):
                    it = QTableWidgetItem(val)
                    if held:
                        it.setForeground(QColor(CURRENT["MUTED"]))
                    self.status_table.setItem(i, j, it)
                if pct is not None:
                    col = TILE_COLORS[pid % len(TILE_COLORS)]
                    label = name + (" (paused)" if held else "")
                    bar_data.append((label, pct, col)); self._bar_pids.append(pid)
                    if not held:
                        pie_data.append((name, pct, col))
            self.status_pie.set_data(pie_data)
            self.status_bar.set_data(bar_data)
            srcs = {s for s in sources if s and s != "none"}
            src_note = (f"Source: {', '.join(sorted(srcs))}.  " if srcs else "")
            self.status_note.setText(
                src_note + (("⚠  " + "   |   ".join(problems[:3])) if problems
                            else "All Head workbooks read successfully."))

        def _reload_status_managers(self, pid):
            row = self.conn.execute("SELECT name FROM projects WHERE id=?", (pid,)).fetchone()
            pname = row[0] if row else "Project"
            self.status_title.setText(f"Status — {pname} (managers)")
            self.bar_title.setText("COMPLETION BY MANAGER")
            self.pie_title.setText("WEIGHTED SHARE")
            self.status_table.setHorizontalHeaderLabels(
                ["Manager", "Team Excel", "Sheet", "Status %", "Normalization"])
            res = compute_project_status(self.conn, pid)
            links = list_manager_links(self.conn, pid)
            self.status_table.setRowCount(len(links))
            bar_data, pie_data = [], []
            for i, (_lid, mgr, wbk, sheet, weight) in enumerate(links):
                pct = None
                for m, pp, _wt in res["managers"]:
                    if m == mgr:
                        pct = pp; break
                cells = [mgr, (Path(wbk).name if wbk else "— not linked —"), sheet or "—",
                         (f"{pct:.1f}" if pct is not None else "—"), f"{float(weight or 0):.2f}"]
                for j, val in enumerate(cells):
                    self.status_table.setItem(i, j, QTableWidgetItem(val))
                col = TILE_COLORS[(i + 1) % len(TILE_COLORS)]
                if pct is not None:
                    bar_data.append((mgr, pct, col))
                    pie_data.append((mgr, pct * float(weight or 0), col))
            self.status_bar.set_data(bar_data); self.status_pie.set_data(pie_data)
            note = f"Project total: {res['percent'] if res['ok'] else '—'}%   ·   " \
                   f"weights total {res['weight_sum']}   ·   source: {res.get('source', '—')}"
            if res["problems"]:
                note += "    ⚠  " + "   |   ".join(res["problems"][:2])
            self.status_note.setText(note)

        def _selected_status_project(self):
            r = self.status_table.currentRow()
            if self._drill_pid is not None:
                pid = self._drill_pid
            elif 0 <= r < len(self._status_ids):
                pid = self._status_ids[r]
            else:
                return None
            return self.conn.execute("SELECT id,name,path FROM projects WHERE id=?", (pid,)).fetchone()

        def _make_head_workbook(self):
            row = self._selected_status_project()
            if not row:
                QMessageBox.information(self, "Head Excel", "Select a project row first."); return
            pid, name, path = row
            existing = [m for _i, m, _w, _s, _wt in list_manager_links(self.conn, pid)]
            txt, ok = QInputDialog.getText(self, "Managers", "Manager names (comma separated):",
                                           text=", ".join(existing) if existing else
                                           "Manager A, Manager B, Manager C")
            if not ok:
                return
            managers = [m.strip() for m in txt.split(",") if m.strip()]
            if not managers:
                return
            out = head_workbook_path(path, name)
            blocked = workbook_blocked_reason(out)
            if blocked:
                QMessageBox.warning(self, "Head Excel", blocked); return
            try:
                created = create_head_workbook(path, name, managers)
            except Exception as e:
                QMessageBox.warning(self, "Head Excel", f"Could not create:\n{e}"); return
            set_managers(self.conn, pid, managers)
            # re-apply any links that already existed
            for _lid, mgr, wbk, sheet, _wt in list_manager_links(self.conn, pid):
                if wbk and sheet:
                    link_manager_in_head(created, mgr, wbk, sheet)
            self._reload_status()
            QMessageBox.information(
                self, "Head Excel",
                f"Created:\n{created}\n\nOnly the Normalization column is editable. "
                "Set each manager's weight so the total is 1.00.")
            self._open_file(created)

        def _make_manager_workbook(self):
            """One workbook per manager covering every project listed in Beacon."""
            projects = [p[1] for p in list_projects(self.conn)]
            if not projects:
                QMessageBox.information(self, "Manager Excel",
                                        "No projects yet — create a project first."); return
            default = self.profile["name"]
            mgr, ok = text_prompt(self, "Manager Excel", "Manager name:", text=default)
            if not ok or not mgr.strip():
                return
            mgr = mgr.strip()
            out = manager_workbook_path(mgr)
            if out.exists():
                if QMessageBox.question(
                        self, "Manager Excel",
                        f"{out.name} already exists.\nRecreate it? Entered data will be lost."
                ) != QMessageBox.Yes:
                    return
            blocked = workbook_blocked_reason(out)
            if blocked:
                QMessageBox.warning(self, "Manager Excel", blocked); return
            try:
                created = create_manager_workbook(mgr, projects)
            except Exception as e:
                QMessageBox.warning(self, "Manager Excel", f"Could not create:\n{e}"); return
            QMessageBox.information(
                self, "Manager Excel",
                f"Created:\n{created}\n\nOne sheet per project ({len(projects)}), plus a "
                f"Summary that auto-calculates each project's status and cannot be edited "
                f"directly.\n\nNow use “Link Team Excel…” to connect it to each project's "
                f"Head Excel.")
            self._open_file(created)

        def _link_team_excel(self):
            row = self._selected_status_project()
            if not row:
                QMessageBox.information(self, "Link", "Select a project row first."); return
            pid, name, path = row
            links = list_manager_links(self.conn, pid)
            if not links:
                QMessageBox.information(self, "Link", "The Head Excel for this project "
                                                      "hasn't been created yet."); return
            names = [m for _i, m, _w, _s, _wt in links]
            mgr, ok = QInputDialog.getItem(self, "Link Manager Excel",
                                           "Which manager's workbook?", names, 0, False)
            if not ok:
                return
            guess = manager_workbook_path(mgr)
            start_dir = str(guess.parent) if guess.parent.exists() else str(files_root())
            wbk, _ = QFileDialog.getOpenFileName(
                self, f"Select {mgr}'s Manager Excel", start_dir, "Excel (*.xlsx *.xlsm)")
            if not wbk:
                return
            srow = manager_summary_row(wbk, name)
            if srow is None:
                QMessageBox.warning(
                    self, "Link",
                    f"“{name}” isn't listed in that workbook's {STATUS_SHEET} sheet.\n\n"
                    "Recreate the Manager Excel so it includes this project.")
                return
            lid = [i for i, m, _w, _s, _wt in links if m == mgr][0]
            set_manager_link(self.conn, lid, wbk, name)
            head = head_workbook_path(path, name)
            linked = link_manager_in_head(head, mgr, wbk, name) if head.exists() else False
            chk = read_manager_status(wbk, name)
            self._reload_status()
            msg = f"Linked {mgr} → {Path(wbk).name}\n{STATUS_SHEET} row {srow} (“{name}”)"
            if not head.exists():
                msg += "\n\nNote: this project has no Head Excel yet."
            elif not linked:
                msg += "\n\nNote: could not write the link into the Head Excel."
            if chk.get("ok"):
                msg += f"\n\nCurrent status: {chk['percent']:.1f}%"
            else:
                msg += f"\n\nNote: {chk.get('error')}"
            QMessageBox.information(self, "Link", msg)

        # ---- Links (all roles) ----
        EMPTY_LINK_ROWS = 4

        def _page_links(self):
            from PySide6.QtWidgets import QHeaderView as _HV
            w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(28, 24, 28, 24); v.setSpacing(12)
            top = QHBoxLayout()
            h = QLabel("Links"); h.setObjectName("H1"); top.addWidget(h); top.addStretch(1)
            rmb = QPushButton("Clear Selected Row"); rmb.clicked.connect(self._clear_link_row)
            top.addWidget(rmb); v.addLayout(top)
            self.links_table = QTableWidget(0, 3)
            self.links_table.setHorizontalHeaderLabels(["Purpose", "Link", "Open"])
            hh = self.links_table.horizontalHeader()
            hh.setSectionResizeMode(0, _HV.Stretch)
            hh.setSectionResizeMode(1, _HV.Stretch)
            hh.setSectionResizeMode(2, _HV.Fixed); self.links_table.setColumnWidth(2, 70)
            # editable Purpose/Link; row numbers come from the vertical header (Req: no S.No column)
            self.links_table.setEditTriggers(
                QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked |
                QAbstractItemView.EditKeyPressed | QAbstractItemView.AnyKeyPressed)
            self.links_table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.links_table.setSelectionMode(QAbstractItemView.SingleSelection)
            self.links_table.itemChanged.connect(self._links_changed)
            v.addWidget(self.links_table, 1)
            hint = QLabel("Type a purpose and paste a link into any empty row; click Open to launch it.")
            hint.setObjectName("Muted"); v.addWidget(hint)
            self._link_saving = False
            return w

        def _reload_links(self):
            from PySide6.QtWidgets import QTableWidgetItem, QPushButton as _PB
            self._link_saving = True
            self.links_table.blockSignals(True)
            self.links_table.setRowCount(0)
            rows = list_links(self.conn)
            total = len(rows) + self.EMPTY_LINK_ROWS
            self.links_table.setRowCount(total)
            for i in range(total):
                if i < len(rows):
                    _lid, purpose, url = rows[i]
                else:
                    purpose, url = "", ""
                self.links_table.setItem(i, 0, QTableWidgetItem(purpose or ""))
                self.links_table.setItem(i, 1, QTableWidgetItem(url or ""))
                if url:
                    btn = _PB("Open"); btn.clicked.connect(lambda _=False, u=url: self._launch_url(u))
                    self.links_table.setCellWidget(i, 2, btn)
                else:
                    self.links_table.removeCellWidget(i, 2)
            self.links_table.blockSignals(False)
            self._link_saving = False

        def _links_changed(self, _item):
            if self._link_saving:
                return
            # rebuild the saved set from every non-empty row, in order
            pairs = []
            for i in range(self.links_table.rowCount()):
                pu = self.links_table.item(i, 0); ln = self.links_table.item(i, 1)
                pu = pu.text().strip() if pu else ""
                ln = ln.text().strip() if ln else ""
                if pu or ln:
                    pairs.append((pu, ln))
            self.conn.execute("DELETE FROM links")
            for pu, ln in pairs:
                add_link(self.conn, pu, ln)
            self._reload_links()

        def _clear_link_row(self):
            r = self.links_table.currentRow()
            if r < 0:
                return
            if self.links_table.item(r, 0): self.links_table.item(r, 0).setText("")
            if self.links_table.item(r, 1): self.links_table.item(r, 1).setText("")

        def _launch_url(self, url):
            url = (url or "").strip()
            if not url:
                return
            if not url.startswith(("http://", "https://", "file:", "mailto:")):
                url = "https://" + url
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(url))

        # ---- Application launcher ----
        def _page_apps(self):
            w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(28, 24, 28, 24); v.setSpacing(12)
            top = QHBoxLayout()
            h = QLabel("Apps"); h.setObjectName("H1"); top.addWidget(h); top.addStretch(1)
            addb = QPushButton("＋ Add Application"); addb.setObjectName("primary")
            addb.clicked.connect(self._add_app)
            det = QPushButton("Detect Installed"); det.clicked.connect(self._detect_apps)
            rmb = QPushButton("Remove Selected"); rmb.clicked.connect(self._remove_app)
            for b_ in (addb, det, rmb): top.addWidget(b_)
            v.addLayout(top)
            self.apps_list = QListWidget()
            self.apps_list.setViewMode(QListWidget.IconMode)
            self.apps_list.setIconSize(QSize(64, 64))
            self.apps_list.setGridSize(QSize(120, 110))
            self.apps_list.setResizeMode(QListWidget.Adjust)
            self.apps_list.setMovement(QListWidget.Static)
            self.apps_list.setSpacing(10)
            self.apps_list.setWordWrap(True)
            self.apps_list.itemDoubleClicked.connect(self._launch_app_item)
            v.addWidget(self.apps_list, 1)
            hint = QLabel("Double-click to launch. Use “Add Application” to tag MATLAB, S32DS, "
                          "VS Code or any other installed program.")
            hint.setObjectName("Muted"); v.addWidget(hint)
            return w

        def _app_icon(self, name, target):
            """Use the real file icon when available, else a lettered badge."""
            from PySide6.QtGui import QPixmap, QIcon
            from PySide6.QtWidgets import QFileIconProvider
            from PySide6.QtCore import QFileInfo
            p = Path(target)
            if p.exists():
                ic = QFileIconProvider().icon(QFileInfo(str(p)))
                if not ic.isNull():
                    return ic
            size = 64
            pm = QPixmap(size, size); pm.fill(Qt.transparent)
            pt = QPainter(pm); pt.setRenderHint(QPainter.Antialiasing)
            r = QRectF(2, 2, size - 4, size - 4)
            path = QPainterPath(); path.addRoundedRect(r, 14, 14)
            base = QColor(TILE_COLORS[(len(name) + ord(name[0] if name else 'A')) % len(TILE_COLORS)])
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0.0, base.lighter(118)); g.setColorAt(1.0, base.darker(112))
            pt.setPen(Qt.NoPen); pt.setBrush(QBrush(g)); pt.drawPath(path)
            pt.setPen(QColor("#ffffff"))
            f = QFont("Segoe UI"); f.setPointSize(20); f.setBold(True); pt.setFont(f)
            pt.drawText(r, Qt.AlignCenter, (name[:2] if name else "?").upper())
            pt.end()
            return QIcon(pm)

        def _reload_apps(self):
            from PySide6.QtWidgets import QListWidgetItem
            self.apps_list.clear()
            for aid, name, target, kind in list_apps(self.conn):
                it = QListWidgetItem(self._app_icon(name, target), name)
                it.setData(Qt.UserRole, (aid, target, kind))
                it.setToolTip(target)
                it.setTextAlignment(Qt.AlignHCenter)
                self.apps_list.addItem(it)

        def _launch_app_item(self, item):
            data = item.data(Qt.UserRole)
            if not data:
                return
            _aid, target, kind = data
            ok, err = launch_app(target, kind)
            if ok:
                self.statusBar().showMessage(f"Launched {item.text()}.", 3000)
            else:
                QMessageBox.warning(self, "Application",
                                    f"Could not launch {item.text()}:\n{target}\n\n{err}")

        def _add_app(self):
            existing = {n.lower() for _i, n, _t, _k in list_apps(self.conn)}
            dlg = AppPickerDialog(available_apps(), existing)
            if dlg.exec() != QDialog.Accepted:
                return
            if dlg.chosen:
                n, t, k = dlg.chosen
                add_app(self.conn, n, t, k)
                self._reload_apps()
                self.statusBar().showMessage(f"Added {n}.", 3000)
                return
            if not dlg.browse:
                return
            # --- browse fallback ---
            name, ok2 = text_prompt(self, "Add Application", "Name for this application:")
            if not ok2 or not name.strip():
                return
            start = ""
            for cand in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                         os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"), "/usr/bin"):
                if cand and Path(cand).exists():
                    start = cand; break
            path, _ = QFileDialog.getOpenFileName(
                self, f"Select the {name.strip()} program", start,
                "Programs (*.exe *.bat *.cmd *.lnk);;All files (*)")
            if not path:
                return
            add_app(self.conn, name.strip(), path, "path")
            self._reload_apps()
            self.statusBar().showMessage(f"Added {name.strip()}.", 3000)

        def _detect_apps(self):
            found = detect_apps()
            existing = {n.lower() for _i, n, _t, _k in list_apps(self.conn)}
            added = [n for n, t, k in found
                     if n.lower() not in existing and (add_app(self.conn, n, t, k) or True)]
            self._reload_apps()
            QMessageBox.information(
                self, "Detect Installed",
                ("Added: " + ", ".join(added)) if added else
                "No new applications found in the usual install locations.\n"
                "Use “Add Application” to browse to one directly.")

        def _remove_app(self):
            it = self.apps_list.currentItem()
            if not it or not it.data(Qt.UserRole):
                return
            delete_app(self.conn, it.data(Qt.UserRole)[0]); self._reload_apps()

        # ---- Screenshots ----
        def _page_shots(self):
            w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(28, 24, 28, 24); v.setSpacing(12)
            top = QHBoxLayout()
            h = QLabel("Screenshots"); h.setObjectName("H1"); top.addWidget(h)
            top.addWidget(QLabel("   Find:"))
            self.shot_search = QLineEdit(); self.shot_search.setPlaceholderText("type a tag name…")
            self.shot_search.setMaximumWidth(260)
            self.shot_search.textChanged.connect(self._shot_search_changed)
            top.addWidget(self.shot_search); top.addStretch(1)
            paste = QPushButton("Paste from Clipboard"); paste.setObjectName("primary")
            paste.clicked.connect(self._paste_shot)
            imp = QPushButton("Add Image File…"); imp.clicked.connect(self._import_shot)
            rmb = QPushButton("Remove"); rmb.clicked.connect(self._remove_shot)
            for b_ in (paste, imp, rmb): top.addWidget(b_)
            v.addLayout(top)

            body = QHBoxLayout(); body.setSpacing(14)
            # LEFT: tag / name list
            left = QVBoxLayout(); left.setSpacing(6)
            lt = QLabel("TAGS"); lt.setObjectName("CardTitle"); left.addWidget(lt)
            self.shot_names = QListWidget()
            self.shot_names.setMaximumWidth(230)
            self.shot_names.currentRowChanged.connect(self._shot_name_selected)
            self.shot_names.itemDoubleClicked.connect(
                lambda it: self._open_file(Path(it.data(Qt.UserRole)[1]))
                if it.data(Qt.UserRole) else None)
            left.addWidget(self.shot_names, 1)
            lw = QWidget(); lw.setLayout(left); body.addWidget(lw)

            # RIGHT: every saved screenshot as an icon
            right = QVBoxLayout(); right.setSpacing(6)
            self.shot_caption = QLabel("SCREENSHOTS"); self.shot_caption.setObjectName("CardTitle")
            right.addWidget(self.shot_caption)
            self.shots_list = QListWidget()
            self.shots_list.setViewMode(QListWidget.IconMode)
            self.shots_list.setIconSize(QSize(120, 120))
            self.shots_list.setGridSize(QSize(170, 170))
            self.shots_list.setResizeMode(QListWidget.Adjust)
            self.shots_list.setMovement(QListWidget.Static)
            self.shots_list.setSpacing(12)
            self.shots_list.setWordWrap(True)
            self.shots_list.currentItemChanged.connect(self._shot_icon_selected)
            self.shots_list.itemDoubleClicked.connect(
                lambda it: self._open_file(Path(it.data(Qt.UserRole)[1]))
                if it.data(Qt.UserRole) else None)
            right.addWidget(self.shots_list, 1)
            rw = QWidget(); rw.setLayout(right); body.addWidget(rw, 1)
            v.addLayout(body, 1)

            hint = QLabel("Copy a screenshot (PrtSc / Win+Shift+S), then click “Paste from Clipboard”. "
                          "Type a tag in Find to highlight matches. Double-click to open.")
            hint.setObjectName("Muted"); v.addWidget(hint)
            self._shot_ids = []
            self._syncing_shots = False
            return w

        def _shot_thumb(self, path):
            from PySide6.QtGui import QIcon
            pm = QPixmap(str(path))
            if pm.isNull():
                pm = QPixmap(96, 96); pm.fill(QColor(CURRENT["PANEL2"]))
            return QIcon(pm.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        def _reload_shots(self):
            from PySide6.QtWidgets import QListWidgetItem
            self._syncing_shots = True
            self.shots_list.clear(); self.shot_names.clear(); self._shot_ids = []
            for sid, tag, path, note, created in list_shots(self.conn):   # always show ALL
                self._shot_ids.append(sid)
                data = (sid, path, tag, note or "")
                icon = QListWidgetItem(self._shot_thumb(path), tag)
                icon.setData(Qt.UserRole, data)
                icon.setToolTip(f"{tag}\n{note or ''}")
                icon.setTextAlignment(Qt.AlignHCenter)
                self.shots_list.addItem(icon)
                name = QListWidgetItem(tag)
                name.setData(Qt.UserRole, data)
                name.setToolTip(note or "")
                self.shot_names.addItem(name)
            self._syncing_shots = False
            if self.shots_list.count():
                self.shots_list.setCurrentRow(0)
            else:
                self.shot_caption.setText("SCREENSHOTS")

        def _shot_name_selected(self, row):
            if self._syncing_shots or row < 0:
                return
            self._syncing_shots = True
            self.shots_list.setCurrentRow(row)
            self.shots_list.scrollToItem(self.shots_list.item(row))
            self._syncing_shots = False
            self._update_shot_caption()

        def _shot_icon_selected(self, *_):
            if self._syncing_shots:
                self._update_shot_caption(); return
            row = self.shots_list.currentRow()
            if row >= 0:
                self._syncing_shots = True
                self.shot_names.setCurrentRow(row)
                self._syncing_shots = False
            self._update_shot_caption()

        def _update_shot_caption(self):
            data = self._current_shot()
            if not data:
                self.shot_caption.setText("SCREENSHOTS"); return
            _sid, _path, tag, note = data
            self.shot_caption.setText(f"SCREENSHOTS   ·   {tag}" + (f"  ({note})" if note else ""))

        def _shot_search_changed(self, text):
            """Highlight every matching screenshot icon (and its tag)."""
            q = text.strip().lower()
            first = None
            for i in range(self.shots_list.count()):
                icon = self.shots_list.item(i)
                name = self.shot_names.item(i)
                data = icon.data(Qt.UserRole) or ()
                hay = f"{data[2] if len(data) > 2 else ''} {data[3] if len(data) > 3 else ''}".lower()
                match = bool(q) and q in hay
                for it in (icon, name):
                    if match:
                        it.setBackground(QColor("#ffd166"))     # amber: search match
                        it.setForeground(QColor("#1a2233"))
                    else:
                        it.setBackground(QColor(0, 0, 0, 0))
                        it.setForeground(QColor(CURRENT["TEXT"]))
                if match and first is None:
                    first = i
            if first is not None:
                self._syncing_shots = True
                self.shots_list.setCurrentRow(first)
                self.shot_names.setCurrentRow(first)
                self.shots_list.scrollToItem(self.shots_list.item(first))
                self._syncing_shots = False
                self._update_shot_caption()

        def _current_shot(self):
            it = self.shots_list.currentItem()
            return it.data(Qt.UserRole) if it else None

        def _paste_shot(self):
            img = QApplication.clipboard().image()
            if img.isNull():
                QMessageBox.information(
                    self, "Screenshots",
                    "No image on the clipboard.\nTake a screenshot first "
                    "(PrtSc or Win+Shift+S), then click this button."); return
            tag, ok = text_prompt(self, "Screenshot", "Tag / name for this screenshot:")
            if not ok or not tag.strip():
                return
            note, _ = text_prompt(self, "Screenshot", "Note (optional):")
            fname = f"{datetime.now():%Y%m%d_%H%M%S}_{safe_name(tag)[:40]}.png"
            out = shots_dir() / fname
            if not img.save(str(out), "PNG"):
                QMessageBox.warning(self, "Screenshots", f"Could not save:\n{out}"); return
            add_shot(self.conn, tag, out, note or "")
            self._reload_shots()
            self.statusBar().showMessage(f"Saved screenshot “{tag}”.", 3000)

        def _import_shot(self):
            path, _ = QFileDialog.getOpenFileName(
                self, "Add image", str(downloads_dir()),
                "Images (*.png *.jpg *.jpeg *.bmp *.gif)")
            if not path:
                return
            tag, ok = text_prompt(self, "Screenshot", "Tag / name for this image:",
                                  text=Path(path).stem)
            if not ok or not tag.strip():
                return
            note, _ = text_prompt(self, "Screenshot", "Note (optional):")
            dest = shots_dir() / f"{datetime.now():%Y%m%d_%H%M%S}_{safe_name(tag)[:40]}{Path(path).suffix}"
            try:
                shutil.copy2(path, dest)
            except Exception as e:
                QMessageBox.warning(self, "Screenshots", f"Could not copy:\n{e}"); return
            add_shot(self.conn, tag, dest, note or "")
            self._reload_shots()

        def _remove_shot(self):
            data = self._current_shot()
            if not data:
                return
            sid, _path, tag, _note = data
            if QMessageBox.question(self, "Remove screenshot",
                                    f"Remove “{tag}”? The image file will be deleted.") != QMessageBox.Yes:
                return
            delete_shot(self.conn, sid, remove_file=True)
            self._reload_shots()

        # ---- requirements ----
        def _page_reqs(self):
            w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(28, 24, 28, 24); v.setSpacing(12)
            top = QHBoxLayout()
            h = QLabel("Requirements"); h.setObjectName("H1"); top.addWidget(h)
            top.addWidget(QLabel("   Project:"))
            self.req_project = QComboBox(); self.req_project.setMinimumWidth(220)
            self.req_project.currentIndexChanged.connect(self._reload_reqs)
            top.addWidget(self.req_project); top.addStretch(1)
            addb = QPushButton("＋ Add Requirement"); addb.setObjectName("primary"); addb.clicked.connect(self._add_req)
            top.addWidget(addb)
            expb = QPushButton("Export CSV"); expb.clicked.connect(self._export_reqs); top.addWidget(expb)
            v.addLayout(top)
            self.req_table = QTableWidget(0, 6)
            self.req_table.setHorizontalHeaderLabels(["ID", "Title", "Type", "Status", "Verify", "Assignee"])
            self.req_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.req_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.req_table.cellDoubleClicked.connect(self._edit_req)
            v.addWidget(self.req_table, 1)
            hint = QLabel("Double-click a row to edit."); hint.setObjectName("Muted"); v.addWidget(hint)
            return w

        def _reload_req_projects(self):
            self.req_project.blockSignals(True); self.req_project.clear(); self._req_ids = []
            for p in list_projects(self.conn):
                self.req_project.addItem(p[1]); self._req_ids.append(p[0])
            self.req_project.blockSignals(False); self._reload_reqs()

        def _current_req_pid(self):
            i = self.req_project.currentIndex()
            return self._req_ids[i] if 0 <= i < len(self._req_ids) else None

        def _reload_reqs(self):
            pid = self._current_req_pid(); self.req_table.setRowCount(0)
            if pid is None: return
            rows = self.conn.execute("SELECT req_key,title,rtype,status,verification,assignee "
                                     "FROM requirements WHERE project_id=? ORDER BY req_key", (pid,)).fetchall()
            self.req_table.setRowCount(len(rows))
            for i, r in enumerate(rows):
                for j, val in enumerate(r): self.req_table.setItem(i, j, QTableWidgetItem(val or ""))

        def _add_req(self):
            pid = self._current_req_pid()
            if pid is None:
                QMessageBox.information(self, "Requirements", "Create a project first."); return
            key = next_req_key(self.conn, pid)
            dlg = ReqDialog(key)
            if dlg.exec() != QDialog.Accepted: return
            d = dlg.result_data
            self.conn.execute("INSERT INTO requirements (project_id,req_key,title,description,rtype,status,"
                              "verification,assignee,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                              (pid, key, d["title"], d["description"], d["rtype"], d["status"],
                               d["verification"], d["assignee"], datetime.now().isoformat(timespec="seconds")))
            self.conn.commit(); self._reload_reqs()

        def _edit_req(self, row, _c):
            pid = self._current_req_pid(); key = self.req_table.item(row, 0).text()
            r = self.conn.execute("SELECT title,description,rtype,status,verification,assignee "
                                  "FROM requirements WHERE project_id=? AND req_key=?", (pid, key)).fetchone()
            data = dict(zip(["title", "description", "rtype", "status", "verification", "assignee"], r))
            dlg = ReqDialog(key, data)
            if dlg.exec() != QDialog.Accepted: return
            d = dlg.result_data
            self.conn.execute("UPDATE requirements SET title=?,description=?,rtype=?,status=?,verification=?,"
                              "assignee=?,updated_at=? WHERE project_id=? AND req_key=?",
                              (d["title"], d["description"], d["rtype"], d["status"], d["verification"],
                               d["assignee"], datetime.now().isoformat(timespec="seconds"), pid, key))
            self.conn.commit(); self._reload_reqs()

        def _export_reqs(self):
            pid = self._current_req_pid()
            if pid is None: return
            name = self.conn.execute("SELECT name FROM projects WHERE id=?", (pid,)).fetchone()[0]
            out, _ = QFileDialog.getSaveFileName(self, "Export requirements",
                                                 f"{safe_name(name)}_requirements.csv", "CSV (*.csv)")
            if not out: return
            rows = self.conn.execute("SELECT req_key,title,description,rtype,status,verification,assignee "
                                     "FROM requirements WHERE project_id=? ORDER BY req_key", (pid,)).fetchall()
            with open(out, "w", newline="", encoding="utf-8") as f:
                wr = csv.writer(f)
                wr.writerow(["ID", "Title", "Description", "Type", "Status", "Verification", "Assignee"])
                wr.writerows(rows)
            self.statusBar().showMessage(f"Exported {len(rows)} requirements.", 4000)

    # ---- launch ----------------------------------------------------------
    global LAUNCH_UI_INDEX
    app = QApplication(sys.argv)
    conn = init_db()
    seed_default_apps(conn)
    apply_theme(app, get_setting(conn, "theme", DEFAULT_THEME))

    # rotating UI: different design + punchline each open (Req1/Req2)
    counter = int(get_setting(conn, "ui_counter", "0"))
    set_setting(conn, "ui_counter", str(counter + 1))
    LAUNCH_UI_INDEX = counter
    apply_ui_rotation(counter)

    # resolve where projects/files live (Req2)
    saved_root = get_setting(conn, "files_root", None)
    if saved_root:
        set_project_root(saved_root)

    profile = get_profile(conn)
    if profile is None:
        dlg = Onboarding(location=saved_root or str(default_root()))
        if dlg.exec() != QDialog.Accepted:
            return
        save_profile(conn, dlg.name, dlg.role)
        set_setting(conn, "files_root", dlg.location); set_project_root(dlg.location)
        profile = get_profile(conn)
    elif not saved_root:
        # existing user from before this feature — pin the current default
        set_setting(conn, "files_root", str(default_root())); set_project_root(default_root())

    win = Home(conn, profile, app); win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui()
