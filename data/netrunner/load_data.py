import json
import os
import psycopg

# db_table = "cards"
# db_user = "postgres"
# db_pass = "postgres"
# db_host = "localhost"
# db_port = 16825
# db_name = "pergamon"

db_table = "cards"
db_user = "<shuttle-user>"
db_pass = "<shuttle-password>"
db_host = "<shuttle-host>"
db_port = 5432
db_name = "<shuttle-db>"

game = 'netrunner'

cwd = os.getcwd()
data_dir = os.path.join(cwd, 'netrunner-cards-json', 'pack')

cards = []

for entry in os.scandir(data_dir):
    if entry.path.endswith('.json'):
        with open(entry.path) as file:
            cards += json.load(file)

print(len(cards))

db_psycopg_connection_string = f"host={db_host} port={db_port} dbname={db_name} user={db_user} password={db_pass}"
print(db_psycopg_connection_string)

# create row data
row_data = [(game, c['title'], json.dumps(c)) for c in cards]

with psycopg.connect(db_psycopg_connection_string) as conn:
    with conn.cursor() as cur:
        # create table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                game TEXT,
                title TEXT,
                card TEXT -- json
            )
        """)
    
        # delete any existing data for this game
        cur.execute(f"DELETE FROM cards WHERE game='{game}'")
        
        # insert data
        cur.executemany("INSERT INTO cards(game, title, card) VALUES (%s, %s, %s)", row_data)

# verify
with psycopg.connect(db_psycopg_connection_string) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM cards")
        print(cur.fetchone())
    
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM cards WHERE game='{game}' LIMIT 1")
        print(cur.fetchone())
