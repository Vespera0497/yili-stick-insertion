# -*- coding: utf-8 -*-
"""
三棒签插签设备 · PC 上位机（S2）
技术栈：PySide6 + pyserial；本地推送走共享 SQLite（见 push.py）。
协议：doc/UART_PROTOCOL_v1.md v1.0

运行：
  python main.py                 正常启动，自动枚举并尝试连 CH340/CP2102
  python main.py --simulate      无硬件演示：回放 R1 协议示例帧 + 合成一个完整工作循环
  python main.py --selftest      不弹前台，离屏构建界面并存 host_selftest.png 后退出
"""
import os, sys, time, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import protocol as P

try:
    import serial
    from serial.tools import list_ports
    HAVE_SERIAL = True
except Exception:
    HAVE_SERIAL = False

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton,
                              QComboBox, QSpinBox, QPlainTextEdit, QVBoxLayout, QHBoxLayout,
                              QGroupBox, QFormLayout, QMessageBox)

BRIDGE_VIDPID = {(0x1A86, 0x7523): "CH340", (0x10C4, 0xEA60): "CP2102",
                 (0x1A86, 0x7522): "CH340", (0x067B, 0x2303): "PL2303"}
STALE_MS = 500          # 协议 §10.7：>500ms 无合法上行帧 -> 判通信中断
HIST_EVERY = 5          # 每 5 帧写一次历史，避免 10Hz 全写


class Host(QMainWindow):
    def __init__(self, simulate=False):
        super().__init__()
        self.setWindowTitle("三棒签插签设备 · 上位机")
        self.simulate = simulate
        self.ser = None
        self.parser = P.Parser()
        self.last_state = None
        self.last_rx_ts = 0.0
        self.prev_seq = None
        self.lost = 0
        self.frame_n = 0
        self._build_ui()

        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

        if simulate:
            self._sim_queue = self._build_sim_stream()
            self.log.append("[SIM] 无硬件演示模式：回放协议示例帧 + 合成工作循环")
        else:
            self._autoconnect()

    # ---------------- UI ----------------
    def _build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        v = QVBoxLayout(root)

        conn = QGroupBox("连接"); hv = QHBoxLayout(conn)
        self.port = QComboBox(); hv.addWidget(self.port)
        self.baud = QComboBox(); self.baud.addItems(["9600", "19200", "38400", "115200"])
        self.baud.setCurrentText("9600"); hv.addWidget(QLabel("波特率")); hv.addWidget(self.baud)
        self.btn_refresh = QPushButton("刷新"); self.btn_refresh.clicked.connect(self._refresh_ports)
        self.btn_conn = QPushButton("连接"); self.btn_conn.clicked.connect(self._toggle_conn)
        hv.addWidget(self.btn_refresh); hv.addWidget(self.btn_conn)
        self.lbl_link = QLabel("未连接"); hv.addWidget(self.lbl_link)
        v.addWidget(conn)

        cmd = QGroupBox("指令"); hc = QHBoxLayout(cmd)
        for name, c in (("启动", 0x01), ("停止", 0x02), ("复位", 0x03)):
            b = QPushButton(name); b.clicked.connect(lambda _=0, cc=c: self._send_cmd(cc, 0))
            hc.addWidget(b)
        hc.addWidget(QLabel("超时阈值 ms"))
        self.spin = QSpinBox(); self.spin.setRange(100, 60000); self.spin.setValue(1000)
        self.spin.setSingleStep(50); hc.addWidget(self.spin)
        b = QPushButton("参数下装"); b.clicked.connect(lambda: self._send_cmd(0x04, self.spin.value()))
        hc.addWidget(b); hc.addStretch(1)
        v.addWidget(cmd)

        st = QGroupBox("实时状态"); form = QFormLayout(st); self.labels = {}
        for key, cap in (("MODE", "运行模式"), ("CNT", "累计成功"), ("CYC_MS", "最近节拍"),
                         ("TMP_D01C", "温度"), ("PRS_D01KPA", "气压"),
                         ("DIO", "IO 位图"), ("LINK", "通信")):
            lab = QLabel("-"); self.labels[key] = lab; form.addRow(cap, lab)
        v.addWidget(st)

        ev = QGroupBox("事件日志"); ve = QVBoxLayout(ev)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000); ve.addWidget(self.log)
        v.addWidget(ev, 1)
        self._refresh_ports()
        self.resize(720, 560)

    # ---------------- 串口 ----------------
    def _refresh_ports(self):
        self.port.clear()
        if not HAVE_SERIAL:
            self.log.append("[WARN] 未安装 pyserial：pip install pyserial"); return
        for it in sorted(list_ports.comports(), key=lambda x: x.device):
            tag = BRIDGE_VIDPID.get((it.vid, it.pid))
            self.port.addItem("%s  %s" % (it.device, tag or (it.description or "")[:28]), it.device)

    def _autoconnect(self):
        if not HAVE_SERIAL or self.port.count() == 0:
            self.log.append("[INFO] 未发现串口；接上 CH340/CP2102 后点“刷新”再“连接”")
            return
        # 优先选识别为桥接芯片的口
        idx = 0
        for i in range(self.port.count()):
            if any(t in self.port.itemText(i) for t in ("CH340", "CP2102", "USB")):
                idx = i; self.port.setCurrentIndex(i); break
        self._connect()

    def _toggle_conn(self):
        if self.ser: self._disconnect()
        else: self._connect()

    def _connect(self):
        if not HAVE_SERIAL: return
        dev = self.port.currentData()
        if not dev:
            QMessageBox.information(self, "提示", "没有可用串口"); return
        try:
            self.ser = serial.Serial(dev, int(self.baud.currentText()),
                                     bytesize=8, parity='N', stopbits=1, timeout=0)
            self.parser = P.Parser()
            self.last_rx_ts = time.time()
            self.lbl_link.setText("已连接 %s" % dev)
            self.btn_conn.setText("断开")
            if hasattr(self, "hub"): self.hub.set_comms(True, str(dev))
            self.log.append("[INFO] 已连接 %s @%s 8N1" % (dev, self.baud.currentText()))
        except Exception as e:
            self.ser = None
            self.log.append("[ERR] 连接失败：%s" % e)

    def _disconnect(self):
        if self.ser:
            try: self.ser.close()
            except Exception: pass
        self.ser = None
        self.btn_conn.setText("连接")
        self.lbl_link.setText("未连接")
        if hasattr(self, "hub"): self.hub.set_comms(False, "")

    # ---------------- 发送 ----------------
    def _send_cmd(self, cmd, param):
        raw = P.build_command(cmd, param)
        if self.simulate:
            self.log.append("[SIM] 下发 %s -> %s" % (P.CMDS.get(cmd, hex(cmd)), raw.hex(" ").upper()))
            self._sim_cmd(cmd)
            return
        if not self.ser:
            self.log.append("[WARN] 未连接串口，命令未发出"); return
        try:
            self.ser.write(raw)
            self.log.append("[TX] %s %s" % (P.CMDS.get(cmd, hex(cmd)), raw.hex(" ").upper()))
        except Exception as e:
            self.log.append("[ERR] 发送失败：%s" % e)

    # ---------------- 接收/解析 ----------------
    def _tick(self):
        data = b""
        if self.simulate:
            n = min(len(self._sim_queue), 3)
            data = bytes(self._sim_queue[:n]); del self._sim_queue[:n]
        elif self.ser:
            try:
                k = self.ser.in_waiting
                if k: data = self.ser.read(k)
            except Exception as e:
                self.log.append("[ERR] 串口异常：%s" % e); self._disconnect(); return
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
                    if gap: self.lost += gap
                self.prev_seq = d["SEQ"]
                self.last_state = d
                self.frame_n += 1
                self._render(d)
                self._push(d)
            elif f.type == P.T_EVENT:
                d = P.decode_event(f.payload)
                self.log.append("[%s] 事件：%s  SEQ=%u  PAR=%d" % (
                    time.strftime("%H:%M:%S"), d["EVT_NAME"], d["EVT_SEQ"], d["PAR"]))
                self._push_event(d)
            elif f.type == P.T_ACK:
                d = P.decode_ack(f.payload)
                line = "[%s] 应答：%s -> %s" % (time.strftime("%H:%M:%S"), d["CMD_NAME"], d["RESULT_NAME"])
                self.log.append(line)
                if d["RESULT"] != 0: self.log.append("       （协议 §7 结果码）")
        except ValueError as e:
            self.log.append("[ERR] 帧长不符协议：%s  raw=%s" % (e, f.hexstr()))

    def _render(self, d):
        self.labels["MODE"].setText(d["MODE_NAME"])
        self.labels["CNT"].setText("%d 次" % d["CNT"])
        self.labels["CYC_MS"].setText("%d ms" % d["CYC_MS"])
        self.labels["TMP_D01C"].setText("-" if d["TMP_D01C"] is None else "%.1f ℃" % (d["TMP_D01C"] / 10.0))
        self.labels["PRS_D01KPA"].setText("-" if d["PRS_D01KPA"] is None else "%.1f kPa" % (d["PRS_D01KPA"] / 10.0))
        self.labels["DIO"].setText(" ".join("%s=%d" % (n, int(d[n])) for n, _ in P.DIO_BITS))
        self.labels["LINK"].setText("正常  帧=%d 丢=%d 校验错=%d" % (
            self.parser.n_frames, self.lost, self.parser.n_sum_err))
        self.labels["LINK"].setStyleSheet("color:#0a7a2f")

    def _check_stale(self):
        if self.simulate or not self.last_rx_ts: return
        if (time.time() - self.last_rx_ts) * 1000 > STALE_MS:
            self.labels["LINK"].setText("通信中断（>%.0fms 无帧），显示最后快照" % STALE_MS)
            self.labels["LINK"].setStyleSheet("color:#b00020")

    # ---------------- SQLite 推送 ----------------
    def _hub(self):
        if not hasattr(self, "hub"):
            try:
                import push
                self.hub = push.PushHub()
            except Exception as e:
                self.hub = None
                self.log.append("[WARN] 推送未启用：%s" % e)
        return self.hub

    def _push(self, d):
        h = self._hub()
        if not h: return
        h.push_state(d, lost=self.lost)
        if self.frame_n % HIST_EVERY == 0: h.trim()

    def _push_event(self, d):
        h = self._hub()
        if h: h.push_event(d)

    # ---------------- 无硬件演示 ----------------
    def _build_sim_stream(self):
        import binascii
        buf = list(binascii.unhexlify("AA550E0107018900D20400006C02FB00F503D7"))
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
        self._sim_queue += P.build_state(self._sim_seq & 0xFF, mode, 0x0080 if mode else 0x0000,
                                         getattr(self, "_sim_cnt", 0), 0)
        self._sim_seq += 1
        self._sim_evt += 1
        self._sim_queue += P.build_ack_bytes(cmd, 0) if hasattr(P, "build_ack_bytes") else \
            P.build_frame(P.T_ACK, [cmd, 0])

    def closeEvent(self, e):
        self._disconnect()
        if hasattr(self, "hub"): self.hub.close()
        super().closeEvent(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--simulate", action="store_true", help="无硬件演示模式")
    ap.add_argument("--selftest", action="store_true", help="离屏构建界面并截图后退出")
    a = ap.parse_args()

    if a.selftest:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv)
    w = Host(simulate=a.simulate)
    w.show()

    if a.selftest:
        d = P.decode_state(P.Parser().feed(
            __import__("binascii").unhexlify("AA550E0107018900D20400006C02FB00F503D7"))[0].payload)
        w.last_state = d; w._render(d)
        w.log.append("[SELFTEST] 注入协议示例状态帧渲染")
        app.processEvents()
        png = os.path.join(os.path.dirname(os.path.abspath(__file__)), "host_selftest.png")
        w.grab().save(png)
        print("SELFTEST ok  window=%dx%d  png=%s" % (w.width(), w.height(), png))
        print("SELFTEST 端口数=%d  pyserial=%s" % (w.port.count(), HAVE_SERIAL))
        return 0
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
