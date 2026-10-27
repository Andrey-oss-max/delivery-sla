import sqlite3


class Store:
    """Хранилище SQLite в памяти (или в файле) с минимальным набором операций."""

    def __init__(self, path=":memory:"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def execute(self, sql, params=()):
        self.conn.execute(sql, params)
        self.conn.commit()

    def insert_many(self, sql, rows):
        self.conn.executemany(sql, rows)
        self.conn.commit()

    def query(self, sql, params=()):
        return [dict(r) for r in self.conn.execute(sql, params)]
