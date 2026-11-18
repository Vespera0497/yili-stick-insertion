# -*- coding: utf-8 -*-
"""
三棒签插签设备 · PC 上位机（S2）—— Tkinter 回退版
背景：本机 PySide6 6.12.0 的 QtCore DLL 加载失败（环境缺陷，非代码缺陷），
PyQt5 未安装；tkinter 为 Python 内置、零依赖。功能与 Qt 版 main.py 一一对应：
  串口枚举/自动连（优先 CH340/CP2102）、启动/停止/复位/参数下装、
  实时状态 + 九位 IO 指示灯、事件日志、SEQ 跳号丢帧统计、
  >500ms 无合法上行帧判通信中断、SQLite 推送（复用 push.py，S3 看板数据源）。

运行：
  python main_tk.py                 正常启动，自动枚举并尝试连 CH340/CP2102
  python main_tk.py --simulate      无硬件演示：回放 R1 协议示例帧 + 合成工作循环
  python main_tk.py --selftest      构建界面、注入示例状态帧、截屏 host_tk_selftest.png 后退出
日常建议直接 python start.py（自动选后端）。
"""
import os, sys, time, argparse, binascii

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import protocol as P
import tkinter as tk
from tkinter import ttk

try:
    import serial
    from serial.tools import list_ports
    HAVE_SERIAL = True
except Exception:
    HAVE_SERIAL = False

BRIDGE_VIDPID = {(0x1A86, 0x7523): "CH340", (0x10C4, 0xEA60): "CP2102",
                 (0x1A86, 0x7522): "CH340", (0x067B, 0x2303): "PL2303"}
STALE_MS = 500          # 协议 §10.7：>500ms 无合法上行帧 -> 判通信中断
HIST_EVERY = 5
SAMPLE_STATE = "AA550E0107018900D20400006C02FB00F503D7"   # R1 §4 示例状态帧

C_ON, C_OFF, C_OK, C_ERR, C_IDLE = "#0a7a2f", "#9aa0a6", "#0a7a2f", "#b00020", "#666666"


def _enable_dpi_awareness():
    """进程内声明 DPI-aware：本机非 DPI-aware 进程坐标被虚拟化(×1.244)，
    导致 winfo 坐标与 ImageGrab 真实像素错位。仅影响本进程，不改系统设置。"""
    if sys.platform != "win32":
        return
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            from ctypes import windll
            windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class HostTk(object):
    def __init__(self, simulate=False):
        self.simulate = simulate
        self.ser = None
        self._port_map = {}
        self.parser = P.Parser()
        self.last_state = None
        self.last_rx_ts = 0.0
        self.prev_seq = None
        self.lost = 0
        self.frame_n = 0
        self.hub = None
        self._closed = False
        self._build()
        if simulate:
            self._sim_queue = self._build_sim_stream()
            self.log("[SIM] 无硬件演示模式：回放协议示例帧 + 合成工作循环")
        else:
            self._refresh_ports()
            self._autoconnect()
        self.root.after(20, self._loop)

    # ---------------- UI ----------------
    def _build(self):
        _enable_dpi_awareness()
        self.root = tk.Tk()
        self.root.title("三棒签插签设备 · 上位机")
        self.root.geometry("780x620")
        main = ttk.Frame(self.root, padding=8)
        main.pack(fill="both", expand=True)

        g1 = ttk.LabelFrame(main, text="连接", padding=6)
        g1.pack(fill="x")
        self.cmb_port = ttk.Combobox(g1, width=36, state="readonly")
        self.cmb_baud = ttk.Combobox(g1, values=["9600", "19200", "38400", "115200"],
                                     width=8, state="readonly")
        self.cmb_baud.set("9600")
        ttk.Label(g1, text="串口").grid(row=0, column=0, padx=2)
        self.cmb_port.grid(row=0, column=1, padx=2)
        ttk.Label(g1, text="波特率").grid(row=0, column=2, padx=2)
        self.cmb_baud.grid(row=0, column=3, padx=2)
        ttk.Button(g1, text="刷新", command=self._refresh_ports).grid(row=0, column=4, padx=2)
        self.btn_conn = ttk.Button(g1, text="连接", command=self._toggle_conn)
        self.btn_conn.grid(row=0, column=5, padx=2)
        self.lbl_link = ttk.Label(g1, text="未连接", foreground=C_IDLE)
        self.lbl_link.grid(row=0, column=6, padx=10)

        g2 = ttk.LabelFrame(main, text="指令", padding=6)
        g2.pack(fill="x", pady=4)
        for i, (name, c) in enumerate((("启动", 0x01), ("停止", 0x02), ("复位", 0x03))):
            ttk.Button(g2, text=name, width=8,
                       command=lambda cc=c: self._send_cmd(cc, 0)).grid(row=0, column=i, padx=4)
        ttk.Label(g2, text="超时阈值 ms").grid(row=0, column=4, padx=(16, 2))
        self.spin = ttk.Spinbox(g2, from_=100, to=60000, increment=50, width=8)
        self.spin.set(1000)
        self.spin.grid(row=0, column=5, padx=2)
        ttk.Button(g2, text="参数下装", command=lambda: self._send_cmd(0x04, int(self.spin.get()))).grid(
            row=0, column=6, padx=4)

        row2 = ttk.Frame(main)
        row2.pack(fill="x", pady=4)

        g3 = ttk.LabelFrame(row2, text="实时状态", padding=6)
        g3.pack(side="left", fill="both", expand=True)
        self.labels = {}
        for i, (key, cap) in enumerate((("MODE", "运行模式"), ("CNT", "累计成功"),
                                        ("CYC_MS", "最近节拍"), ("TMP_D01C", "温度"),
                                        ("PRS_D01KPA", "气压"))):
            ttk.Label(g3, text=cap + "：").grid(row=i, column=0, sticky="e", padx=2, pady=1)
            v = ttk.Label(g3, text="-", width=22)
            v.grid(row=i, column=1, sticky="w", padx=2, pady=1)
            self.labels[key] = v
        self.lbl_dio = ttk.Label(g3, text="-", width=22)
        ttk.Label(g3, text="IO 位图：").grid(row=5, column=0, sticky="e", padx=2, pady=1)
        self.lbl_dio.grid(row=5, column=1, sticky="w", padx=2, pady=1)
        self.lbl_stat = ttk.Label(g3, text="-", foreground=C_IDLE)
        self.lbl_stat.grid(row=6, column=0, columnspan=2, sticky="w", pady=(4, 0))

        g4 = ttk.LabelFrame(row2, text="IO 指示", padding=6)
        g4.pack(side="left", fill="both", padx=(8, 0))
        self.leds = {}
        for i, name in enumerate(n for n, _ in P.DIO_BITS):
            r, c = i % 5, (i // 5) * 2
            lab = ttk.Label(g4, text="○ " + name, foreground=C_OFF, width=12)
            lab.grid(row=r, column=c, padx=2, pady=2)
            self.leds[name] = lab

        g5 = ttk.LabelFrame(main, text="事件日志", padding=4)
        g5.pack(fill="both", expand=True, pady=(4, 0))
        self.txt_log = tk.Text(g5, height=12, state="disabled", wrap="none",
                               font=("Consolas", 9), bg="#fafafa")
        sb = ttk.Scrollbar(g5, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt_log.pack(fill="both", expand=True)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def log(self, msg):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", "%s %s\n" % (time.strftime("%H:%M:%S"), msg))
        if int(self.txt_log.index("end-1c").split(".")[0]) > 2000:
            self.txt_log.delete("1.0", "200.0")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    # ---------------- 串口 ----------------
    def _refresh_ports(self):
        items = []
        if HAVE_SERIAL:
            for it in sorted(list_ports.comports(), key=lambda x: x.device):
                tag = BRIDGE_VIDPID.get((it.vid, it.pid))
                items.append(("%s  %s" % (it.device, tag or (it.description or "")[:28]), it.device))
        self.cmb_port["values"] = [t for t, _ in items]
        self._port_map = dict(items)
        if items:
            self.cmb_port.current(0)

    def _autoconnect(self):
        if not HAVE_SERIAL or not self._port_map:
            self.log("[INFO] 未发现串口；接上 CH340/CP2102 后点“刷新”再“连接”")
            return
        for text, dev in self._port_map.items():
            if any(t in text for t in ("CH340", "CP2102", "USB")):
                self.cmb_port.set(text)
                break
        self._connect()

    def _toggle_conn(self):
        if self.ser:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        if self.simulate:
            self.log("[SIM] 演示模式：协议链路本地仿真中，无需连接串口")
            return
        if not HAVE_SERIAL:
            self.log("[WARN] 未安装 pyserial：pip install pyserial")
            return
        dev = self._port_map.get(self.cmb_port.get())
        if not dev:
            self.log("[WARN] 没有可用串口")
            return
        try:
            self.ser = serial.Serial(dev, int(self.cmb_baud.get()),
                                     bytesize=8, parity="N", stopbits=1, timeout=0)
            self.parser = P.Parser()
            self.last_rx_ts = time.time()
            self.lbl_link.configure(text="已连接 %s" % dev, foreground=C_OK)
            self.btn_conn.configure(text="断开")
            if self.hub:
                self.hub.set_comms(True, str(dev))
            self.log("[INFO] 已连接 %s @%s 8N1" % (dev, self.cmb_baud.get()))
        except Exception as e:
            self.ser = None
            self.log("[ERR] 连接失败：%s" % e)

    def _disconnect(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.btn_conn.configure(text="连接")
        self.lbl_link.configure(text="未连接", foreground=C_IDLE)
        if self.hub:
            self.hub.set_comms(False, "")

    # ---------------- 发送 ----------------
    def _send_cmd(self, cmd, param):
        raw = P.build_command(cmd, param)
        if self.simulate:
            self.log("[SIM] 下发 %s -> %s" % (P.CMDS.get(cmd, hex(cmd)), raw.hex(" ").upper()))
            self._sim_cmd(cmd)
            return
        if not self.ser:
            self.log("[WARN] 未连接串口，命令未发出")
            return
        try:
            self.ser.write(raw)
            self.log("[TX] %s %s" % (P.CMDS.get(cmd, hex(cmd)), raw.hex(" ").upper()))
        except Exception as e:
            self.log("[ERR] 发送失败：%s" % e)

    # ---------------- 接收/解析 ----------------
    def _loop(self):
        if self._closed:
            return
        try:
            self._tick()
        finally:
            if not self._closed:
                self.root.after(20, self._loop)

    def _tick(self):
        data = b""
        if self.simulate:
            n = min(len(self._sim_queue), 3)
            data = bytes(self._sim_queue[:n])
            del self._sim_queue[:n]
        elif self.ser:
            try:
                k = self.ser.in_waiting
                if k:
                    data = self.ser.read(k)
            except Exception as e:
                self.log("[ERR] 串口异常：%s" % e)
                self._disconnect()
                return
        if data:
            for f in self.parser.feed(data):
                self._on_frame(f)
        self._check_stale()

    def _on_frame(self, f):
        self.last_rx_ts = time.time()
        try:
            if f.type == P.T_STATE:
                d = P.decode_state(f.payload)
                if self.prev_seq is not None:
                    gap = (d["SEQ"] - self.prev_seq - 1) & 0xFF
                    if gap:
                        self.lost += gap
                self.prev_seq = d["SEQ"]
                self.last_state = d
                self.frame_n += 1
                self._render(d)
                self._push(d)
            elif f.type == P.T_EVENT:
                d = P.decode_event(f.payload)
                self.log("事件：%s  SEQ=%d  PAR=%d" % (d["EVT_NAME"], d["EVT_SEQ"], d["PAR"]))
                self._push_event(d)
            elif f.type == P.T_ACK:
                d = P.decode_ack(f.payload)
                self.log("应答：%s -> %s" % (d["CMD_NAME"], d["RESULT_NAME"]))
                if d["RESULT"] != 0:
                    self.log("       （协议 §7 结果码非 0）")
        except ValueError as e:
            self.log("[ERR] 帧长不符协议：%s  raw=%s" % (e, f.hexstr()))

    def _render(self, d):
        self.labels["MODE"].configure(text=d["MODE_NAME"], foreground=(
            C_OK if d["MODE"] == 1 else (C_ERR if d["MODE"] in (2, 3) else C_IDLE)))
        self.labels["CNT"].configure(text="%d 次" % d["CNT"])
        self.labels["CYC_MS"].configure(text="%d ms" % d["CYC_MS"])
        self.labels["TMP_D01C"].configure(
            text="-" if d["TMP_D01C"] is None else "%.1f ℃" % (d["TMP_D01C"] / 10.0))
        self.labels["PRS_D01KPA"].configure(
            text="-" if d["PRS_D01KPA"] is None else "%.1f kPa" % (d["PRS_D01KPA"] / 10.0))
        self.lbl_dio.configure(text="0x%04X" % d["DIO_RAW"])
        for name, _ in P.DIO_BITS:
            on = d[name]
            self.leds[name].configure(text=("● " if on else "○ ") + name,
                                      foreground=(C_ON if on else C_OFF))
        self.lbl_stat.configure(text="通信正常  帧=%d 丢=%d 校验错=%d" % (
            self.parser.n_frames, self.lost, self.parser.n_sum_err), foreground=C_OK)

    def _check_stale(self):
        if self.simulate or not self.last_rx_ts:
            return
        if (time.time() - self.last_rx_ts) * 1000 > STALE_MS:
            self.lbl_stat.configure(
                text="通信中断（>%.0fms 无帧），显示最后快照" % STALE_MS, foreground=C_ERR)

    # ---------------- SQLite 推送 ----------------
    def _hub(self):
        if self.hub is None:
            try:
                import push
                self.hub = push.PushHub()
            except Exception as e:
                self.hub = False
                self.log("[WARN] 推送未启用：%s" % e)
        return self.hub or None

    def _push(self, d):
        h = self._hub()
        if not h:
            return
        h.push_state(d, lost=self.lost)
        if self.frame_n % HIST_EVERY == 0:
            h.trim()

    def _push_event(self, d):
        h = self._hub()
        if h:
            h.push_event(d)

    # ---------------- 无硬件演示 ----------------
    def _build_sim_stream(self):
        buf = list(binascii.unhexlify(SAMPLE_STATE))
        buf += list(binascii.unhexlify("AA55060201D204000000DF"))
        seq = 8
        for (mode, dio, cnt, cyc) in [(1, 0x008C, 1234, 0), (1, 0x009C, 1234, 120),
                                      (1, 0x00BC, 1235, 640), (0, 0x0080, 1235, 640)]:
            buf += P.build_state(seq & 0xFF, mode, dio, cnt, cyc)
            seq += 1
        buf += P.build_event(0x05, 2, 0)
        self._sim_seq = seq
        self._sim_evt = 2
        return buf

    def _sim_cmd(self, cmd):
        if cmd == 0x03:
            self._sim_cnt = 0
        self._sim_seq = getattr(self, "_sim_seq", 20)
        mode = {0x01: 1, 0x02: 0, 0x03: 0}.get(cmd, 1)
        self._sim_queue += P.build_state(self._sim_seq & 0xFF, mode,
                                         0x0080 if mode else 0x0000,
                                         getattr(self, "_sim_cnt", 0), 0)
        self._sim_seq += 1
        self._sim_evt += 1
        self._sim_queue += P.build_frame(P.T_ACK, [cmd, 0])

    # ---------------- 生命周期 ----------------
    def run(self):
        self.root.mainloop()

    def _on_close(self):
        self._closed = True
        self._disconnect()
        if self.hub:
            self.hub.close()
        self.root.destroy()

    def selftest(self):
        d = P.decode_state(P.Parser().feed(binascii.unhexlify(SAMPLE_STATE))[0].payload)
        self._render(d)
        self.log("[SELFTEST] 注入协议示例状态帧渲染")
        self.root.update_idletasks()
        self.root.update()
        png = os.path.join(BASE, "host_tk_selftest.png")
        png_msg = "-"
        try:
            from PIL import ImageGrab
            x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
            w, h = self.root.winfo_width(), self.root.winfo_height()
            ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(png)
            png_msg = png
        except Exception as e:
            png_msg = "截屏失败：%s" % e
        print("SELFTEST ok  window=%dx%d  pyserial=%s  ports=%d" % (
            self.root.winfo_width(), self.root.winfo_height(),
            HAVE_SERIAL, len(getattr(self, "_port_map", {}))))
        print("SELFTEST png: %s" % png_msg)
        self._on_close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--simulate", action="store_true", help="无硬件演示模式")
    ap.add_argument("--selftest", action="store_true", help="构建界面+注入示例帧+截屏后退出")
    a = ap.parse_args()
    app = HostTk(simulate=a.simulate)
    if a.selftest:
        app.selftest()
        return 0
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
