import os
from dotenv import load_dotenv
import psycopg

load_dotenv()

dbpassword = os.getenv("password")

def getConnection():
    return psycopg.connect(
        host = "localhost",
        port=5432,
        dbname="itsm_database",
        user="postgres",
        password=dbpassword
        )
