import sqlite3
from pathlib import Path
DB = Path(__file__).with_name('security.sqlite3')
def connect():
    c = sqlite3.connect(DB)
    c.execute('CREATE TABLE IF NOT EXISTS incidents (id INTEGER PRIMARY KEY, speaker TEXT, event TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS transfers (id TEXT PRIMARY KEY, speaker TEXT, amount INTEGER, recipient TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)')
    return c
def incident(speaker, event):
    with connect() as c: c.execute('INSERT INTO incidents(speaker,event) VALUES (?,?)',(speaker,event))
def transfer(id, speaker, amount, recipient):
    with connect() as c: c.execute('INSERT INTO transfers(id,speaker,amount,recipient) VALUES (?,?,?,?)',(id,speaker,amount,recipient))
