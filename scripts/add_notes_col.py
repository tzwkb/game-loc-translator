import sqlite3, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "core"))
import config

db = sqlite3.connect(str(config.WORKSPACE_DIR / "workspace.db"))
try:
    db.execute("ALTER TABLE rows ADD COLUMN notes TEXT DEFAULT ''")
    db.commit()
    print("Added notes column")
except sqlite3.OperationalError as e:
    print(e)
db.close()
