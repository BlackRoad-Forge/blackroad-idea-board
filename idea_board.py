#!/usr/bin/env python3
"""BlackRoad Idea Board – capture, develop, and prioritize ideas."""

import argparse, json, os, random, sqlite3, sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import List, Optional

GREEN  = "\033[0;32m"; RED    = "\033[0;31m"; YELLOW = "\033[1;33m"
CYAN   = "\033[0;36m"; BOLD   = "\033[1m";    NC     = "\033[0m"
def ok(m):   print(f"{GREEN}✓{NC} {m}")
def err(m):  print(f"{RED}✗{NC} {m}", file=sys.stderr)
def info(m): print(f"{CYAN}ℹ{NC} {m}")
def warn(m): print(f"{YELLOW}⚠{NC} {m}")

DB_PATH    = os.path.expanduser("~/.blackroad-personal/idea_board.db")
CATEGORIES = ("product", "tech", "content", "business", "personal")
STATUSES   = ("captured", "exploring", "validating", "building", "shipped", "archived")

@dataclass
class Idea:
    id: int
    title: str
    description: str
    category: str
    status: str
    priority: int
    votes: int
    notes_json: str
    links_json: str
    created_at: str
    shipped_result: str = ""

    @property
    def notes(self) -> List[str]:
        return json.loads(self.notes_json or "[]")

    @property
    def links(self) -> List[str]:
        return json.loads(self.links_json or "[]")

    @property
    def score(self) -> float:
        return self.votes * self.priority

def get_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ideas (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            title          TEXT NOT NULL,
            description    TEXT NOT NULL DEFAULT '',
            category       TEXT NOT NULL DEFAULT 'tech',
            status         TEXT NOT NULL DEFAULT 'captured',
            priority       INTEGER NOT NULL DEFAULT 3,
            votes          INTEGER NOT NULL DEFAULT 0,
            notes_json     TEXT NOT NULL DEFAULT '[]',
            links_json     TEXT NOT NULL DEFAULT '[]',
            created_at     TEXT NOT NULL,
            shipped_result TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS idea_notes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            idea_id    INTEGER NOT NULL REFERENCES ideas(id),
            content    TEXT NOT NULL,
            timestamp  TEXT NOT NULL
        );
    """)
    conn.commit()
    return conn

def row_to_idea(row) -> Idea:
    d = dict(row)
    return Idea(**d)

STATUS_ICON = {
    "captured":   "💡", "exploring":  "🔍", "validating": "🧪",
    "building":   "🔨", "shipped":    "🚀", "archived":   "📦",
}
CATEGORY_ICON = {
    "product":"📦","tech":"⚙️","content":"✍️","business":"💼","personal":"🌱"
}
PRIORITY_STARS = {1:"★☆☆☆☆",2:"★★☆☆☆",3:"★★★☆☆",4:"★★★★☆",5:"★★★★★"}

def print_idea(idea: Idea, detail=False):
    icon = STATUS_ICON.get(idea.status,"?")
    cat  = CATEGORY_ICON.get(idea.category,"?")
    stars = PRIORITY_STARS.get(idea.priority,"?")
    print(f"\n{icon} [{idea.id:>4}] {CYAN}{idea.title}{NC}")
    print(f"       {cat} {idea.category:<12}  {stars}  votes={idea.votes}  score={idea.score:.0f}")
    print(f"       status: {idea.status}  created: {idea.created_at[:10]}")
    if detail:
        if idea.description: print(f"       {idea.description}")
        if idea.notes:
            print(f"  {BOLD}Notes:{NC}")
            for n in idea.notes: print(f"    • {n}")
        if idea.links:
            print(f"  {BOLD}Links:{NC}")
            for l in idea.links: print(f"    🔗 {l}")
        if idea.shipped_result:
            print(f"  {GREEN}Shipped:{NC} {idea.shipped_result}")

def cmd_capture(args):
    db = get_db()
    if args.category not in CATEGORIES:
        err(f"Category must be one of: {', '.join(CATEGORIES)}"); sys.exit(1)
    now = datetime.now().isoformat()
    cur = db.execute("""
        INSERT INTO ideas(title,description,category,status,priority,votes,
            notes_json,links_json,created_at)
        VALUES(?,?,?,?,?,?,?,?,?)
    """, (args.title, args.description or "", args.category, "captured",
          args.priority or 3, 0, "[]", "[]", now))
    db.commit()
    ok(f"Idea #{cur.lastrowid} captured: {args.title}")

def cmd_develop(args):
    db  = get_db()
    row = db.execute("SELECT * FROM ideas WHERE id=?", (args.idea_id,)).fetchone()
    if not row:
        err(f"Idea #{args.idea_id} not found"); return
    idea  = row_to_idea(row)
    notes = idea.notes + [args.note]
    db.execute("UPDATE ideas SET notes_json=? WHERE id=?", (json.dumps(notes), args.idea_id))
    ts = datetime.now().isoformat()
    db.execute("INSERT INTO idea_notes(idea_id,content,timestamp) VALUES(?,?,?)",
               (args.idea_id, args.note, ts))
    db.commit()
    ok(f"Note added to idea #{args.idea_id}")

def cmd_vote(args):
    db = get_db()
    db.execute("UPDATE ideas SET votes=votes+1 WHERE id=?", (args.idea_id,))
    db.commit()
    row = db.execute("SELECT votes FROM ideas WHERE id=?", (args.idea_id,)).fetchone()
    if row: ok(f"Idea #{args.idea_id} now has {row['votes']} vote(s)")

def cmd_update_status(args):
    if args.status not in STATUSES:
        err(f"Status must be one of: {', '.join(STATUSES)}"); sys.exit(1)
    db = get_db()
    db.execute("UPDATE ideas SET status=? WHERE id=?", (args.status, args.idea_id))
    db.commit()
    ok(f"Idea #{args.idea_id} → {args.status}")

def cmd_prioritize(args):
    db  = get_db()
    rows = db.execute(
        "SELECT * FROM ideas WHERE status NOT IN ('shipped','archived') ORDER BY (votes*priority) DESC"
    ).fetchall()
    if not rows:
        warn("No active ideas"); return
    print(f"\n{BOLD}Top ideas by score (votes × priority):{NC}")
    for row in rows[:args.limit or 10]:
        idea = row_to_idea(row)
        print_idea(idea)

def cmd_daily_review(args):
    db   = get_db()
    rows = db.execute(
        "SELECT * FROM ideas WHERE status='exploring' ORDER BY RANDOM() LIMIT 3"
    ).fetchall()
    if not rows:
        warn("No ideas in 'exploring' status")
        info("Use `capture` and then `update-status <id> exploring` to add some"); return
    print(f"\n{BOLD}Daily review — 3 random ideas to explore:{NC}")
    for row in rows:
        print_idea(row_to_idea(row), detail=True)

def cmd_ship(args):
    db  = get_db()
    row = db.execute("SELECT * FROM ideas WHERE id=?", (args.idea_id,)).fetchone()
    if not row:
        err(f"Idea #{args.idea_id} not found"); return
    db.execute("UPDATE ideas SET status='shipped', shipped_result=? WHERE id=?",
               (args.result or "", args.idea_id))
    db.commit()
    ok(f"🚀 Idea #{args.idea_id} shipped!")
    if args.result: print(f"   Result: {args.result}")

def cmd_archive_old(args):
    db   = get_db()
    days = args.days or 90
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = db.execute(
        "SELECT id,title FROM ideas WHERE status='captured' AND created_at < ?", (cutoff,)
    ).fetchall()
    for row in rows:
        db.execute("UPDATE ideas SET status='archived' WHERE id=?", (row["id"],))
        warn(f"Archived old captured idea #{row['id']}: {row['title']}")
    db.commit()
    ok(f"Archived {len(rows)} stale idea(s)")

def cmd_show(args):
    db  = get_db()
    row = db.execute("SELECT * FROM ideas WHERE id=?", (args.id,)).fetchone()
    if not row:
        err(f"Idea #{args.id} not found"); return
    print_idea(row_to_idea(row), detail=True)

def cmd_list(args):
    db     = get_db()
    where  = ""
    params = []
    if args.status:   where += " AND status=?";   params.append(args.status)
    if args.category: where += " AND category=?"; params.append(args.category)
    rows = db.execute(f"SELECT * FROM ideas WHERE 1=1{where} ORDER BY (votes*priority) DESC LIMIT 30",
                      params).fetchall()
    if not rows:
        warn("No ideas found"); return
    for row in rows: print_idea(row_to_idea(row))

def cmd_add_link(args):
    db  = get_db()
    row = db.execute("SELECT * FROM ideas WHERE id=?", (args.idea_id,)).fetchone()
    if not row:
        err(f"Idea #{args.idea_id} not found"); return
    idea  = row_to_idea(row)
    links = idea.links + [args.url]
    db.execute("UPDATE ideas SET links_json=? WHERE id=?", (json.dumps(links), args.idea_id))
    db.commit()
    ok(f"Link added to idea #{args.idea_id}")

def main():
    parser = argparse.ArgumentParser(prog="br-ideas", description="BlackRoad Idea Board")
    sub    = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("capture"); p.add_argument("title")
    p.add_argument("--description","-d",default="")
    p.add_argument("--category","-c",default="tech",choices=CATEGORIES)
    p.add_argument("--priority","-p",type=int,default=3,choices=range(1,6))
    p.set_defaults(func=cmd_capture)

    p = sub.add_parser("develop"); p.add_argument("idea_id",type=int); p.add_argument("note")
    p.set_defaults(func=cmd_develop)

    p = sub.add_parser("vote"); p.add_argument("idea_id",type=int); p.set_defaults(func=cmd_vote)

    p = sub.add_parser("status"); p.add_argument("idea_id",type=int); p.add_argument("status",choices=STATUSES)
    p.set_defaults(func=cmd_update_status)

    p = sub.add_parser("prioritize"); p.add_argument("--limit",type=int,default=10)
    p.set_defaults(func=cmd_prioritize)

    sub.add_parser("daily-review").set_defaults(func=cmd_daily_review)

    p = sub.add_parser("ship"); p.add_argument("idea_id",type=int); p.add_argument("--result",default="")
    p.set_defaults(func=cmd_ship)

    p = sub.add_parser("archive-old"); p.add_argument("--days",type=int,default=90)
    p.set_defaults(func=cmd_archive_old)

    p = sub.add_parser("show"); p.add_argument("id",type=int); p.set_defaults(func=cmd_show)

    p = sub.add_parser("list"); p.add_argument("--status",default=None,choices=STATUSES)
    p.add_argument("--category",default=None,choices=CATEGORIES); p.set_defaults(func=cmd_list)

    p = sub.add_parser("add-link"); p.add_argument("idea_id",type=int); p.add_argument("url")
    p.set_defaults(func=cmd_add_link)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
