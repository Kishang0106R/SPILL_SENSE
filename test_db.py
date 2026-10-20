import os
import psycopg
from dotenv import load_dotenv

# Load variables from the .env file in the project directory
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is missing. Check your .env file."
    )

try:
    with psycopg.connect(
        DATABASE_URL,
        connect_timeout=10
    ) as conn:

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT current_database(), current_user;"
            )

            result = cursor.fetchone()

            if result is None:
                raise RuntimeError("No database result returned.")

            database, user = result

            print("PostgreSQL connection successful!")
            print("Database:", database)
            print("User:", user)

except Exception as error:
    print("PostgreSQL connection failed.")
    print("Error:", error)