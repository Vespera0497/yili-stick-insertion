# -*- coding: utf-8 -*-
"""
本地推送：上位机 -> 监控看板（S3）
协议 §七 允许 WebSocket / 本地 HTTP / 共享 SQLite 三选一。
选 **共享 SQLite** 的理由：本机未装 websockets（需联网装），SQLite 是 Python 内置、
零依赖，且看板可只读访问、天然留痕。用 WAL 模式让"写"不阻塞"读"。
"""
import os, json, sqlite3, time, threading

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stickinsert.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS state (
  id INTEGER PRIMARY KEY CHECK (id=1),
  ts REAL, seq INTEGER, mode INTEGER, mode_name TEXT, dio INTEGER,
  cnt INTEGER, cyc_ms INTEGER, tmp_d01c INTEGER, prs_d01kpa INTEGER,
  lost_frames INTEGER, source TEXT
);
CREATE TABLE IF NOT EXISTS state_history (
  ts REAL, seq INTEGER, mode INTEGER, cnt INTEGER, cyc_ms INTEGER, dio INTEGER
);
CREATE TABLE IF NOT EXISTS events (
  ts REAL, evt INTEGER, evt_name TEXT, evt_seq INTEGER, par INTEGER
);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


class PushHub:
    def __init__(self, db_path=DEFAULT_DB, keep_history=20000):
        self.db_path = db_path
        self.keep = keep_history
        self._lock = threading.Lock()
        self._con = sqlite3.connect(db_path, check_same_thread=False)
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA synchronous=NORMAL")
        self._con.executescript(_SCHEMA)
        self._con.commit()

    def push_state(self, d: dict, lost=0):
        with self._lock:
            now = time.time()
            self._con.execute("INSERT OR REPLACE INTO state VALUES (1,?,?,?,?,?,?,?,?,?,?,?)",
                              (now, d["SEQ"], d["MODE"], d["MODE_NAME"], d["DIO_RAW"],
                               d["CNT"], d["CYC_MS"], d["TMP_D01C"], d["PRS_D01KPA"], lost, "host_pc"))
            self._con.execute("INSERT INTO state_history(ts,seq,mode,cnt,cyc_ms,dio) VALUES (?,?,?,?,?,?)",
                              (now, d["SEQ"], d["MODE"], d["CNT"], d["CYC_MS"], d["DIO_RAW"]))
            self._con.execute("INSERT OR REPLACE INTO meta VALUES ('updated_at',?)", (repr(now),))
            self._con.commit()

    def push_event(self, d: dict):
        with self._lock:
            self._con.execute("INSERT INTO events(ts,evt,evt_name,evt_seq,par) VALUES (?,?,?,?,?)",
                              (time.time(), d["EVT"], d["EVT_NAME"], d["EVT_SEQ"], d["PAR"]))
            self._con.commit()

    def set_comms(self, connected: bool, port: str = ""):
        with self._lock:
            self._con.execute("INSERT OR REPLACE INTO meta VALUES ('comms',?)",
                              (json.dumps({"connected": connected, "port": port,
                                           "ts": time.time()}),))
            self._con.commit()

    def trim(self):
        """历史表封顶，防长跑撑爆磁盘。"""
        with self._lock:
            n = self._con.execute("SELECT COUNT(*) FROM state_history").fetchone()[0]
            if n > self.keep:
                self._con.execute(
                    "DELETE FROM state_history WHERE rowid NOT IN "
                    "(SELECT rowid FROM state_history ORDER BY rowid DESC LIMIT ?)", (self.keep,))
                self._con.commit()
            return n

    def close(self):
        with self._lock:
            self._con.close()


if __name__ == "__main__":
    import binascii
    import protocol as P
    ST = binascii.unhexlify("AA550E0107018900D20400006C02FB00F503D7")
    EV = binascii.unhexlify("AA55060201D204000000DF")
    hub = PushHub()
    hub.push_state(P.decode_state(P.Parser().feed(ST)[0].payload))
    hub.push_event(P.decode_event(P.Parser().feed(EV)[0].payload))
    hub.set_comms(False, "SIMULATE")
    print("db:", hub.db_path)
    print("state :", hub._con.execute(
        "SELECT seq,mode_name,cnt,cyc_ms,tmp_d01c,prs_d01kpa FROM state").fetchone())
    print("events:", hub._con.execute("SELECT evt_name,evt_seq,par FROM events").fetchall())
    print("meta  :", hub._con.execute("SELECT k,v FROM meta").fetchall())
    hub.close()
