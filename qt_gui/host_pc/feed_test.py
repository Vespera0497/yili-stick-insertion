# -*- coding: utf-8 -*-
"""无硬件端到端自验的造数器：复用 S2 的 push.py/protocol.py，按真实格式写 stickinsert.db。
   用途：S3 看板联调（替代需要真实串口的固件数据流）。用法：python feed_test.py [秒数]"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import protocol as P
import push

SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
hub = push.PushHub()
seq, cnt, evt_seq = 100, 500, 10
t0 = time.time()
n = 0
while time.time() - t0 < SECONDS:
    t = time.time() - t0
    mode, dio, cyc = (1, 0x0081, 0) if t < 1 else (1, 0x008C, 0)
    if 1 <= t < 1.2:  dio = 0x009C                       # YV1-3 全通
    if 1.2 <= t < 3:  dio = 0x00BC                       # +SQ1-3 到位
    if t >= 3:
        cnt += 1; cyc = 640
        dio = 0x0080                                     # 循环完成，缸缩回
    d = {"SEQ": seq & 0xFF, "MODE": mode, "MODE_NAME": P.MODES[mode], "DIO_RAW": dio,
         "CNT": cnt, "CYC_MS": cyc, "TMP_D01C": None, "PRS_D01KPA": None}
    for nm, bit in P.DIO_BITS: d[nm] = bool((dio >> bit) & 1)
    hub.push_state(d, lost=0); seq += 1; n += 1
    if abs(t - 2.5) < 0.05:                              # 演示一条急停事件
        ev = P.build_event(1, evt_seq, 0)[4:-1]   # 整帧切出 PAYLOAD 再解码
        hub.push_event(P.decode_event(ev)); evt_seq += 1
    time.sleep(0.1)
hub.set_comms(True, "FEED_TEST")
print("fed %d frames in %.1fs, cnt=%d" % (n, time.time() - t0, cnt))
hub.close()
