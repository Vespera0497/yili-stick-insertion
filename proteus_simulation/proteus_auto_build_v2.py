# -*- coding: utf-8 -*-
"""
Proteus 确定性自动化 v2 —— 补掉 v1 的三个洞
  洞1 hex/频率：改为枚举属性框子控件 + WM_SETTEXT 真填 + 读回校验 + 点 OK
  洞2 连线：改为运行时从截图检测 U1 引脚末端真实坐标，再按行做水平直线连线
  洞3 坐标作废：不再硬编码 v10 屏幕坐标；画布几何一律检测，面板几何才用窗口偏移
另外：启动前杀干净旧 PDS 实例；每阶段保存并核对磁盘字节数。

用法:
  D:\ANACONDA\python.exe proteus_auto_build_v2.py --measure   # 只检测+写 report，不动工程
  D:\ANACONDA\python.exe proteus_auto_build_v2.py             # 全流程
"""
import os, sys, re, time, json, subprocess, logging

import win32gui, win32con, win32api, win32process
from win32gui import PostMessage
from PIL import Image, ImageGrab, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "auto_out")
os.makedirs(OUT, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(os.path.join(HERE, "proteus_v2.log"), encoding="utf-8"),
              logging.StreamHandler()])
log = logging.getLogger("pv2")

# ---------------- CONFIG ----------------
PDS   = r"C:\Program Files (x86)\Labcenter Electronics\Proteus 8 Professional\BIN\PDS.EXE"
PROJ  = os.path.join(HERE, "StickInsert_ref_copy.pdsprj")
HEX   = os.path.join(HERE, "control.hex")
HEX_MD5 = "add4cedc80a26f4666e09a4603a884c9"
CLOCK = "11.0592MHz"

CMD_SAVE, CMD_VIEW_ALL, CMD_ZOOM_IN, CMD_CENTER, CMD_RUN = 0x0204, 0x014B, 0x0149, 0x0148, 0x0233

# 只有"停靠面板"用窗口相对偏移（面板位置与画布缩放无关）
# 实测自 23:26 截图：DEVICES 列表 AT89C52/BUTTON/LED-RED/RES 依次在 y≈270/292/310/328
OFF_LED_LIST   = (60, 310)      # Pick devices: LED-RED
OFF_GND_LIST   = (60, 328)      # Pick devices: RES（共地串阻用）
TERM_MIN_PITCH = 26              # 引脚行距小于此值就继续放大
N_LED          = 3
PINMAP         = os.path.join(OUT, "pinmap.json")   # {"L":[行名...]} 由 OCR 步骤产出
WANT_PINS      = ("P1.0", "P1.1", "P1.2")

def md5(p):
    import hashlib
    return hashlib.md5(open(p, "rb").read()).hexdigest()

def psize(p):
    try:
        return os.path.getsize(p)
    except OSError:
        return -1

# ---------------- 窗口 ----------------
def enum_pids():
    return {p for p in [win32process.GetWindowThreadProcessId(h)[1] for h in
                        [win32gui.GetDesktopWindow()]] }

def kill_old_pds():
    """杀干净旧 PDS 实例（工程此前已确认无未保存内容）。"""
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq PDS.EXE", "/FO", "CSV", "/NH"],
                       capture_output=True, text=True)
    pids = [int(m.group(1)) for m in re.finditer(r'"PDS\.EXE","(\d+)"', r.stdout or "")]
    for pid in pids:
        log.info("杀旧 PDS 实例 pid=%s", pid)
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    time.sleep(3 if pids else 0.2)
    return pids

def find_main():
    """主编辑器窗口：标题含 Proteus/工程名 且类名不是 #32770，取客户区最大的。"""
    base = os.path.splitext(os.path.basename(PROJ))[0].lower()
    best = []
    def cb(h, _):
        if not win32gui.IsWindowVisible(h):
            return
        t = win32gui.GetWindowText(h)
        if win32gui.GetClassName(h) == "#32770":
            return
        if ("isis" in t.lower()) or ("proteus" in t.lower()) or (base in t.lower()):
            rc = win32gui.GetWindowRect(h)
            best.append(((rc[2]-rc[0])*(rc[3]-rc[1]), h, t))
    win32gui.EnumWindows(cb, None)
    if not best:
        return None, ""
    best.sort(reverse=True)
    return best[0][1], best[0][2]

def dialogs():
    d = []
    def cb(h, _):
        if win32gui.GetClassName(h) == "#32770" and win32gui.IsWindowVisible(h):
            d.append((h, win32gui.GetWindowText(h)))
    win32gui.EnumWindows(cb, None)
    return d

def esc_modals():
    n = 0
    for h, t in dialogs():
        log.info("清模态: %r", t)
        for m in (win32con.WM_KEYDOWN, win32con.WM_KEYUP):
            win32api.PostMessage(h, m, win32con.VK_ESCAPE, 0)
        n += 1
    if n:
        time.sleep(0.35)
    return n

def children(h):
    out = []
    def cb(c, _):
        out.append((c, win32gui.GetClassName(c), win32gui.GetWindowText(c),
                    win32gui.GetWindowRect(c)))
    win32gui.EnumChildWindows(h, cb, None)
    return out

def click_btn(h, *keys):
    for c, cls, t, rc in children(h):
        if cls in ("Button", "TButton", "ButtonWindowClass") and any(k in t for k in keys):
            real_click((rc[0]+rc[2])//2, (rc[1]+rc[3])//2)
            log.info("点按钮 %r", t)
            return True
    return False

# ---------------- 真实输入 ----------------
CUR0 = None
def grab_cursor():
    global CUR0
    CUR0 = win32api.GetCursorPos()
def restore_cursor():
    if CUR0:
        win32api.SetCursorPos(CUR0)
        log.info("光标已还原 %s", CUR0)

def real_click(x, y, double=False, right=False):
    win32api.SetCursorPos((int(x), int(y)))
    time.sleep(0.06)
    if right:
        dn, up = win32con.MOUSEEVENTF_RIGHTDOWN, win32con.MOUSEEVENTF_RIGHTUP
    else:
        dn, up = win32con.MOUSEEVENTF_LEFTDOWN, win32con.MOUSEEVENTF_LEFTUP
    for _ in range(2 if double else 1):
        win32api.mouse_event(dn, 0, 0, 0, 0)
        win32api.mouse_event(up, 0, 0, 0, 0)
        time.sleep(0.09)
    time.sleep(0.12)

def real_key(vk):
    win32api.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.1)

def cmd(h, cid):
    win32api.PostMessage(h, win32con.WM_COMMAND, cid, 0)
    time.sleep(0.4)

def shot(name):
    p = os.path.join(OUT, name)
    ImageGrab.grab().save(p)
    log.info("截图 %s", p)
    return p

# ---------------- 几何检测（洞2/洞3 核心） ----------------
def grab_canvas(hwnd=None):
    """只裁 Proteus 窗口区域，避免屏幕上别的窗口线条污染检测。
       返回 (image, origin_x, origin_y)，image 坐标 + origin = 屏幕坐标。"""
    img = ImageGrab.grab()
    if hwnd and win32gui.IsWindow(hwnd):
        wr = win32gui.GetWindowRect(hwnd)
        left, top = max(0, wr[0]), max(0, wr[1])
        box = (left, top, min(img.width, wr[2]), min(img.height, wr[3]))
        if box[2] > box[0] + 50 and box[3] > box[1] + 50:
            return img.crop(box), box[0], box[1]
    return img, 0, 0

def black_mask(img):
    g = img.convert("L")
    w, h = g.size
    px = g.load()
    return [[1 if px[x, y] < 140 else 0 for x in range(w)] for y in range(h)], w, h

def detect_u1(img, log_prefix="", ox=0, oy=0):
    """按 U1 的灰填充矩形定位（黑线法会匹到工具箱面板，见 detect_u1_edges）。
       返回 None 表示没找到或没完整入镜（调用方应回整图重试）。"""
    g = img.convert("L"); W, H = g.size; px = g.load()
    rows = []
    for y in range(H):
        run = best = bs = 0
        for x in range(W):
            if 185 <= px[x, y] <= 250:
                run += 1
                if run > best:
                    best, bs = run, x - run + 1
            else:
                run = 0
        if best >= 70:
            rows.append((y, bs, best))
    if len(rows) < 120:
        log.warning("%s灰填充行太少(%d)", log_prefix, len(rows))
        return None
    # 最长连续 y 带（允许 2px 间断）
    best_band, cur = None, [rows[0]]
    for r in rows[1:]:
        if r[0] - cur[-1][0] <= 2:
            cur.append(r)
        else:
            if best_band is None or len(cur) > len(best_band):
                best_band = cur
            cur = [r]
    if best_band is None or len(cur) > len(best_band):
        best_band = cur
    top_y, bot_y = best_band[0][0], best_band[-1][0]
    if top_y < 4 or bot_y > H - 5:
        log.warning("%sU1 未完整入镜 (y %d-%d / H=%d)", log_prefix, top_y, bot_y, H)
        return None
    left_x = min(b + s for _, b, s in best_band)
    right_x = max(b + s - 1 for _, b, s in best_band)
    if right_x - left_x < 80:
        log.warning("%s填充块过窄", log_prefix)
        return None

    def tips(side):
        res = {}
        for y in range(top_y + 2, bot_y - 1):
            run = 0
            for k in range(1, 90):
                x = (left_x - k) if side == "L" else (right_x + k)
                if 0 <= x < W and px[x, y] < 140:
                    run += 1
                else:
                    break
            if run >= 8:
                res.setdefault(y // 3, []).append((y, run, x))
        return res
    L, R = tips("L"), tips("R")
    rowsout = []
    for band in sorted(set(list(L.keys()) + list(R.keys()))):
        c = [v for b in (band - 1, band, band + 1) for v in L.get(b, [])] + \
            [v for b in (band - 1, band, band + 1) for v in R.get(b, [])]
        if not c:
            continue
        ys = sorted(z[0] for z in c)
        y = ys[len(ys) // 2]
        lc = [z for z in c if z[2] <= left_x]
        rc = [z for z in c if z[2] >= right_x]
        rowsout.append({"y": y,
                        "lx": min(z[2] for z in lc) if lc else None,
                        "rx": max(z[2] for z in rc) if rc else None})
    merged = []
    for r in rowsout:
        if merged and abs(r["y"] - merged[-1]["y"]) <= 4:
            m = merged[-1]
            m["lx"] = min([v for v in (m["lx"], r["lx"]) if v is not None] or [None])
            m["rx"] = max([v for v in (m["rx"], r["rx"]) if v is not None] or [None])
        else:
            merged.append(dict(r))
    pitch = 0.0
    if len(merged) > 1:
        d = [merged[i + 1]["y"] - merged[i]["y"] for i in range(len(merged) - 1)]
        pitch = sum(d) / len(d)
    out = {"left_x": left_x, "right_x": right_x, "top_y": top_y, "bot_y": bot_y,
           "rows": merged, "pitch": round(pitch, 2)}
    log.info("%sU1(灰块法): body x %d-%d y %d-%d, 行 %d, 行距 %.1f",
             log_prefix, left_x, right_x, top_y, bot_y, len(merged), pitch)
    return out


def detect_u1_edges(img, log_prefix="", ox=0, oy=0):
    """旧的黑线边框法（保留作对照）。"""
    M, W, H = black_mask(img)
    # 累计每行的黑色跨度，找最长的水平线
    spans = []
    for y in range(H):
        row = M[y]
        x0, x1 = None, None
        for x in range(W):
            if row[x]:
                if x0 is None:
                    x0 = x
                x1 = x
        if x0 is not None:
            spans.append((x1 - x0, x0, x1, y))
    spans.sort(reverse=True)
    long_h = [s for s in spans[:400] if s[0] > 90]
    if not long_h:
        log.warning("%s没找到长水平线", log_prefix)
        return None
    ys = sorted({s[3] for s in long_h})
    top_y, bot_y = ys[0], ys[-1]
    # 上下边框必须成对（同一 x 区间、高度差 > 120）
    cand = None
    for a in range(len(ys)):
        for b in range(a + 1, len(ys)):
            ya, yb = ys[a], ys[b]
            if yb - ya < 150:
                continue
            sa = [s for s in long_h if s[3] == ya][0]
            sb = [s for s in long_h if s[3] == yb][0]
            ox = min(sa[2], sb[2]) - max(sa[1], sb[1])
            if ox > 60:
                cand = (ya, yb, max(sa[1], sb[1]), min(sa[2], sb[2]))
                break
        if cand:
            break
    if not cand:
        log.warning("%s找不到成对边框", log_prefix)
        return None
    top_y, bot_y, bx0, bx1 = cand
    # 垂直线定左右边框（区间必须夹紧，否则越界 IndexError）
    vspans = []
    for x in range(max(0, bx0 - 30), min(W, bx1 + 31)):
        y0 = y1 = None
        for y in range(max(0, top_y - 20), min(H, bot_y + 21)):
            if M[y][x]:
                if y0 is None:
                    y0 = y
                y1 = y
        if y0 is not None and y1 - y0 > 120:
            vspans.append((y1 - y0, x))
    vspans.sort(reverse=True)
    if len(vspans) < 2:
        log.warning("%s垂直边框不足", log_prefix)
        return None
    left_x = min(v[1] for v in vspans[:4])
    right_x = max(v[1] for v in vspans[:4])

    # 引脚：边框外侧 6..70 px 内的水平短线
    def tips(side):
        res = {}
        for y in range(top_y + 2, bot_y - 1):
            run = 0
            for k in range(1, 90):
                x = (left_x - k) if side == "L" else (right_x + k)
                if 0 <= x < W and M[y][x]:
                    run += 1
                else:
                    break
            if run >= 8:
                res.setdefault(y // 3, []).append((y, run, x))
        return res
    L, R = tips("L"), tips("R")
    rows = []
    for band in sorted(set(list(L.keys()) + list(R.keys()))):
        cands = [v for b in (band - 1, band, band + 1) for v in L.get(b, [])] + \
                [v for b in (band - 1, band, band + 1) for v in R.get(b, [])]
        if not cands:
            continue
        y = sorted(c for c, _, _ in cands)[len(cands) // 2]
        lc = [c for c in cands if c[2] <= left_x]
        rc = [c for c in cands if c[2] >= right_x]
        lx = min(c[2] for c in lc) if lc else None
        rx = max(c[2] for c in rc) if rc else None
        rows.append({"y": y, "lx": lx, "rx": rx})
    # 合并 4px 内重复行
    merged = []
    for r in rows:
        if merged and abs(r["y"] - merged[-1]["y"]) <= 4:
            m = merged[-1]
            m["lx"] = min([v for v in (m["lx"], r["lx"]) if v is not None] or [None])
            m["rx"] = max([v for v in (m["rx"], r["rx"]) if v is not None] or [None])
        else:
            merged.append(dict(r))
    pitch = 0.0
    if len(merged) > 1:
        d = [merged[i + 1]["y"] - merged[i]["y"] for i in range(len(merged) - 1)]
        pitch = sum(d) / len(d)
    out = {"left_x": left_x, "right_x": right_x, "top_y": top_y, "bot_y": bot_y,
           "rows": merged, "pitch": round(pitch, 2)}
    log.info("%sU1 检测: body x %d-%d, y %d-%d, 引脚行 %d, 行距 %.1f",
             log_prefix, left_x, right_x, top_y, bot_y, len(merged), pitch)
    return out

def to_screen(geo, ox, oy):
    """把裁图内相对坐标换成屏幕绝对坐标，供真实点击使用。"""
    g = dict(geo)
    g["left_x"], g["right_x"] = geo["left_x"] + ox, geo["right_x"] + ox
    g["top_y"], g["bot_y"] = geo["top_y"] + oy, geo["bot_y"] + oy
    g["rows"] = [{"y": r["y"] + oy,
                  "lx": None if r["lx"] is None else r["lx"] + ox,
                  "rx": None if r["rx"] is None else r["rx"] + ox} for r in geo["rows"]]
    return g

def annotate(img, geo, path):
    im = img.copy()
    d = ImageDraw.Draw(im)
    d.rectangle([geo["left_x"], geo["top_y"], geo["right_x"], geo["bot_y"]], outline=(255, 0, 0))
    for i, r in enumerate(geo["rows"]):
        if r["lx"]:
            d.ellipse([r["lx"] - 4, r["y"] - 4, r["lx"] + 4, r["y"] + 4], outline=(0, 0, 255))
            d.text((max(0, r["lx"] - 60), r["y"] - 6), "L%d" % i, fill=(0, 0, 255))
        if r["rx"]:
            d.ellipse([r["rx"] - 4, r["y"] - 4, r["rx"] + 4, r["y"] + 4], outline=(0, 160, 0))
            d.text((r["rx"] + 6, r["y"] - 6), "R%d" % i, fill=(0, 120, 0))
    im.save(path)
    log.info("标注图 %s", path)

def strip_pins(img, geo, path, side="L"):
    """把每行引脚名裁出来纵向拼接（4x 放大），供 OCR 读回行号->引脚名映射。"""
    n = len(geo["rows"])
    cw = 96 if side == "L" else 96
    x0 = geo["left_x"] - cw if side == "L" else geo["right_x"]
    W, H = cw * 4, 20 * n
    out = Image.new("RGB", (W, H), "white")
    for i, r in enumerate(geo["rows"]):
        box = (max(0, x0), max(0, r["y"] - 7), min(img.width, x0 + cw), r["y"] + 7)
        c = img.crop(box).resize((cw * 4, 14 * 4))
        out.paste(c, (0, i * 20))
        ImageDraw.Draw(out).line([(0, i * 20), (W, i * 20)], fill=(200, 0, 0))
    out.save(path)
    log.info("引脚裁条 %s (%d 行)", path, n)
    return n

# ---------------- 洞1：属性框真填 ----------------
LABEL_HEX = ("program file", "程序文件", "program memory", "hex", "固件")
LABEL_CLK = ("clock", "时钟", "frequency", "频率")
LABEL_OTHER = ("model", "script", "producer", "package", "spice", "value", "reference")

def dump_dialog(h):
    log.info("属性框控件 %r", win32gui.GetWindowText(h))
    for c, cls, t, rc in children(h):
        log.info("   cls=%-16s text=%-34r rect=%s", cls, t, rc)

def open_u1_props(hwnd, geo):
    """四种真实方式逐个试：双击本体中心 / 单击+真回车 / 双击位号区 / 右键菜单。"""
    bx = (geo["left_x"] + geo["right_x"]) // 2
    by = (geo["top_y"] + geo["bot_y"]) // 2
    cands = [("本体中心", bx, by),
             ("位号区", geo["left_x"] + 14, geo["top_y"] + 16),
             ("本体下部", bx, geo["bot_y"] - 40)]
    for name, x, y in cands:
        esc_modals()
        real_click(x, y, double=True)
        time.sleep(0.7)
        ds = dialogs()
        if ds:
            log.info("双击 %s (%d,%d) 弹出 %r", name, x, y, ds[0][1])
            return ds[0][0]
        real_click(x, y)
        time.sleep(0.25)
        real_key(win32con.VK_RETURN)
        time.sleep(0.7)
        ds = dialogs()
        if ds:
            log.info("选中 %s + 真回车 弹出 %r", name, ds[0][1])
            return ds[0][0]
        esc_modals()
    # 右键：Proteus 上下文菜单是自绘弹出窗口，只能按标题栏匹配 #32770 或点首项位置
    real_click(bx, by, right=True)
    time.sleep(0.5)
    ds = dialogs()
    if ds:
        log.info("右键后弹出 %r", ds[0][1])
        return ds[0][0]
    log.warning("属性框未能打开（三种双击+回车+右键均已尝试）")
    return None

def set_field(dlg, keys, value, skip=()):
    """找 label 命中 keys 的行，把右侧最近的可编辑控件设为 value，并读回校验。"""
    ch = children(dlg)
    labs = [(cls, t, rc) for c, cls, t, rc in ch if cls in ("Static", "SysLabel", "label") and t]
    ed = [(c, cls, t, rc) for c, cls, t, rc in ch
          if cls in ("Edit", "ComboBox", "ComboBoxEx32", "EditWindowClass", "ButtonWindowClass")]
    for cls, t, rc in labs:
        low = t.lower()
        if not any(k in low for k in keys):
            continue
        if any(s in low for s in skip):
            continue
        cy = (rc[1] + rc[3]) // 2
        near = [e for e in ed if e[3][1] - 6 <= cy <= e[3][3] + 6 and e[3][0] >= rc[0] - 4]
        if not near:
            continue
        tgt = min(near, key=lambda e: abs(e[3][0] - rc[2]))
        c, ccls, ctext, crc = tgt
        if ccls == "ComboBox":
            cbi = win32api.SendMessage(c, win32con.CB_GETEDITCONTROL, 0, 0)
            h_edit = cbi or c
        else:
            h_edit = c
        win32api.SendMessage(h_edit, win32con.WM_SETTEXT, 0, value)
        time.sleep(0.1)
        back = win32gui.GetWindowText(h_edit)
        log.info("字段 %r -> 写入 %r 读回 %r (%s)", t, value, back, ccls)
        return back == value
    log.warning("没找到字段 %s", keys)
    return False

def fill_props(dlg):
    dump_dialog(dlg)
    okh = set_field(dlg, LABEL_HEX, HEX)
    okc = set_field(dlg, LABEL_CLK, CLOCK)
    shot("05_props.png")
    if okh and okc:
        click_btn(dlg, "OK", "确定")
        time.sleep(0.8)
        log.info("属性框已点 OK 提交")
    else:
        log.warning("有字段没写进去，点取消保持工程不变")
        click_btn(dlg, "Cancel", "取消")
        time.sleep(0.5)
    esc_modals()
    return okh and okc

# ---------------- 放件 ----------------
def find_lead(img, y, x_from, x_to, min_run=6):
    """在 y 行、[x_from,x_to) 区间找水平黑色短线端点（器件引脚末端），返回最靠右的端点 x。"""
    g = img.convert("L"); px = g.load(); W = g.size[0]
    x_from, x_to = max(0, x_from), min(W, x_to)
    best = None
    for yy in (y - 1, y, y + 1):
        run, start = 0, None
        for x in range(x_from, x_to):
            if px[x, yy] < 140:
                if run == 0:
                    start = x
                run += 1
            else:
                if run >= min_run:
                    cand = start + run - 1
                    if best is None or cand > best:
                        best = cand
                run = 0
        if run >= min_run and (best is None or x_to - 1 > best):
            best = x_to - 1
    return best

def place_led(hwnd, geo, i, row):
    esc_modals()
    rc = win32gui.GetWindowRect(hwnd)
    real_click(rc[0] + OFF_LED_LIST[0], rc[1] + OFF_LED_LIST[1])   # 装填（停靠面板=窗口相对）
    time.sleep(0.35)
    x = geo["left_x"] - 120        # P1.x 在左列，LED 放左侧才能走水平直线
    y = row["y"]
    real_click(x, y)                                               # 放置
    time.sleep(0.35)
    for dh, dt in dialogs():
        if "replace" in dt.lower():
            if not click_btn(dh, "New", "新建", "Place New"):
                esc_modals()
    esc_modals()
    log.info("第 %d 个 LED-RED 放于 (%d,%d)", i + 1, x, y)
    return {"x": x, "y": y}

def wire_pair(x1, y1, x2, y2):
    """Proteus 默认模式下：点引脚末端起线 -> 点目标末端收尾。"""
    esc_modals()
    real_click(x1, y1)
    time.sleep(0.25)
    real_click(x2, y2)
    time.sleep(0.3)
    esc_modals()

# ---------------- 主流程 ----------------
def main():
    measure_only = "--measure" in sys.argv
    log.info("=== Proteus v2 开始 (measure_only=%s) ===", measure_only)
    kill_old_pds()
    if not os.path.exists(PDS) or not os.path.exists(PROJ):
        log.error("路径缺失: PDS=%s PROJ=%s", os.path.exists(PDS), os.path.exists(PROJ))
        return 2
    if md5(HEX) != HEX_MD5:
        log.error("control.hex MD5 不符: %s（红线，终止）", md5(HEX))
        return 3
    sz0 = psize(PROJ)
    log.info("工程初始大小 %d B", sz0)
    grab_cursor()
    subprocess.Popen([PDS, PROJ])

    hwnd = None
    for _ in range(24):
        time.sleep(1)
        # 启动恢复框：必须点「否」，否则主窗口不出现
        for dh, dt in dialogs():
            log.info("启动期对话框 %r", dt)
            if any(k in dt for k in ("恢复", "recover", "保存的工程")):
                if not (click_btn(dh, "否", "&N", "No") or click_btn(dh, "N")):
                    log.warning("没找到「否」按钮")
                time.sleep(1.2)
        esc_modals()
        hwnd, title = find_main()
        if hwnd:
            log.info("主窗口 %r", title)
            break
    if not hwnd:
        log.error("主窗口没出来"); restore_cursor(); return 4

    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    time.sleep(0.8)
    cmd(hwnd, CMD_VIEW_ALL)
    time.sleep(0.8)

    geo = None
    for attempt in range(8):
        img, ox, oy = grab_canvas(hwnd)
        geo = detect_u1(img, "try%d " % attempt, ox, oy)
        if geo and len(geo["rows"]) >= 30 and geo["pitch"] >= TERM_MIN_PITCH:
            break
        if geo and len(geo["rows"]) < 30:
            log.info("只检出 %d 行（引脚没分全）-> 放大", len(geo["rows"]))
            cmd(hwnd, CMD_ZOOM_IN); continue
        if geo and geo["pitch"] < TERM_MIN_PITCH:
            log.info("行距 %.1f 太小 -> 放大", geo["pitch"])
            cmd(hwnd, CMD_ZOOM_IN); continue
        log.info("检测失败/未完整入镜 -> 回整张图纸")
        cmd(hwnd, CMD_VIEW_ALL)
    if not geo:
        log.error("始终检测不到完整 U1，终止（工程未改动）"); restore_cursor(); return 5

    img, ox, oy = grab_canvas(hwnd)
    geo = detect_u1(img, "final ", ox, oy) or geo
    annotate(img, geo, os.path.join(OUT, "geo_u1.png"))
    nrow = strip_pins(img, geo, os.path.join(OUT, "pins_L.png"), "L")
    strip_pins(img, geo, os.path.join(OUT, "pins_R.png"), "R")
    geo = to_screen(geo, ox, oy)     # 之后一律用屏幕绝对坐标
    left_rows = [r for r in geo["rows"] if r["lx"]]
    rep = {"geo": {k: v for k, v in geo.items() if k != "rows"},
           "rows": geo["rows"], "n_left_rows": len(left_rows),
           "left_rows_y": [r["y"] for r in left_rows],
           "project_size": psize(PROJ)}
    with open(os.path.join(OUT, "report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    if not os.path.exists(PINMAP):
        with open(os.path.join(OUT, "pinmap_skeleton.json"), "w", encoding="utf-8") as f:
            json.dump({"L": ["?"] * len(left_rows), "R": ["?"] *
                       len([r for r in geo["rows"] if r["rx"]])}, f, indent=1)
        log.info("没找到 pinmap.json，已写 pinmap_skeleton.json（%d 左行）", len(left_rows))
    log.info("report.json 已写；左列 %d 行", len(left_rows))
    if measure_only:
        esc_modals(); restore_cursor(); log.info("=== measure 结束（工程未改动）===")
        return 0

    # ---- 用 pinmap 精确挑 P1.0/1.1/1.2 行（不再靠"最后三行"猜）
    want = list(WANT_PINS)
    picks = []
    if os.path.exists(PINMAP):
        names = json.load(open(PINMAP, encoding="utf-8")).get("L", [])
        for i, nm in enumerate(names):
            if i < len(left_rows) and any(nm.startswith(w) for w in want):
                picks.append(left_rows[i])
                log.info("pinmap: 第 %d 行 = %s -> y=%d", i, nm, left_rows[i]["y"])
    if len(picks) < N_LED:
        log.error("pinmap 没能定位到 %d 个 P1.x 行（拿到 %d）。拒绝盲放，终止。", N_LED, len(picks))
        restore_cursor(); return 7

    placed = []
    for i, row in enumerate(picks[:N_LED]):
        placed.append(place_led(hwnd, geo, i, row))
    cmd(hwnd, CMD_SAVE)
    sz1 = psize(PROJ)
    log.info("放件后工程 %d B（+%-5d vs %d）", sz1, sz1 - sz0, sz0)
    shot("02_placed.png")
    if sz1 <= sz0:
        log.error("放件没落盘！停止后续破坏性步骤"); restore_cursor(); return 6

    # ---- 洞1：载 hex
    dlg = open_u1_props(hwnd, geo)
    filled = fill_props(dlg) if dlg else False
    cmd(hwnd, CMD_SAVE)
    sz2 = psize(PROJ)
    log.info("填 hex 后工程 %d B（Δ %d），hex 字段是否写入成功=%s", sz2, sz2 - sz1, filled)

    # ---- 洞2：连线（放件后重新检测，用实测末端坐标）
    img, ox, oy = grab_canvas(hwnd)
    geor = detect_u1(img, "wired ") or geo
    annotate(img, geor, os.path.join(OUT, "geo_u1_after.png"))
    geo2 = to_screen(geor, ox, oy)
    left_rows2 = [r for r in geo2["rows"] if r["lx"]]
    # 按 y 就近匹配回放件时选定的引脚行（视图在放件后可能又动了）
    pins = []
    for pk in picks:
        near = [r for r in left_rows2 if abs(r["y"] - pk["y"]) <= 6]
        pins.append(min(near, key=lambda r: abs(r["y"] - pk["y"])) if near else None)
    log.info("连线引脚行匹配: %s", [None if p is None else p["y"] for p in pins])
    esc_modals()
    real_key(win32con.VK_ESCAPE)          # 取消任何装填态，确保进入默认选择/连线模式
    wires = 0
    for p, led in zip(pins, placed):
        if not p or p["lx"] is None:
            log.warning("某引脚行没匹配上，跳过该线")
            continue
        # LED 在左：在其与引脚之间找最靠右的黑色短线端点 = LED 引脚末端
        xt = find_lead(img, p["y"] - oy, led["x"] - ox - 45, p["lx"] - ox - 8)
        if xt is None:
            log.warning("行 y=%d 没测到 LED 引脚末端，跳过该线（不盲点）", p["y"])
            continue
        xt += ox
        wire_pair(p["lx"], p["y"], xt, p["y"])
        wires += 1
        log.info("连线 引脚(%d,%d) -> LED末端(%d,%d)", p["lx"], p["y"], xt, p["y"])
    log.info("共尝试 %d 条水平连线", wires)
    cmd(hwnd, CMD_SAVE)
    shot("03_wired.png")
    log.info("连线后工程 %d B", psize(PROJ))

    # ---- 跑仿真 + 录屏
    cmd(hwnd, CMD_RUN)
    time.sleep(1.0)
    shot("04_running.png")
    rec = os.path.join(OUT, "sim_record.mp4")
    ff = shutil_ffmpeg()
    if ff:
        subprocess.run([ff, "-y", "-f", "gdigrab", "-i", "desktop", "-t", "4", "-r", "10", rec],
                       capture_output=True)
        log.info("录屏 %s (%d B)", rec, psize(rec))
    else:
        for i in range(8):
            shot("sim_frame_%02d.png" % i)
            time.sleep(0.4)
        log.info("无 ffmpeg，改用 0.4s 连拍 8 帧")
    cmd(hwnd, CMD_SAVE)
    esc_modals()
    cmd(hwnd, 0x0234) if False else None   # 停止仿真交由用户/后续
    restore_cursor()
    log.info("=== 结束：工程 %d B，产物在 %s ===", psize(PROJ), OUT)
    return 0

def shutil_ffmpeg():
    import shutil
    for c in ("ffmpeg", r"D:\ANACONDA\Library\bin\ffmpeg.exe"):
        p = shutil.which(c) or (c if os.path.exists(c) else None)
        if p:
            return p
    return None

if __name__ == "__main__":
    sys.exit(main())
