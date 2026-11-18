# -*- coding: utf-8 -*-
"""协议实现自测：对照 doc/UART_PROTOCOL_v1.md §8 的四条示例帧 + 抗噪/抗篡改用例。"""
import binascii
import random
import sys
sys.path.insert(0, ".")
import protocol

ok = fail = 0
def chk(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print("  PASS  %s %s" % (name, extra))
    else:    fail += 1; print("  FAIL  %s %s" % (name, extra))

def hx(s): return binascii.unhexlify(s.replace(" ", ""))

ST  = hx("AA 55 0E 01 07 01 89 00 D2 04 00 00 6C 02 FB 00 F5 03 D7")
EV  = hx("AA 55 06 02 01 D2 04 00 00 00 DF")
CMD = hx("AA 55 03 81 04 20 03 AB")
ACK = hx("AA 55 02 03 04 00 09")
SEN = hx("AA 55 0E 01 00 00 00 00 00 00 00 00 00 00 FF 7F FF FF 8B")

print("[1] R1 示例帧解码")
f = protocol.Parser().feed(ST); chk("状态帧收到 1 帧", len(f) == 1)
if f:
    d = protocol.decode_state(f[0].payload)
    chk("SEQ=7", d["SEQ"] == 7); chk("MODE=RUNNING", d["MODE_NAME"].startswith("RUNNING"))
    chk("CNT=1234", d["CNT"] == 1234); chk("CYC=620", d["CYC_MS"] == 620)
    chk("TMP=25.1C", d["TMP_D01C"] == 251); chk("PRS=101.3kPa", d["PRS_D01KPA"] == 1013)
    chk("YV1=1 YV2=0 YV3=0", (d["YV1"], d["YV2"], d["YV3"]) == (True, False, False))
    chk("SQ1=1 SQ2=0 SQ3=0", (d["SQ1"], d["SQ2"], d["SQ3"]) == (True, False, False))
    chk("SB1=0(未触发)", d["SB1"] is False)
    chk("LED_RUN=1 亮", d["LED_RUN"] is True); chk("LED_ALARM=0", d["LED_ALARM"] is False)
    chk("DIO 原始=0x0089", d["DIO_RAW"] == 0x0089)
    chk("保留位 b9-15 全 0", (d["DIO_RAW"] >> 9) == 0)

f = protocol.Parser().feed(EV); chk("事件帧 1 帧", len(f) == 1)
if f:
    d = protocol.decode_event(f[0].payload)
    chk("EVT=急停触发", d["EVT"] == 0x01 and d["EVT_NAME"] == "急停触发")
    chk("EVT_SEQ=1234", d["EVT_SEQ"] == 1234); chk("PAR=0", d["PAR"] == 0)

f = protocol.Parser().feed(ACK); chk("应答帧 1 帧", len(f) == 1)
if f:
    d = protocol.decode_ack(f[0].payload)
    chk("CMD=参数下装 RESULT=已执行", d["CMD_NAME"] == "参数下装" and d["RESULT_NAME"] == "已执行")

print("[2] 方向位：下行 TYPE 不得被当上行收下")
p = protocol.Parser(); got = p.feed(CMD)
chk("命令帧被拒", len(got) == 0 and p.n_dir_err == 1)
chk("命令帧 SUM 与协议示例一致", protocol.build_command(0x04, 800) == CMD)

print("[3] 任意切分（逐字节喂）结果一致")
acc = []
p = protocol.Parser()
for i in range(len(ST)): acc += p.feed(ST[i:i+1])
chk("逐字节喂出 1 帧", len(acc) == 1 and acc[0].raw == ST)
p = protocol.Parser(); acc = p.feed(ST[:5]) + p.feed(ST[5:9]) + p.feed(ST[9:])
chk("三段切分喂出 1 帧", len(acc) == 1)

print("[4] 噪声与重同步")
p = protocol.Parser(); r = p.feed(b"\x00\xff\x13" + ST + b"\x77" + EV)
chk("噪声前后两帧都恢复", len(r) == 2 and r[0].type == 0x01 and r[1].type == 0x02)
p = protocol.Parser(); r = p.feed(b"\xAA\xAA\x55" + ST[2:])
chk("双 AA 重同步", len(r) == 1)
p = protocol.Parser(); r = p.feed(bytes([0xAA,0x55,0x00]) + ST)   # 前插 LEN=0 坏帧，真帧完整保留
chk("LEN=0 非法被拒后重同步", len(r) == 1 and p.n_len_err == 1)
p = protocol.Parser(); r = p.feed(hx("AA 55") + b"\x10" + b"\x01" + b"\x00" * 16 + b"\x00")
chk("LEN=16 非法被拒", len(r) == 0 and p.n_len_err == 1)

print("[5] 篡改检测")
bad = bytearray(ST); bad[6] ^= 0x01
p = protocol.Parser(); r = p.feed(bytes(bad))
chk("翻转 1 位 -> 拒收", len(r) == 0 and p.n_sum_err == 1)
bad2 = bytearray(ST); bad2[-1] ^= 0xFF            # 只错 SUM 字节，帧长仍完整
p = protocol.Parser(); chk("SUM 字节错 -> 拒收", len(p.feed(bytes(bad2))) == 0 and p.n_sum_err == 1)
p = protocol.Parser(); chk("半帧(缺 SUM)不产出", len(p.feed(bytes(ST[:-1]))) == 0 and p.n_frames == 0)

print("[6] 哨兵与负温")
p = protocol.Parser(); d = protocol.decode_state(p.feed(SEN)[0].payload)
chk("TMP 哨兵 -> None", d["TMP_D01C"] is None); chk("PRS 哨兵 -> None", d["PRS_D01KPA"] is None)
neg = protocol.build_state(1, 1, 0, 0, 0, tmp=0x10000 - 50, prs=999)   # -5.0C
d = protocol.decode_state(protocol.Parser().feed(neg)[0].payload)
chk("负温 -5.0C 还原", d["TMP_D01C"] == -50, "got %s" % d["TMP_D01C"])

print("[7] 构造/解析往返 100 组")
random.seed(7); bad_cnt = 0
for _ in range(100):
    seq = random.randrange(256); mode = random.randrange(4); dio = random.randrange(512)
    cnt = random.randrange(1 << 32); cyc = random.randrange(65536)
    raw = protocol.build_state(seq, mode, dio, cnt, cyc, 0x7FFF, 0xFFFF)
    fr = protocol.Parser().feed(raw)
    if len(fr) != 1: bad_cnt += 1; continue
    dd = protocol.decode_state(fr[0].payload)
    if (dd["SEQ"], dd["MODE"], dd["DIO_RAW"], dd["CNT"], dd["CYC_MS"]) != (seq, mode, dio, cnt, cyc): bad_cnt += 1
chk("往返全对", bad_cnt == 0, "失败 %d 组" % bad_cnt)

print("\n合计 PASS=%d FAIL=%d" % (ok, fail))
sys.exit(1 if fail else 0)
