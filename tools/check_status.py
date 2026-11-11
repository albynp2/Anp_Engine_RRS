from database.database import get_connection, DB_PATH

conn = get_connection()
print(f"Database: {DB_PATH}")
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM stories")
count = cursor.fetchone()[0]

print(f"\nTotal stories: {count}\n")

# cursor.execute("""
#     SELECT id, title, source, published, status
#     FROM stories
#     ORDER BY id DESC
#     LIMIT 10
# """)

# rows = cursor.fetchall()

# for row in rows:
#     print(f"ID     : {row[0]}")
#     print(f"Title  : {row[1]}")
#     print(f"Source : {row[2]}")
#     print(f"Date   : {row[3]}")
#     print(f"Status : {row[4]}")
#     print("-" * 60)

conn.close()