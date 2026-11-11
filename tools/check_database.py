from database.database import get_connection, DB_PATH

conn = get_connection()
print(f"Database: {DB_PATH}")
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM stories")

count = cursor.fetchone()[0]

print(f"Total stories: {count}")

conn.close()