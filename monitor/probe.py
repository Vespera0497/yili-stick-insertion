# -*- coding: utf-8 -*-
import sys, os, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app
print("DB =", app.DB)
print("exists =", os.path.exists(app.DB), " cwd =", os.getcwd())
print("wal exists =", os.path.exists(app.DB + "-wal"), " shm exists =", os.path.exists(app.DB + "-shm"))
try:
    con = app.ro(); print("ro() OK"); con.close()
except Exception:
    traceback.print_exc()
try:
    r = app.api_state()
    print("api_state ok =", r.get("ok"), " mode =", r.get("mode_name"), " cnt =", r.get("cnt"),
          " fresh =", r.get("fresh"))
except Exception:
    traceback.print_exc()
