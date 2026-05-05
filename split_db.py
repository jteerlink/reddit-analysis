#!/usr/bin/env python3
"""
Split historical_reddit_data.db:
- Keep AI-related subreddits in posts/comments
- Move all others to posts_other/comments_other

SQLite-only maintenance utility. Do not point this script at Neon/PostgreSQL.
"""

import shutil
import sqlite3
from pathlib import Path

DB_PATH = Path("/Users/jaredteerlink/repos/reddit-analyzer/historical_reddit_data.db")
BAK_PATH = DB_PATH.with_suffix(".db.bak")

AI_SUBREDDITS = {
    "ChatGPT", "OpenAI", "ClaudeAI", "AnthropicAI", "LocalLLaMA",
    "MachineLearning", "artificial", "ArtificialIntelligence", "DeepLearning",
    "AGI", "Singularity", "StableDiffusion", "AItools", "aiNews",
    "huggingface", "AIStartups", "DeepMind", "nvidia", "AIArt",
    "technology", "LLMDevs", "PromptEngineering", "Gemini", "datascience",
    "learnmachinelearning", "AutoGPT",
}

AI_SUBREDDIT_PARAMS = tuple(sorted(AI_SUBREDDITS))
AI_PLACEHOLDERS = ",".join("?" for _ in AI_SUBREDDIT_PARAMS)
NOT_IN_AI = f"subreddit NOT IN ({AI_PLACEHOLDERS})"


def counts(cur, table):
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0]


def per_sub_counts(cur, table):
    cur.execute(
        f"SELECT subreddit, COUNT(*) FROM {table} GROUP BY subreddit ORDER BY COUNT(*) DESC"
    )
    return cur.fetchall()


# ── Step 0: Backup ───────────────────────────────────────────────────────────
print(f"Backing up {DB_PATH.name} → {BAK_PATH.name} …")
shutil.copy2(DB_PATH, BAK_PATH)
print(f"  Backup size: {BAK_PATH.stat().st_size / 1_048_576:.1f} MB\n")

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
cur = conn.cursor()

# ── Step 1: Before counts per subreddit ─────────────────────────────────────
print("=" * 60)
print("STEP 1 — Row counts per subreddit (BEFORE)")
print("=" * 60)

for table in ("posts", "comments", "posts_other", "comments_other"):
    try:
        rows = per_sub_counts(cur, table)
        print(f"\n  [{table}] — {sum(r[1] for r in rows):,} total rows")
        for sub, n in rows:
            tag = "[AI]   " if sub in AI_SUBREDDITS else "[OTHER]"
            print(f"    {tag} {sub}: {n:,}")
    except sqlite3.OperationalError:
        print(f"\n  [{table}] — does not exist yet")

before = {}
for t in ("posts", "comments", "posts_other", "comments_other"):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (t,))
    if cur.fetchone():
        before[t] = counts(cur, t)
print(f"\nBefore totals: {before}\n")

# ── Step 2: (Re)create posts_other and comments_other ───────────────────────
print("=" * 60)
print("STEP 2 — (Re)creating posts_other and comments_other")
print("=" * 60)

conn.execute("DROP TABLE IF EXISTS posts_other")
conn.execute("DROP TABLE IF EXISTS comments_other")

conn.execute("""
    CREATE TABLE posts_other (
        id           TEXT PRIMARY KEY,
        title        TEXT NOT NULL,
        content      TEXT,
        upvotes      INTEGER,
        timestamp    DATETIME,
        subreddit    TEXT,
        author       TEXT,
        author_karma INTEGER,
        url          TEXT,
        num_comments INTEGER,
        content_type TEXT DEFAULT 'post',
        created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")

conn.execute("""
    CREATE TABLE comments_other (
        id           TEXT PRIMARY KEY,
        parent_id    TEXT,
        content      TEXT NOT NULL,
        upvotes      INTEGER,
        timestamp    DATETIME,
        subreddit    TEXT,
        author       TEXT,
        author_karma INTEGER,
        post_id      TEXT,
        content_type TEXT DEFAULT 'comment',
        created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()
print("  Tables created.\n")

# ── Step 3: Copy non-AI rows into *_other tables ─────────────────────────────
print("=" * 60)
print("STEP 3 — Copying non-AI rows to *_other tables")
print("=" * 60)

cur.execute(f"INSERT INTO posts_other SELECT * FROM posts WHERE {NOT_IN_AI}", AI_SUBREDDIT_PARAMS)
posts_moved = cur.rowcount
cur.execute(f"INSERT INTO comments_other SELECT * FROM comments WHERE {NOT_IN_AI}", AI_SUBREDDIT_PARAMS)
comments_moved = cur.rowcount
conn.commit()
print(f"  Copied {posts_moved:,} posts → posts_other")
print(f"  Copied {comments_moved:,} comments → comments_other\n")

# ── Step 4: Delete non-AI rows from original tables ──────────────────────────
print("=" * 60)
print("STEP 4 — Deleting non-AI rows from posts / comments")
print("=" * 60)

cur.execute(f"DELETE FROM posts WHERE {NOT_IN_AI}", AI_SUBREDDIT_PARAMS)
posts_deleted = cur.rowcount
cur.execute(f"DELETE FROM comments WHERE {NOT_IN_AI}", AI_SUBREDDIT_PARAMS)
comments_deleted = cur.rowcount
conn.commit()
print(f"  Deleted {posts_deleted:,} posts from posts")
print(f"  Deleted {comments_deleted:,} comments from comments\n")

assert posts_moved == posts_deleted, "Mismatch: posts moved vs deleted"
assert comments_moved == comments_deleted, "Mismatch: comments moved vs deleted"

# ── Step 5: VACUUM ────────────────────────────────────────────────────────────
print("=" * 60)
print("STEP 5 — VACUUM (reclaiming space)")
print("=" * 60)
conn.close()  # must close WAL before VACUUM from a fresh connection
conn = sqlite3.connect(DB_PATH)
conn.execute("VACUUM")
conn.commit()
print("  VACUUM complete.\n")

# ── Step 6: Final verification ───────────────────────────────────────────────
cur = conn.cursor()

print("=" * 60)
print("STEP 6 — Final verification")
print("=" * 60)

after = {t: counts(cur, t) for t in ("posts", "comments", "posts_other", "comments_other")}

for table, n in after.items():
    print(f"  {table}: {n:,} rows")

print()
print("Subreddit breakdown in posts (should be AI only):")
for sub, n in per_sub_counts(cur, "posts"):
    tag = "[AI]   " if sub in AI_SUBREDDITS else "[OTHER]"
    print(f"  {tag} {sub}: {n:,}")

print("\nSubreddit breakdown in comments (should be AI only):")
for sub, n in per_sub_counts(cur, "comments"):
    tag = "[AI]   " if sub in AI_SUBREDDITS else "[OTHER]"
    print(f"  {tag} {sub}: {n:,}")

conn.close()

db_size = DB_PATH.stat().st_size / 1_048_576
bak_size = BAK_PATH.stat().st_size / 1_048_576

print(f"\n{'=' * 60}")
print("SUMMARY")
print(f"{'=' * 60}")
print(f"  Backup:   {BAK_PATH.name}  ({bak_size:.1f} MB)")
print(f"  Database: {DB_PATH.name} ({db_size:.1f} MB)")
print(f"\n  Before → After:")
print(f"    posts:          {before.get('posts', 0):>7,} → {after['posts']:>7,}  (moved {posts_moved:,} non-AI)")
print(f"    comments:       {before.get('comments', 0):>7,} → {after['comments']:>7,}  (moved {comments_moved:,} non-AI)")
print(f"    posts_other:    {before.get('posts_other', 0):>7,} → {after['posts_other']:>7,}")
print(f"    comments_other: {before.get('comments_other', 0):>7,} → {after['comments_other']:>7,}")
print("\nDone.")
