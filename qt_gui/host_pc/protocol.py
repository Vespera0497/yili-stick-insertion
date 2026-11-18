# -*- coding: utf-8 -*-
"""
三棒签 · 8051 <-> PC UART 字节协议实现（严格照 doc/UART_PROTOCOL_v1.md v1.0）

本模块不依赖 Qt / pyserial，可单独跑测试，也被 main.py / 监控看板复用。
注意：协议多字节字段一律**小端**；这里全部用显式位移，不做任何内存布局假设。
"""
from __future__ import annotations

# ---- 帧常量（协议 §2）----
SYNC0, SYNC1 = 0xAA, 0x55
LEN_MIN, LEN_MAX = 1, 15
MAX_FRAME = 2 + 1 + 1 + LEN_MAX + 1          # 20

# ---- TYPE（协议 §3）----
T_STATE, T_EVENT, T_ACK = 0x01, 0x02, 0x03
T_CMD = 0x81
def is_uplink(t: int) -> bool: return (t & 0x80) == 0

# ---- MODE（协议 §4）----
MODES = {0: "IDLE 停机", 1: "RUNNING 运行", 2: "ESTOP 急停", 3: "FAULT 告警"}

# ---- DIO 位（协议 §4）----
DIO_BITS = [("YV1", 0), ("YV2", 1), ("YV3", 2),
            ("SQ1", 3), ("SQ2", 4), ("SQ3", 5),
            ("SB1", 6), ("LED_RUN", 7), ("LED_ALARM", 8)]

# ---- 事件码（协议 §5）----
EVENTS = {0x01: "急停触发", 0x02: "到位超时", 0x03: "连续失败超限",
          0x04: "告警", 0x05: "复位完成"}
# ---- 命令码 / 结果码（协议 §6/§7）----
CMDS = {0x01: "启动", 0x02: "停止", 0x03: "复位", 0x04: "参数下装"}
RESULTS = {0x00: "已执行", 0x01: "命令无效", 0x02: "状态不允许", 0x03: "参数越界"}

# ---- 传感器未接哨兵（协议 §4）----
TMP_ABSENT, PRS_ABSENT = 0x7FFF, 0xFFFF


class Frame:
    __slots__ = ("type", "payload", "raw", "sum_ok")

    def __init__(self, ftype, payload, raw, sum_ok=True):
        self.type, self.payload, self.raw, self.sum_ok = ftype, bytes(payload), bytes(raw), sum_ok

    def hexstr(self):
        return " ".join("%02X" % b for b in self.raw)

    def __repr__(self):
        return "Frame(type=0x%02X len=%d sum_ok=%s)" % (self.type, len(self.payload), self.sum_ok)


# ============================ 发送侧 ============================
def build_frame(ftype: int, payload) -> bytes:
    payload = bytes(payload)
    if not (LEN_MIN <= len(payload) <= LEN_MAX):
        raise ValueError("LEN 必须在 %d..%d，收到 %d" % (LEN_MIN, LEN_MAX, len(payload)))
    s = (len(payload) + ftype + sum(payload)) & 0xFF
    return bytes([SYNC0, SYNC1, len(payload), ftype]) + payload + bytes([s])


def build_command(cmd: int, param: int = 0) -> bytes:
    """0x81 命令帧：CMD(1) + PARAM[2] 小端；无参命令 PARAM=0（协议 §6）。"""
    return build_frame(T_CMD, [cmd & 0xFF, param & 0xFF, (param >> 8) & 0xFF])


def _put16(v):  return [v & 0xFF, (v >> 8) & 0xFF]
def _put32(v):  return [(v >> s) & 0xFF for s in (0, 8, 16, 24)]


def build_state(seq, mode, dio, cnt, cyc, tmp=TMP_ABSENT, prs=PRS_ABSENT) -> bytes:
    """0x01 状态帧 14B（协议 §4），供测试与模拟器使用。"""
    pl = [seq & 0xFF, mode & 0xFF] + _put16(dio) + _put32(cnt) + _put16(cyc) + _put16(tmp) + _put16(prs)
    return build_frame(T_STATE, pl)


def build_event(evt, evt_seq, par=0) -> bytes:
    return build_frame(T_EVENT, [evt & 0xFF] + _put32(evt_seq) + [par & 0xFF])


# ============================ 解析侧 ============================
def decode_state(pl: bytes) -> dict:
    if len(pl) != 14:
        raise ValueError("状态帧 PAYLOAD 应为 14B，收到 %d" % len(pl))
    dio = pl[2] | (pl[3] << 8)
    cnt = int.from_bytes(pl[4:8], "little")
    cyc = pl[8] | (pl[9] << 8)
    tmp = pl[10] | (pl[11] << 8)
    prs = pl[12] | (pl[13] << 8)
    d = {
        "SEQ": pl[0],
        "MODE": pl[1],
        "MODE_NAME": MODES.get(pl[1], "未知(0x%02X)" % pl[1]),
        "CNT": cnt,
        "CYC_MS": cyc,
        "TMP_D01C": None if tmp == TMP_ABSENT else (tmp - 0x10000 if tmp >= 0x8000 else tmp),
        "PRS_D01KPA": None if prs == PRS_ABSENT else prs,
    }
    for name, bit in DIO_BITS:
        d[name] = bool((dio >> bit) & 1)
    d["DIO_RAW"] = dio
    return d


def decode_event(pl: bytes) -> dict:
    if len(pl) != 6:
        raise ValueError("事件帧 PAYLOAD 应为 6B，收到 %d" % len(pl))
    return {"EVT": pl[0], "EVT_NAME": EVENTS.get(pl[0], "未知(0x%02X)" % pl[0]),
            "EVT_SEQ": int.from_bytes(pl[1:5], "little"), "PAR": pl[5]}


def decode_ack(pl: bytes) -> dict:
    if len(pl) != 2:
        raise ValueError("应答帧 PAYLOAD 应为 2B，收到 %d" % len(pl))
    return {"CMD": pl[0], "CMD_NAME": CMDS.get(pl[0], "未知"), "RESULT": pl[1],
            "RESULT_NAME": RESULTS.get(pl[1], "未知")}


class Parser:
    """协议 §10 的 6 态同步状态机；feed() 可任意切分字节流。"""

    S_H0, S_H1, S_LEN, S_TYP, S_PAY, S_SUM = range(6)

    def __init__(self):
        self.st = self.S_H0
        self.len = 0
        self.idx = 0
        self.typ = 0
        self.sum = 0
        self.pl = bytearray()
        # 统计
        self.n_frames = 0
        self.n_sum_err = 0
        self.n_len_err = 0
        self.n_dir_err = 0

    def reset(self):
        self.st = self.S_H0

    def feed(self, data) -> list:
        out = []
        for b in bytes(data):
            f = self._step(b)
            if f is not None:
                out.append(f)
        return out

    def _step(self, b: int):
        if self.st == self.S_H0:
            return self._h0(b)
        if self.st == self.S_H1:
            return self._h1(b)
        if self.st == self.S_LEN:
            return self._len(b)
        if self.st == self.S_TYP:
            self.typ = b
            self.sum = (self.sum + b) & 0xFF
            self.st = self.S_PAY
            return None
        if self.st == self.S_PAY:
            self.pl.append(b)
            self.sum = (self.sum + b) & 0xFF
            self.idx += 1
            if self.idx >= self.len:
                self.st = self.S_SUM
            return None
        # S_SUM
        if b == self.sum:
            if not is_uplink(self.typ):
                self.n_dir_err += 1
                self.reset()
                return None
            self.n_frames += 1
            self.reset()
            return Frame(self.typ, self.pl,
                         bytes([SYNC0, SYNC1, self.len, self.typ]) + bytes(self.pl) + bytes([b]))
        self.n_sum_err += 1
        self.reset()
        return None

    def _h0(self, b):
        if b == SYNC0:
            self.st = self.S_H1
        return None

    def _h1(self, b):
        if b == SYNC1:
            self.st = self.S_LEN
            self.sum = 0
            self.idx = 0
            self.pl = bytearray()
        elif b != SYNC0:                 # AA 后不是 55 且不是 AA -> 重找
            self.st = self.S_H0
        return None

    def _len(self, b):
        if LEN_MIN <= b <= LEN_MAX:
            self.len = b
            self.sum = b
            self.st = self.S_TYP
        else:
            self.n_len_err += 1
            self.st = self.S_H0
        return None


def describe(f: Frame) -> str:
    if f.type == T_STATE:
        d = decode_state(f.payload)
        return "状态 SEQ=%d MODE=%s CNT=%d CYC=%dms TMP=%s PRS=%s | %s" % (
            d["SEQ"], d["MODE_NAME"], d["CNT"], d["CYC_MS"],
            "-" if d["TMP_D01C"] is None else "%.1f℃" % (d["TMP_D01C"] / 10.0),
            "-" if d["PRS_D01KPA"] is None else "%.1fkPa" % (d["PRS_D01KPA"] / 10.0),
            " ".join("%s=%d" % (n, int(d[n])) for n, _ in DIO_BITS))
    if f.type == T_EVENT:
        d = decode_event(f.payload)
        return "事件 %s(0x%02X) SEQ=%u PAR=%d" % (d["EVT_NAME"], d["EVT"], d["EVT_SEQ"], d["PAR"])
    if f.type == T_ACK:
        d = decode_ack(f.payload)
        return "应答 %s -> %s" % (d["CMD_NAME"], d["RESULT_NAME"])
    return "未知帧 type=0x%02X" % f.type
