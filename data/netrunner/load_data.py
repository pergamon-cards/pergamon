import json
import os
import sqlite3

game = 'netrunner'

cwd = os.getcwd()
data_dir = os.path.join(cwd, 'netrunner-cards-json', 'pack')
db_sqlite_path = os.path.join(os.path.dirname(cwd), 'cards.sqlite')

cards = []

for entry in os.scandir(data_dir):
    if entry.path.endswith('.json'):
        with open(entry.path) as file:
            cards += json.load(file)

print(len(cards))

print(db_sqlite_path)

conn = sqlite3.connect(db_sqlite_path)
cur = conn.cursor()

# create table if it doesn't exist
cur.execute("""
    CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY,
        game TEXT,
        title TEXT,
        card TEXT -- json
    )
""")

# create row data
row_data = [(None, game, c['title'], json.dumps(c)) for c in cards]

# delete any existing data for this game
cur.execute("DELETE FROM cards WHERE game='netrunner'")
conn.commit()

# insert data
cur.executemany("INSERT INTO cards VALUES (?, ?, ?, ?)", row_data)
conn.commit()

conn.close()

# verify
conn = sqlite3.connect(db_sqlite_path)
cur = conn.cursor()

res = cur.execute("SELECT count(*) FROM cards")
print(res.fetchone())

res = cur.execute("SELECT * FROM cards LIMIT 1")
print(res.fetchone())

conn.close()
