# -*- coding: utf-8 -*-
"""
三棒签 · 监控 Web 看板（S3，独立于上位机，只读+记录，不反向写固件）
技术选型：Python 内置 http.server + 静态页 1s 轮询（零第三方依赖；
本机未装 Flask/FastAPI/websockets，指令 §1 允许实现方自定）。
数据源（只读）：qt_gui/host_pc/stickinsert.db —— S2 push.py 以 WAL 写入，
读侧用 file:...?mode=ro 打开，避免锁住上位机的写。
运行：python app.py   （默认 http://127.0.0.1:8765）
"""
import os, sys, json, time, sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.abspath(os.path.join(BASE, "..", "qt_gui", "host_pc", "stickinsert.db"))
PORT = int(os.environ.get("MON_PORT", "8765"))
STALE_SEC = 3.0          # updated_at 超过 3 秒没动 -> 判"数据未刷新"

MODES = {0: "IDLE 停机", 1: "RUNNING 运行", 2: "ESTOP 急停", 3: "FAULT 告警"}
DIO_BITS = [("YV1", 0), ("YV2", 1), ("YV3", 2), ("SQ1", 3), ("SQ2", 4), ("SQ3", 5),
            ("SB1", 6), ("LED_RUN", 7), ("LED_ALARM", 8)]
EVENTS = {1: "急停触发", 2: "到位超时", 3: "连续失败超限", 4: "告警", 5: "复位完成"}


def ro():
    """只读连接：优先 URI mode=ro；若库里残留 -wal/-shm（写进程异常退出所致），
    ro 连接无法创建 shm 会报 unable to open database file —— 此时退化为普通连接
    加 PRAGMA query_only=ON（SQL 层强制只读），看板可用且绝不写库。"""
    p = os.path.abspath(DB).replace(chr(92), "/")
    try:
        con = sqlite3.connect("file:%s?mode=ro" % p, uri=True, timeout=2)
        con.execute("SELECT 1")
    except sqlite3.OperationalError:
        con = sqlite3.connect(p, timeout=2)
        con.execute("PRAGMA query_only=ON")
    con.row_factory = sqlite3.Row
    return con


def day_stats(con, day_start):
    """当日产量 = 当日 state_history 里 CNT 最大-最小；平均节拍取 cyc_ms>0 的均值。"""
    rows = con.execute("SELECT ts, cnt, cyc_ms, mode FROM state_history WHERE ts>=? ORDER BY ts",
                       (day_start,)).fetchall()
    if not rows:
        return {"day_count": 0, "avg_cyc": None, "avail": None, "n": 0}
    cnts = [r["cnt"] for r in rows]
    cycs = [r["cyc_ms"] for r in rows if r["cyc_ms"] > 0]
    n = len(rows)
    ok_modes = sum(1 for r in rows if r["mode"] in (0, 1))
    return {"day_count": max(cnts) - min(cnts), "avg_cyc": round(sum(cycs) / len(cycs), 1) if cycs else None,
            "avail": round(ok_modes * 100.0 / n, 1), "n": n}


def alarm_count(con, day_start):
    return con.execute("SELECT COUNT(*) c FROM events WHERE ts>=? AND evt IN (1,2,3,4)",
                       (day_start,)).fetchone()["c"]


def api_state():
    con = ro()
    try:
        s = con.execute("SELECT * FROM state WHERE id=1").fetchone()
        meta = {r["k"]: r["v"] for r in con.execute("SELECT k,v FROM meta").fetchall()}
        if s is None:
            return {"ok": False, "reason": "数据库还没有状态行（上位机未运行？）"}
        updated = float(meta.get("updated_at", "0") or 0)
        day0 = time.time() - (time.time() % 86400) - 8 * 3600   # 当日 0 点（UTC+8 近似）
        dio = s["dio"] or 0
        io = {name: bool((dio >> bit) & 1) for name, bit in DIO_BITS}
        timeouts = con.execute("SELECT COUNT(*) c FROM events WHERE evt IN (2,3) AND ts>=?",
                               (day0,)).fetchone()["c"]
        st = day_stats(con, day0)
        # 简化 OEE = 可用率 x 良率（软件口径，定义见页面说明；协议 §2.4 允许软件算）
        quality = round(100.0 * s["cnt"] / (s["cnt"] + timeouts), 1) if (s["cnt"] + timeouts) else None
        oee = round(st["avail"] * quality / 100.0, 1) if (st["avail"] is not None and quality is not None) else None
        return {"ok": True, "now": time.time(), "stale_sec": round(time.time() - updated, 1),
                "fresh": (time.time() - updated) < STALE_SEC,
                "seq": s["seq"], "mode": s["mode"], "mode_name": MODES.get(s["mode"], "?"),
                "dio": dio, "io": io,
                "cnt": s["cnt"], "cyc_ms": s["cyc_ms"],
                "tmp": None if s["tmp_d01c"] is None else s["tmp_d01c"] / 10.0,
                "prs": None if s["prs_d01kpa"] is None else s["prs_d01kpa"] / 10.0,
                "lost": s["lost_frames"],
                "comms": json.loads(meta["comms"]) if "comms" in meta else {},
                "day_count": st["day_count"], "avg_cyc": st["avg_cyc"], "avail": st["avail"],
                "quality": quality, "oee": oee, "alarms_today": alarm_count(con, day0),
                "hist_rows": st["n"]}
    finally:
        con.close()


def api_events(after):
    con = ro()
    try:
        rows = con.execute("SELECT rowid id, ts, evt, evt_name, evt_seq, par FROM events "
                           "WHERE rowid>? ORDER BY rowid DESC LIMIT 200", (after,)).fetchall()
        last = con.execute("SELECT COALESCE(MAX(rowid),0) m FROM events").fetchone()["m"]
        return {"ok": True, "last_id": last,
                "events": [{"id": r["id"], "time": time.strftime("%m-%d %H:%M:%S", time.localtime(r["ts"])),
                            "evt": r["evt"], "name": r["evt_name"], "seq": r["evt_seq"], "par": r["par"]}
                           for r in rows]}
    finally:
        con.close()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):      # 静默访问日志
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            if self.path.startswith("/api/state"):
                b = json.dumps(api_state(), ensure_ascii=False).encode("utf-8")
                self._send(200, b, "application/json; charset=utf-8")
            elif self.path.startswith("/api/events"):
                after = 0
                q = self.path.split("?", 1)
                if len(q) == 2 and "after=" in q[1]:
                    try: after = int(q[1].split("after=")[1].split("&")[0])
                    except ValueError: after = 0
                b = json.dumps(api_events(after), ensure_ascii=False).encode("utf-8")
                self._send(200, b, "application/json; charset=utf-8")
            elif self.path in ("/", "/index.html"):
                with open(os.path.join(BASE, "index.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            else:
                self._send(404, b"{}", "application/json")
        except Exception as e:
            b = json.dumps({"ok": False, "reason": str(e)}, ensure_ascii=False).encode("utf-8")
            self._send(500, b, "application/json; charset=utf-8")


if __name__ == "__main__":
    port = PORT
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    print("监控看板: http://127.0.0.1:%d   (只读 %s)" % (port, os.path.abspath(DB)))
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
