#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.connection import connection, is_postgres


month_expr = "TO_CHAR(timestamp, 'YYYY-MM')" if is_postgres() else "strftime('%Y-%m', timestamp)"

with connection(readonly=True) as conn:
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT {month_expr} AS month, COUNT(*) AS count
        FROM posts
        GROUP BY month
        ORDER BY month
    """)

    print("Posts per month:")
    for month, count in cursor.fetchall():
        print(f"{month}: {count}")

    print("\nComments per month:")
    cursor.execute(f"""
        SELECT {month_expr} AS month, COUNT(*) AS count
        FROM comments
        GROUP BY month
        ORDER BY month
    """)

    for month, count in cursor.fetchall():
        print(f"{month}: {count}")
