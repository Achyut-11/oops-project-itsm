import psycopg

with psycopg.connect(
    host="localhost",
    port=5432,
    dbname="itsm_database",
    user="postgres",
    password="Achhyut"
) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM incidents;")
        print(cur.fetchone())

print("Database connection successful!")