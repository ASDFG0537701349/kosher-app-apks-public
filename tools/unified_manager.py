#!/usr/bin/env python3
"""
כלי מאוחד לניהול חנות אפליקציות פרטית.
כולל:
1. ניהול ידני של אפליקציות (הוספה/עדכון APK).
2. עדכון אוטומטי של תיאורים וצילומי מסך מ-Google Play.

דרישות:
    pip install pyaxmlparser pillow google-play-scraper
"""

from __future__ import annotations
import hashlib
import json
import shutil
import tkinter as tk
import urllib.parse
import zipfile
import time
import sys
import threading
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

# GitHub repository URL - hardcoded for this project
GITHUB_USER = "ASDFG0537701349"
GITHUB_REPO = "kosher-app-apks-public"
DEFAULT_GITHUB_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/refs/heads/main"

CATEGORIES = [
    "פיננסים", 
    "תחבורה", 
    "אפליקציות גוגל", 
    "מסרים", 
    "כלים", 
    "מדיה ובידור", 
    "קניות", 
    "לימוד וחינוך", 
    "כללי"
]

@dataclass
class ApkMetadata:
    apk_path: Path
    name: str
    package_name: str
    version_code: int
    version_name: str
    size: str
    checksum: str
    icon_path_in_apk: str | None

# --- פונקציות עזר מ-store_manager.py ---

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
    if "drive.google.com" not in value:
        return value
    parsed = urllib.parse.urlparse(value)
    file_id = None
    if "/file/d/" in parsed.path:
        file_id = parsed.path.split("/file/d/", 1)[1].split("/", 1)[0]
    else:
        file_id = urllib.parse.parse_qs(parsed.query).get("id", [None])[0]
    if not file_id:
        return value
    return f"https://drive.google.com/uc?export=download&id={file_id}"

def load_apk_metadata(apk_path: Path) -> ApkMetadata:
    apk = APK(str(apk_path))
    package_name = read_apk_value(apk, "package", "get_package")
    if not package_name:
        raise RuntimeError("לא הצלחתי לחלץ Package Name מה-APK.")
    version_code = int(read_apk_value(apk, "version_code", "get_androidversion_code") or 0)
    version_name = read_apk_value(apk, "version_name", "get_androidversion_name") or str(version_code)
    app_name = read_apk_value(apk, "application", "get_app_name") or package_name
    icon_path = None
    try:
        icon_path = apk.get_app_icon()
    except Exception:
        icon_path = None
    return ApkMetadata(
        apk_path=apk_path,
        name=app_name,
        package_name=package_name,
        version_code=version_code,
        version_name=version_name,
        size=file_size_mb(apk_path),
        checksum=md5_checksum(apk_path),
        icon_path_in_apk=icon_path,
    )

def read_apk_value(apk: APK, *names: str) -> str | None:
    for name in names:
        value = getattr(apk, name, None)
        if callable(value):
            value = value()
        if value not in (None, ""):
            return str(value)
    return None

def extract_icon(metadata: ApkMetadata) -> Path:
    ICONS_DIR.mkdir(exist_ok=True)
    output_path = ICONS_DIR / f"{metadata.package_name}.png"
    
    icon_path = None
    try:
        with zipfile.ZipFile(metadata.apk_path) as archive:
            icon_path = choose_icon_path(archive, metadata.icon_path_in_apk)
            if not icon_path:
                icon_path = find_any_icon(archive)
                
            if icon_path:
                with archive.open(icon_path) as icon_file:
                    temp_path = ICONS_DIR / f"{metadata.package_name}{Path(icon_path).suffix}"
                    with temp_path.open("wb") as out:
                        shutil.copyfileobj(icon_file, out)
                
                if temp_path.suffix.lower() == ".png":
                    temp_path.replace(output_path)
                    return output_path
                
                if Image:
                    with Image.open(temp_path) as image:
                        image.convert("RGBA").save(output_path, "PNG")
                    temp_path.unlink(missing_ok=True)
                    return output_path
                else:
                    temp_path.replace(output_path)
                    return output_path
    except Exception:
        pass

    # --- FALLBACK: Try Google Play Store ---
    print(f"  🔍 ניסיון אחרון: משיכת אייקון מ-Google Play עבור {metadata.package_name}...")
    play_icon_url = fetch_play_icon_url(metadata.package_name)
    if play_icon_url:
        try:
            import urllib.request
            with urllib.request.urlopen(play_icon_url) as response:
                with open(output_path, 'wb') as out_file:
                    out_file.write(response.read())
            print(f"  ✅ האייקון נמשך בהצלחה מ-Google Play.")
            return output_path
        except Exception as e:
            print(f"  ❌ נכשל במשיכת אייקון מגוגל פליי: {e}")

    raise RuntimeError("לא נמצא אייקון בתוך ה-APK וגם לא ב-Google Play.")

def fetch_play_icon_url(package_name: str) -> str | None:
    """Fetches just the icon URL from Google Play Store."""
    if not play_scraper: return None
    try:
        result = play_scraper(package_name, lang='iw', country='il')
        return result.get('icon')
    except Exception:
        return None

def choose_icon_path(archive: zipfile.ZipFile, manifest_path: str | None) -> str | None:
    """Smartly chooses the best icon from the archive, prioritizing density and type."""
    names = archive.namelist()
    supported = (".png", ".webp", ".jpg")
    
    # 1. Try to clean and use manifest path if it's not XML
    if manifest_path:
        clean_path = manifest_path.lstrip('/')
        if clean_path in names and clean_path.lower().endswith(supported):
            return clean_path
        
        # If it was an XML (adaptive icon), try to find a PNG/WebP with the same name
        base_name = Path(clean_path).stem
        for n in names:
            if base_name in n and n.lower().endswith(supported) and ("mipmap" in n or "drawable" in n):
                return n

    # 2. Priority-based search: Density folders (High to Low)
    densities = ["xxxhdpi", "xxhdpi", "xhdpi", "hdpi", "mdpi"]
    types = ["mipmap", "drawable"]
    common_names = ["ic_launcher", "app_icon", "icon", "ic_app"]

    for density in densities:
        for t in types:
            for name in common_names:
                # Look for exact matches in specific folders
                target = f"res/{t}-{density}/{name}"
                for ext in supported:
                    path = f"{target}{ext}"
                    if path in names:
                        return path

    return None

def find_any_icon(archive: zipfile.ZipFile) -> str | None:
    """Fallback: finds the largest image that looks like an app icon."""
    names = archive.namelist()
    supported = (".png", ".webp")
    candidates = [
        n for n in names 
        if n.lower().endswith(supported) 
        and ("icon" in n.lower() or "launcher" in n.lower())
        and "res/" in n
    ]
    if not candidates:
        return None
    # Return the largest candidate (likely highest resolution)
    return max(candidates, key=lambda n: archive.getinfo(n).file_size)

def load_apps_json() -> list[dict]:
    if not APPS_JSON_PATH.exists():
        return []
    with APPS_JSON_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError("apps.json חייב להיות מערך JSON.")
    return data

def save_apps_json(apps: list[dict]) -> None:
    with APPS_JSON_PATH.open("w", encoding="utf-8") as file:
        json.dump(apps, file, ensure_ascii=False, indent=2)
        file.write("\n")

def upsert_app(app_entry: dict) -> None:
    apps = load_apps_json()
    package_name = app_entry["packageName"]
    updated = False
    for index, existing in enumerate(apps):
        if existing.get("packageName") == package_name:
            apps[index] = app_entry
            updated = True
            break
    if not updated:
        apps.append(app_entry)
    apps.sort(key=lambda item: item.get("name", "").lower())
    save_apps_json(apps)

# --- פונקציות מ-update_descriptions.py ---

def fetch_play_store_data(package_name: str) -> dict[str, any]:
    if not play_scraper:
        return {}
    try:
        result = play_scraper(package_name, lang='iw', country='il')
        data = {}
        description = result.get('description')
        if description:
            data['description'] = description
        screenshots = result.get('screenshots', [])
        if screenshots:
            data['screenshots'] = screenshots[:5]
        return data
    except Exception:
        return {}

def run_auto_sync(log_callback=None):
    if not play_scraper:
        if log_callback: log_callback("❌ שגיאה: google-play-scraper לא מותקן.")
        return

    apps = load_apps_json()
    if log_callback: log_callback(f"📱 נמצאו {len(apps)} אפליקציות לעדכון.")
    
    desc_updated = 0
    for i, app in enumerate(apps, 1):
        package_name = app.get('packageName')
        if not package_name: continue
        
        if log_callback: log_callback(f"[{i}/{len(apps)}] מושך נתונים עבור {package_name}...")
        data = fetch_play_store_data(package_name)
        
        if 'description' in data:
            app['description'] = data['description']
            desc_updated += 1
        if 'screenshots' in data:
            app['screenshots'] = data['screenshots']
        
        if i < len(apps):
            time.sleep(1)
            
    save_apps_json(apps)
    if log_callback: log_callback(f"✅ הסנכרון הסתיים. {desc_updated} תיאורים עודכנו.")

# --- ממשק משתמש מאוחד ---

class StoreManagerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Private Store Manager - Unified")
        self.geometry("850x700")
        self.minsize(800, 650)

        self.metadata: ApkMetadata | None = None
        self.apk_url_var = tk.StringVar()
        self.category_var = tk.StringVar(value=CATEGORIES[-1])
        self.status_var = tk.StringVar(value="בחר APK מהמחשב או סנכרן נתונים מגוגל פליי.")

        self.name_var = tk.StringVar()
        self.package_var = tk.StringVar()
        self.version_code_var = tk.StringVar()
        self.version_name_var = tk.StringVar()
        self.size_var = tk.StringVar()
        self.checksum_var = tk.StringVar()

        self._build_ui()

    def _make_entry_with_buttons(self, parent, variable, row, col=1) -> ttk.Entry:
        """Creates an entry field with Copy and Paste buttons next to it."""
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=col, sticky="ew", pady=5)
        frame.columnconfigure(0, weight=1)

        entry = ttk.Entry(frame, textvariable=variable)
        entry.grid(row=0, column=0, sticky="ew")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=0, column=1, padx=(5, 0))

        ttk.Button(btn_frame, text="📋 העתק", width=7, 
                   command=lambda v=variable: self._copy_to_clipboard(v.get())).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📥 הדבק", width=7, 
                   command=lambda v=variable: self._paste_from_clipboard(v)).pack(side=tk.LEFT, padx=2)

        return entry

    def _copy_to_clipboard(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("✅ הועתק ללוח.")

    def _paste_from_clipboard(self, var: tk.StringVar) -> None:
        try:
            var.set(self.clipboard_get().strip())
            self.status_var.set("✅ הודבק מהלוח.")
        except tk.TclError:
            pass

    def _build_ui(self) -> None:
        # סגנון מודרני
        style = ttk.Style()
        style.configure("Action.TButton", padding=6, font=('Helvetica', 10, 'bold'))

        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # --- חלק עליון: ניהול APK ---
        apk_group = ttk.LabelFrame(main_frame, text=" הוספת/עדכון אפליקציה (APK) ", padding=15)
        apk_group.pack(fill=tk.X, pady=(0, 15))
        apk_group.columnconfigure(1, weight=1)

        ttk.Button(apk_group, text="📂 בחר APK מהמחשב", command=self.choose_apk).grid(row=0, column=0, sticky="w", pady=5)
        ttk.Label(apk_group, textvariable=self.status_var, font=('Helvetica', 9, 'italic')).grid(row=0, column=1, sticky="w", padx=10)

        # שדות מידע
        fields_frame = ttk.Frame(apk_group)
        fields_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=10)
        fields_frame.columnconfigure(1, weight=1)
        fields_frame.columnconfigure(3, weight=1)

        info_fields = [
            ("שם האפליקציה", self.name_var, 0, 0),
            ("Version Code", self.version_code_var, 1, 0),
            ("Version Name", self.version_name_var, 1, 2),
            ("גודל", self.size_var, 2, 0),
        ]

        for label, var, r, c in info_fields:
            ttk.Label(fields_frame, text=label).grid(row=r, column=c, sticky="w", padx=(10, 5), pady=5)
            ttk.Entry(fields_frame, textvariable=var).grid(row=r, column=c+1, sticky="ew", pady=5)

        # Fields with copy/paste buttons
        ttk.Label(fields_frame, text="Package Name").grid(row=0, column=2, sticky="w", padx=(10, 5), pady=5)
        self._make_entry_with_buttons(fields_frame, self.package_var, row=0, col=3)

        ttk.Label(fields_frame, text="MD5 Checksum").grid(row=2, column=2, sticky="w", padx=(10, 5), pady=5)
        self._make_entry_with_buttons(fields_frame, self.checksum_var, row=2, col=3)

        ttk.Label(apk_group, text="קישור הורדה").grid(row=2, column=0, sticky="w", pady=5)
        self._make_entry_with_buttons(apk_group, self.apk_url_var, row=2)

        ttk.Label(apk_group, text="קטגוריה").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Combobox(apk_group, textvariable=self.category_var, values=CATEGORIES, state="readonly").grid(row=3, column=1, sticky="ew", pady=5)

        ttk.Label(apk_group, text="תיאור").grid(row=4, column=0, sticky="nw", pady=5)
        self.description_text = tk.Text(apk_group, height=4, wrap=tk.WORD)
        self.description_text.grid(row=4, column=1, sticky="ew", pady=5)

        ttk.Button(apk_group, text="💾 שמור ב-JSON", style="Action.TButton", command=self.update_json).grid(row=5, column=1, sticky="e", pady=10)

        # --- חלק תחתון: כלים אוטומטיים ---
        tools_group = ttk.LabelFrame(main_frame, text=" כלים ותחזוקה ", padding=15)
        tools_group.pack(fill=tk.BOTH, expand=True)

        btn_bar = ttk.Frame(tools_group)
        btn_bar.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(btn_bar, text="🔄 סנכרן תיאורים וצילומי מסך מגוגל פליי", command=self.start_sync).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_bar, text="🚀 פרסם ל-GitHub (Push)", command=self.start_git_push).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(tools_group, text="לוג פעילות:").pack(anchor="w")
        self.log_text = tk.Text(tools_group, height=8, bg="#F0F0F0", state="disabled")
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=5)

    def log(self, message: str):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.update_idletasks()

    def start_git_push(self):
        if not messagebox.askyesno("פרסום", "האם להעלות את כל השינויים (JSON ואייקונים) ל-GitHub?"):
            return
        
        def run():
            self.log("🚀 מתחיל תהליך פרסום ל-GitHub...")
            import subprocess
            try:
                # 0. Get current branch
                branch_res = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT_DIR, capture_output=True, text=True)
                branch = branch_res.stdout.strip() or "main"
                self.log(f"📍 אתה נמצא בענף: {branch}")

                # 1. Add changes (Only icons and JSON as requested)
                self.log("  • אוסף קבצי חנות (apps.json ו-icons)...")
                subprocess.run(["git", "add", "apps.json", "icons/"], cwd=ROOT_DIR, check=True)
                
                # 2. Commit
                self.log("  • מבצע Commit לשינויים...")
                msg = f"Update store data - {time.strftime('%Y-%m-%d %H:%M')}"
                subprocess.run(["git", "commit", "-m", msg], cwd=ROOT_DIR, capture_output=True)
                
                # 3. Push
                self.log(f"  • מבצע Push לענף {branch}...")
                result = subprocess.run(["git", "push", "-u", "origin", branch], cwd=ROOT_DIR, capture_output=True, text=True)
                
                if result.returncode == 0:
                    self.log(f"✅ הפרסום לענף '{branch}' הסתיים בהצלחה!")
                    messagebox.showinfo("הצלחה", f"הנתונים עלו בהצלחה ל-GitHub!\n\nהועלו רק: apps.json ותיקיית האייקונים.")
                else:
                    self.log(f"❌ שגיאה ב-Push:\n{result.stderr}")
                    messagebox.showerror("שגיאה", f"ה-Push נכשל:\n{result.stderr}")
            except Exception as e:
                self.log(f"❌ שגיאה כללית: {e}")
                messagebox.showerror("שגיאה", f"נכשל בתהליך ה-Git:\n{e}")

        threading.Thread(target=run, daemon=True).start()

    def choose_apk(self) -> None:
        selected = filedialog.askopenfilename(filetypes=[("Android APK", "*.apk")])
        if not selected: return
        try:
            self.metadata = load_apk_metadata(Path(selected))
            self.name_var.set(self.metadata.name)
            self.package_var.set(self.metadata.package_name)
            self.version_code_var.set(str(self.metadata.version_code))
            self.version_name_var.set(self.metadata.version_name)
            self.size_var.set(self.metadata.size)
            self.checksum_var.set(self.metadata.checksum)
            self.description_text.delete("1.0", tk.END)
            self.description_text.insert("1.0", self.metadata.name)
            self.status_var.set(f"✅ נטען: {self.metadata.name}")
        except Exception as e:
            messagebox.showerror("שגיאה", str(e))

    def update_json(self) -> None:
        if not self.metadata: return
        url = normalize_drive_url(self.apk_url_var.get())
        if not url:
            messagebox.showwarning("חסר קישור", "יש להזין קישור הורדה.")
            return
        try:
            extract_icon(self.metadata)
            package_name = self.package_var.get().strip()
            app_entry = {
                "name": self.name_var.get().strip(),
                "packageName": package_name,
                "versionCode": int(self.version_code_var.get().strip()),
                "versionName": self.version_name_var.get().strip(),
                "apkUrl": url,
                "iconUrl": f"{DEFAULT_GITHUB_BASE}/icons/{package_name}.png",
                "description": self.description_text.get("1.0", tk.END).strip(),
                "category": self.category_var.get().strip(),
                "size": self.size_var.get().strip(),
                "checksum": self.checksum_var.get().strip(),
                "checksumType": "MD5",
            }
            upsert_app(app_entry)
            messagebox.showinfo("נשמר", "האפליקציה עודכנה ב-apps.json")
        except Exception as e:
            messagebox.showerror("שגיאה", str(e))

    def start_sync(self):
        if not play_scraper:
            messagebox.showerror("חסרה ספרייה", "יש להתקין את google-play-scraper:\npip install google-play-scraper")
            return
        
        if not messagebox.askyesno("סנכרון", "האם לסנכרן תיאורים וצילומי מסך עבור כל האפליקציות?\nתהליך זה עשוי לקחת זמן."):
            return

        def run():
            self.log("🚀 מתחיל סנכרון מגוגל פליי...")
            run_auto_sync(log_callback=self.log)
            messagebox.showinfo("סיום", "תהליך הסנכרון הסתיים בהצלחה.")

        threading.Thread(target=run, daemon=True).start()

if __name__ == "__main__":
    StoreManagerApp().mainloop()
