#!/usr/bin/env python3
import sqlite3
from datetime import datetime

db_path = "historical_reddit_data.db"

with sqlite3.connect(db_path) as conn:
    cursor = conn.cursor()
    
    # Posts per year/month
    cursor.execute('''
        SELECT strftime('%Y-%m', timestamp) as month, COUNT(*) as count 
        FROM posts 
        GROUP BY month 
        ORDER BY month
    ''')
    
    print("Posts per month:")
    for month, count in cursor.fetchall():
        print(f"{month}: {count}")
    
    print("\nComments per month:")
    cursor.execute('''
        SELECT strftime('%Y-%m', timestamp) as month, COUNT(*) as count 
        FROM comments 
        GROUP BY month 
        ORDER BY month
    ''')
    
    for month, count in cursor.fetchall():
        print(f"{month}: {count}")
