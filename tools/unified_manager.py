#!/usr/bin/env python3
"""
כלי מאוחד לניהול חנות אפליקציות פרטית.
כולל עריכת אפליקציות קיימות, טעינת APK חדש, וסנכרון מגוגל פליי.
"""

from __future__ import annotations
import hashlib
import json
import shutil
import tkinter as tk
import urllib.parse
import zipfile
import time
import threading
import os
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from pyaxmlparser import APK

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    from google_play_scraper import app as play_scraper
except ImportError:
    play_scraper = None

# --- הגדרות נתיבים ---
ROOT_DIR = Path(__file__).resolve().parents[1]
APPS_JSON_PATH = ROOT_DIR / "apps.json"
ICONS_DIR = ROOT_DIR / "icons"

GITHUB_USER = "ASDFG0537701349"
GITHUB_REPO = "kosher-app-apks-public"
DEFAULT_GITHUB_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/refs/heads/main"

CATEGORIES = ["פיננסים", "תחבורה", "אפליקציות גוגל", "מסרים", "כלים", "מדיה ובידור", "קניות", "לימוד וחינוך", "כללי"]

@dataclass
class ApkMetadata:
    apk_path: Path
    name: str
    package_name: str
    version_code: int
    size: str
    checksum: str
    icon_path_in_apk: str | None

def file_size_mb(path: Path) -> str:
    size_mb = path.stat().st_size / (1024 * 1024)
    return f"{size_mb:.1f} MB"

def md5_checksum(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def normalize_drive_url(value: str) -> str:
    value = value.strip()
    if "drive.google.com" not in value: return value
    parsed = urllib.parse.urlparse(value)
    file_id = None
    if "/file/d/" in parsed.path:
        file_id = parsed.path.split("/file/d/", 1)[1].split("/", 1)[0]
    else:
        file_id = urllib.parse.parse_qs(parsed.query).get("id", [None])[0]
    return f"https://drive.google.com/uc?export=download&id={file_id}" if file_id else value

def load_apk_metadata(apk_path: Path) -> ApkMetadata:
    apk = APK(str(apk_path))
    package_name = apk.get_package()
    if not package_name: raise RuntimeError("לא הצלחתי לחלץ Package Name.")
    version_code = int(apk.get_androidversion_code() or 0)
    app_name = apk.get_app_name() or package_name
    icon_path = None
    try: icon_path = apk.get_app_icon()
    except: pass
    return ApkMetadata(
        apk_path=apk_path, name=app_name, package_name=package_name,
        version_code=version_code, size=file_size_mb(apk_path),
        checksum=md5_checksum(apk_path), icon_path_in_apk=icon_path
    )

def fetch_play_icon_url(package_name: str) -> str | None:
    if not play_scraper: return None
    try: return play_scraper(package_name, lang='iw', country='il').get('icon')
    except: return None

def extract_icon(metadata: ApkMetadata) -> Path:
    ICONS_DIR.mkdir(exist_ok=True)
    output_path = ICONS_DIR / f"{metadata.package_name}.png"
    play_url = fetch_play_icon_url(metadata.package_name)
    if play_url:
        try:
            import urllib.request
            with urllib.request.urlopen(play_url) as res:
                with open(output_path, 'wb') as f: f.write(res.read())
            return output_path
        except: pass
    # Fallback to APK
    try:
        with zipfile.ZipFile(metadata.apk_path) as archive:
            if metadata.icon_path_in_apk and metadata.icon_path_in_apk in archive.namelist():
                with archive.open(metadata.icon_path_in_apk) as icon_file:
                    with open(output_path, 'wb') as f: shutil.copyfileobj(icon_file, f)
                return output_path
    except: pass
    return output_path

def load_apps_json() -> list[dict]:
    if not APPS_JSON_PATH.exists(): return []
    with APPS_JSON_PATH.open("r", encoding="utf-8") as f: return json.load(f)

def save_apps_json(apps: list[dict]) -> None:
    with APPS_JSON_PATH.open("w", encoding="utf-8") as f:
        json.dump(apps, f, ensure_ascii=False, indent=2)

def upsert_app(app_entry: dict) -> None:
    apps = load_apps_json()
    pkg = app_entry["packageName"]
    for i, existing in enumerate(apps):
        if existing.get("packageName") == pkg:
            apps[i] = app_entry
            break
    else: apps.append(app_entry)
    apps.sort(key=lambda x: x.get("name", "").lower())
    save_apps_json(apps)

def run_auto_sync(log_callback=None):
    if not play_scraper: return
    apps = load_apps_json()
    for i, app in enumerate(apps, 1):
        pkg = app.get('packageName')
        if not pkg: continue
        if log_callback: log_callback(f"[{i}/{len(apps)}] מסנכרן {pkg}...")
        try:
            res = play_scraper(pkg, lang='iw', country='il')
            app['description'] = res.get('description', app.get('description', ''))
            app['screenshots'] = res.get('screenshots', [])[:5]
        except: pass
        time.sleep(1)
    save_apps_json(apps)

class StoreManagerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Private Store Manager - Unified")
        self.geometry("1000x750")
        
        self.metadata = None
        self.apk_url_var = tk.StringVar()
        self.category_var = tk.StringVar(value="כללי")
        self.status_var = tk.StringVar(value="בחר אפליקציה מהרשימה או טען APK חדש.")
        self.name_var = tk.StringVar()
        self.package_var = tk.StringVar()
        self.version_code_var = tk.StringVar()
        self.size_var = tk.StringVar()
        self.checksum_var = tk.StringVar()

        self._build_ui()

    def _build_ui(self):
        style = ttk.Style()
        style.configure("Action.TButton", padding=6, font=('Helvetica', 10, 'bold'))

        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Sidebar
        side = ttk.LabelFrame(paned, text=" אפליקציות קיימות ", padding=10)
        paned.add(side, weight=1)
        self.apps_listbox = tk.Listbox(side, font=("Segoe UI", 10))
        self.apps_listbox.pack(fill=tk.BOTH, expand=True)
        self.apps_listbox.bind("<<ListboxSelect>>", self.on_app_selected)
        ttk.Button(side, text="🔄 רענן רשימה", command=self.refresh_apps_list).pack(fill=tk.X, pady=(5,0))

        # Main
        main = ttk.Frame(paned, padding=10)
        paned.add(main, weight=3)

        form = ttk.LabelFrame(main, text=" פרטי אפליקציה ", padding=15)
        form.pack(fill=tk.X, pady=(0,10))
        
        grid = ttk.Frame(form)
        grid.pack(fill=tk.X)
        grid.columnconfigure(1, weight=1)

        self.add_field(grid, 0, "שם האפליקציה:", self.name_var)
        self.add_field(grid, 1, "Package Name:", self.package_var, show_copy=True)
        self.add_field(grid, 2, "Version Code:", self.version_code_var)
        self.add_field(grid, 3, "קישור APK:", self.apk_url_var, show_copy=True)
        self.add_field(grid, 4, "קטגוריה:", self.category_var, is_combo=True)
        self.add_field(grid, 5, "גודל:", self.size_var)
        self.add_field(grid, 6, "Checksum:", self.checksum_var, show_copy=True)

        ttk.Label(form, text="תיאור:").pack(anchor="w", pady=(10,0))
        self.description_text = tk.Text(form, height=5, font=("Segoe UI", 10), wrap=tk.WORD)
        self.description_text.pack(fill=tk.X, pady=5)

        btns = ttk.Frame(main)
        btns.pack(fill=tk.X, pady=(0,10))
        ttk.Button(btns, text="💾 שמור שינויים", style="Action.TButton", command=self.update_json).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text="📂 טען APK מהמחשב", command=self.load_apk).pack(side=tk.LEFT, padx=5)

        tools = ttk.LabelFrame(main, text=" כלים ואוטומציה ", padding=15)
        tools.pack(fill=tk.BOTH, expand=True)
        t_btns = ttk.Frame(tools)
        t_btns.pack(fill=tk.X, pady=(0,10))
        ttk.Button(t_btns, text="🔄 סנכרן מ-Google Play", command=self.start_sync).pack(side=tk.LEFT, padx=5)
        ttk.Button(t_btns, text="🖼️ עדכן אייקונים", command=self.start_icon_sync).pack(side=tk.LEFT, padx=5)
        ttk.Button(t_btns, text="🚀 פרסם (Push)", command=self.start_git_push).pack(side=tk.LEFT, padx=5)
        
        self.log_text = tk.Text(tools, height=8, bg="#F8F8F8", state="disabled", font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=5)
        ttk.Label(main, textvariable=self.status_var, font=('Helvetica', 9, 'italic')).pack(anchor="w")

        self.refresh_apps_list()

    def add_field(self, parent, row, label, var, is_combo=False, show_copy=False):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0,10), pady=5)
        if is_combo:
            ttk.Combobox(parent, textvariable=var, values=CATEGORIES, state="readonly").grid(row=row, column=1, sticky="ew")
        elif show_copy:
            f = ttk.Frame(parent)
            f.grid(row=row, column=1, sticky="ew")
            f.columnconfigure(0, weight=1)
            ttk.Entry(f, textvariable=var).grid(row=0, column=0, sticky="ew")
            ttk.Button(f, text="📋", width=3, command=lambda: self.copy(var.get())).grid(row=0, column=1, padx=2)
            ttk.Button(f, text="📥", width=3, command=lambda: self.paste(var)).grid(row=0, column=2, padx=2)
        else:
            ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew")

    def copy(self, txt):
        self.clipboard_clear()
        self.clipboard_append(txt)
        self.status_var.set("✅ הועתק.")

    def paste(self, var):
        try: var.set(self.clipboard_get().strip())
        except: pass

    def refresh_apps_list(self):
        self.apps_listbox.delete(0, tk.END)
        self.current_apps = load_apps_json()
        for app in self.current_apps: self.apps_listbox.insert(tk.END, app.get("name", "Unknown"))

    def on_app_selected(self, event):
        sel = self.apps_listbox.curselection()
        if not sel: return
        app = self.current_apps[sel[0]]
        self.metadata = None
        self.name_var.set(app.get("name", ""))
        self.package_var.set(app.get("packageName", ""))
        self.version_code_var.set(str(app.get("versionCode", "")))
        self.apk_url_var.set(app.get("apkUrl", ""))
        self.category_var.set(app.get("category", "כללי"))
        self.size_var.set(app.get("size", ""))
        self.checksum_var.set(app.get("checksum", ""))
        self.description_text.delete("1.0", tk.END)
        self.description_text.insert("1.0", app.get("description", ""))

    def load_apk(self):
        p = filedialog.askopenfilename(filetypes=[("APK", "*.apk")])
        if not p: return
        try:
            self.metadata = load_apk_metadata(Path(p))
            self.name_var.set(self.metadata.name)
            self.package_var.set(self.metadata.package_name)
            self.version_code_var.set(str(self.metadata.version_code))
            self.size_var.set(self.metadata.size)
            self.checksum_var.set(self.metadata.checksum)
            self.status_var.set(f"✅ נטען: {self.metadata.name}")
        except Exception as e: messagebox.showerror("שגיאה", str(e))

    def update_json(self):
        url = normalize_drive_url(self.apk_url_var.get())
        if not url: return messagebox.showwarning("חסר קישור", "הזן קישור הורדה")
        try:
            if self.metadata: extract_icon(self.metadata)
            pkg = self.package_var.get().strip()
            upsert_app({
                "name": self.name_var.get().strip(),
                "packageName": pkg,
                "versionCode": int(self.version_code_var.get().strip()),
                "apkUrl": url,
                "iconUrl": f"{DEFAULT_GITHUB_BASE}/icons/{pkg}.png",
                "description": self.description_text.get("1.0", tk.END).strip(),
                "category": self.category_var.get().strip(),
                "size": self.size_var.get().strip(),
                "checksum": self.checksum_var.get().strip(),
                "checksumType": "MD5"
            })
            self.refresh_apps_list()
            messagebox.showinfo("הצלחה", "נשמר בהצלחה!")
        except Exception as e: messagebox.showerror("שגיאה", str(e))

    def log(self, msg):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, f"{msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.update_idletasks()

    def start_icon_sync(self):
        def run():
            self.log("🚀 מעדכן אייקונים...")
            apps = load_apps_json()
            import urllib.request
            for i, app in enumerate(apps, 1):
                pkg = app.get('packageName')
                if not pkg: continue
                self.log(f"[{i}/{len(apps)}] {pkg}...")
                u = fetch_play_icon_url(pkg)
                if u:
                    try:
                        with urllib.request.urlopen(u) as r:
                            with open(ICONS_DIR / f"{pkg}.png", 'wb') as f: f.write(r.read())
                    except: pass
                time.sleep(0.5)
            self.log("✅ אייקונים עודכנו.")
        threading.Thread(target=run, daemon=True).start()

    def start_git_push(self):
        def run():
            import subprocess
            self.log("🚀 מפרסם ל-GitHub...")
            try:
                subprocess.run(["git", "add", "apps.json", "icons/"], cwd=ROOT_DIR, check=True)
                subprocess.run(["git", "commit", "-m", "Update store data"], cwd=ROOT_DIR, capture_output=True)
                subprocess.run(["git", "push", "origin", "main"], cwd=ROOT_DIR, check=True)
                self.log("✅ פורסם בהצלחה!")
            except Exception as e: self.log(f"❌ שגיאה: {e}")
        threading.Thread(target=run, daemon=True).start()

    def start_sync(self):
        def run():
            self.log("🚀 מסנכרן נתונים...")
            run_auto_sync(self.log)
            self.refresh_apps_list()
            self.log("✅ סנכרון הסתיים.")
        threading.Thread(target=run, daemon=True).start()

if __name__ == "__main__":
    StoreManagerApp().mainloop()
