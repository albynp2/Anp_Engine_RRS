from database.database import get_connection, DB_PATH

conn = get_connection()
print(f"Database: {DB_PATH}")
cursor = conn.cursor()

cursor.execute("SELECT * FROM stories")

rows = cursor.fetchall()

for row in rows:
    print(row)

conn.close()