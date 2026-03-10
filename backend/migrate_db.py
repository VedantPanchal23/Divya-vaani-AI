import sqlite3
from pathlib import Path

db_path = Path("data/divyavaani.db")

print(f"Connecting to database: {db_path.absolute()}")
if not db_path.exists():
    print("Database file not found!")
    exit(1)

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Try adding the youtube_id column
    cursor.execute("ALTER TABLE videos ADD COLUMN youtube_id VARCHAR(50);")
    conn.commit()
    print("✅ Successfully added 'youtube_id' column to 'videos' table.")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
         print("✅ Column 'youtube_id' already exists.")
    else:
        print(f"❌ Error adding column: {e}")
finally:
    conn.close()
