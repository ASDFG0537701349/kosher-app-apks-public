#!/usr/bin/env python3
"""
סקריפט לעדכון תיאורים וצילומי מסך של אפליקציות מ-Google Play Store (עברית).

קורא את apps.json, מושך תיאור עדכני וצילומי מסך מ-Google Play עבור כל packageName,
ומעדכן רק את שדות description ו-screenshots תוך שמירה על כל שאר השדות ללא שינוי.
"""

import json
import time
import sys
from pathlib import Path
from typing import List, Dict, Any

try:
    from google_play_scraper import app as play_scraper
except ImportError:
    print("שגיאה: יש להתקין את ספריית google-play-scraper")
    print("הרץ: pip install google-play-scraper")
    sys.exit(1)


def fetch_app_data(package_name: str) -> Dict[str, Any]:
    """
    מושך את התיאור וצילומי המסך of an app from Google Play Store in Hebrew.
    
    Args:
        package_name: שם החבילה של האפליקציה
        
    Returns:
        מילון with 'description' and 'screenshots' keys, or empty dict on error
    """
    try:
        result = play_scraper(
            package_name,
            lang='iw',
            country='il'
        )
        
        data = {}
        
        # Get description
        description = result.get('description')
        if description:
            data['description'] = description
        
        # Get screenshots
        screenshots = result.get('screenshots', [])
        if screenshots:
            # Take first 5 screenshots to avoid too many
            data['screenshots'] = screenshots[:5]
        
        return data
    except Exception as e:
        print(f"  ⚠️ שגיאה במשיכת נתונים עבור {package_name}: {e}")
        return {}


def update_apps_data(input_file: str = "apps.json", 
                    output_file: str = "apps_updated.json",
                    delay: float = 2.0) -> None:
    """
    מעדכן תיאורים וצילומי מסך של אפליקציות מ-Google Play Store.
    
    Args:
        input_file: קובץ הקלט (JSON)
        output_file: קובץ הפלט (JSON)
        delay: השהיה בשניות בין בקשות (ברירת מחדל: 2)
    """
    # קריאת קובץ הקלט
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"שגיאה: הקובץ {input_file} לא נמצא")
        sys.exit(1)
    
    with open(input_path, 'r', encoding='utf-8') as f:
        apps = json.load(f)
    
    print(f"📱 נמצאו {len(apps)} אפליקציות לעדכון")
    
    # עדכון נתונים
    desc_updated = 0
    screenshots_updated = 0
    
    for i, app in enumerate(apps, 1):
        package_name = app.get('packageName')
        if not package_name:
            print(f"  ❌ לא נמצא packageName באובייקט #{i}")
            continue
        
        print(f"[{i}/{len(apps)}] מושך נתונים עבור {package_name}...")
        
        data = fetch_app_data(package_name)
        
        # Update description
        if 'description' in data:
            app['description'] = data['description']
            desc_updated += 1
            print(f"  ✅ תיאור עודכן")
        else:
            print(f"  ⚠️ לא נמצא תיאור חדש, נשמר התיאור המקורי")
        
        # Update screenshots
        if 'screenshots' in data:
            app['screenshots'] = data['screenshots']
            screenshots_updated += 1
            print(f"  ✅ נמצאו {len(data['screenshots'])} צילומי מסך")
        else:
            # Keep existing screenshots if any, or empty list
            if 'screenshots' not in app:
                app['screenshots'] = []
            print(f"  ⚠️ לא נמצאו צילומי מסך")
        
        # השהיה בין בקשות (לא אחרי האחרונה)
        if i < len(apps):
            print(f"  ⏳ ממתין {delay} שניות...")
            time.sleep(delay)
    
    # שמירת הפלט
    output_path = Path(output_file)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(apps, f, ensure_ascii=False, indent=2)
    
    print(f"\n🎉 בוצע בהצלחה!")
    print(f"   • {desc_updated} תיאורים עודכנו")
    print(f"   • {len(apps) - desc_updated} תיאורים נשארו ללא שינוי")
    print(f"   • {screenshots_updated} אפליקציות עם צילומי מסך")
    print(f"   • הפלט נשמר ב-{output_file}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="עדכון תיאורים וצילומי מסך מ-Google Play Store (עברית)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
דוגמה:
  python update_descriptions.py
  python update_descriptions.py -i my_apps.json -o updated.json -d 3
        """
    )
    
    parser.add_argument(
        '-i', '--input',
        default='apps.json',
        help='קובץ קלט JSON (ברירת מחדל: apps.json)'
    )
    
    parser.add_argument(
        '-o', '--output',
        default='apps_updated.json',
        help='קובץ פלט JSON (ברירת מחדל: apps_updated.json)'
    )
    
    parser.add_argument(
        '-d', '--delay',
        type=float,
        default=2.0,
        help='השהיה בשניות בין בקשות (ברירת מחדל: 2)'
    )
    
    args = parser.parse_args()
    
    update_apps_data(
        input_file=args.input,
        output_file=args.output,
        delay=args.delay
    )