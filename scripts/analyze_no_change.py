import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "core"))
import config

db = sqlite3.connect(str(config.WORKSPACE_DIR / "workspace.db"))
db.row_factory = sqlite3.Row

same = db.execute("SELECT COUNT(*) FROM rows WHERE change_type = 'no_change' AND draft = translation").fetchone()[0]
diff = db.execute("SELECT COUNT(*) FROM rows WHERE change_type = 'no_change' AND draft != translation").fetchone()[0]
total_no = db.execute("SELECT COUNT(*) FROM rows WHERE change_type = 'no_change'").fetchone()[0]
print(f'no_change total: {total_no}')
print(f'  draft == translation: {same}')
print(f'  draft != translation: {diff} (false negatives)')

other = db.execute("SELECT COUNT(*) FROM rows WHERE draft = translation AND change_type != 'no_change'").fetchone()[0]
print(f'draft == translation but change_type != no_change: {other} (false positives)')

db.close()
