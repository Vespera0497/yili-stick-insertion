# -*- coding: utf-8 -*-
import sqlite3, os, urllib.parse
p = os.path.abspath(os.path.join("qt_gui", "host_pc", "stickinsert.db"))
print("path:", p, "exists:", os.path.exists(p), "size:", os.path.getsize(p))
fwd = p.replace(os.sep, "/")
for name, uri in (("plain-rw", None),
                  ("uri-raw", "file:" + fwd + "?mode=ro"),
                  ("uri-quoted", "file:" + urllib.parse.quote(fwd) + "?mode=ro")):
    try:
        con = sqlite3.connect(uri, uri=True, timeout=2) if uri else sqlite3.connect(p, timeout=2)
        n = con.execute("SELECT COUNT(*) FROM state_history").fetchone()[0]
        e = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        con.close()
        print(name, "OK  state_history =", n, " events =", e)
    except Exception as exc:
        print(name, "FAIL", type(exc).__name__, exc)
