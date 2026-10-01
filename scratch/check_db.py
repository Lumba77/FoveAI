import sqlite3

db_path = (
    r"C:\Users\danie\AppData\Roaming\Antigravity IDE\User\globalStorage\state.vscdb"
)
try:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM ItemTable WHERE key LIKE '%papillon%'")
    rows = cur.fetchall()
    print("Found keys in state.vscdb:", len(rows))
    for r in rows:
        val = r[1][:80] if isinstance(r[1], str) else str(r[1])[:80]
        print(f" - {r[0]}: {val}")
    conn.close()
except Exception as e:
    print("SQLite check:", e)
