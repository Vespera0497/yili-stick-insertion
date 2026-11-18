"""参数化草图与零件三视图生成器（2026-11-12）

数据来源（均为本项目既有文件，未新增假设尺寸）：
  - solidworks/SW_装配_三棒签_生成宏.txt  —— 零件草图原始几何（单位 m，本脚本换算 mm）
  - solidworks/v6_上料段与三视图交付说明_20261111.md —— 总装尺寸、公差、投影法、技术要求
  - solidworks/汇报图_v6/v6_三视图_标注.png —— 第一角投影布局与标题栏口径

输出：
  *.png   高清工程图（示意缩放，含尺寸链 / 几何约束 / 标题栏）
  *.dxf   AutoCAD R12，1:1 mm，图层 OBJ/CEN/REF/DIM/TXT，可导入 SOLIDWORKS 草图
  *.pdf   A3 横向合订图纸册
  参数化草图与三视图_交付说明_20261112.md

边界（重要）：
  这些是「依据 v6 参数绘制的二维工程图」，不是 SOLIDWORKS 界面截图，
  也不是原生 .SLDPRT / .SLDDRW 文件；约束状态徽章表示按所列约束推定无自由度，
  未在 SOLIDWORKS 内实测 Fully Defined。
"""

from PIL import Image, ImageDraw, ImageFont
import os, math

OUT = r"F:\伊利雪糕三棒签插签设备项目\solidworks\参数化草图与三视图_20261112"
os.makedirs(OUT, exist_ok=True)

FONT_R = r"C:\Windows\Fonts\msyh.ttc"
FONT_B = r"C:\Windows\Fonts\msyhbd.ttc"

NAVY = (24, 42, 67)
BLUE = (29, 78, 137)
CYAN = (46, 134, 193)
GREEN = (30, 132, 73)
RED = (198, 52, 52)
GRAY = (122, 140, 160)
LIGHT = (232, 238, 245)
WHITE = (255, 255, 255)
BLACK = (26, 38, 55)
BG = (250, 251, 253)

W, H = 2800, 1900
DRAW_L, DRAW_R, DRAW_T, DRAW_B = 70, 2030, 165, 1640
INFO_L, INFO_R = 2070, 2730


def F(size, bold=False):
    return ImageFont.truetype(FONT_B if bold else FONT_R, size)


# ----------------------------------------------------------------------------
# 几何数据容器：同一份 mm 坐标同时驱动 PNG 与 DXF
# ----------------------------------------------------------------------------
class Page:
    def __init__(self, code, title, subtitle, scale, cx, cy, view="SKETCH"):
        self.code, self.title, self.subtitle = code, title, subtitle
        self.scale, self.cx, self.cy = scale, cx, cy
        self.view = view
        self.sh = []          # 几何/标注实体
        self.info = []        # 右侧信息栏
        self.footer = []      # 标题栏字段
        self.status = ""
        self.notes = []

    def px(self, x, y):
        return (self.cx + x * self.scale, self.cy - y * self.scale)

    def line(self, x1, y1, x2, y2, layer="OBJ", dash=0):
        self.sh.append(("line", (x1, y1, x2, y2, layer, dash)))
        return self

    def rect(self, x1, y1, x2, y2, layer="OBJ", dash=0):
        self.line(x1, y1, x2, y1, layer, dash)
        self.line(x2, y1, x2, y2, layer, dash)
        self.line(x2, y2, x1, y2, layer, dash)
        self.line(x1, y2, x1, y1, layer, dash)
        return self

    def circle(self, x, y, r, layer="OBJ", dash=0):
        self.sh.append(("circle", (x, y, r, layer, dash)))
        return self

    def arc(self, x, y, r, a1, a2, layer="OBJ", dash=0):
        self.sh.append(("arc", (x, y, r, a1, a2, layer, dash)))
        return self

    def cline_h(self, x1, x2, y):
        return self.line(x1, y, x2, y, "CEN", 2)

    def cline_v(self, y1, y2, x):
        return self.line(x, y1, x, y2, "CEN", 2)

    def dim_h(self, x1, x2, y_obj, y_dim, label, ascii_label):
        self.sh.append(("dimh", (x1, x2, y_obj, y_dim, label, ascii_label)))
        return self

    def dim_v(self, y1, y2, x_obj, x_dim, label, ascii_label):
        self.sh.append(("dimv", (y1, y2, x_obj, x_dim, label, ascii_label)))
        return self

    def leader(self, x, y, tx, ty, label, ascii_label):
        self.sh.append(("leader", (x, y, tx, ty, label, ascii_label)))
        return self

    def badge(self, x, y, kind):
        self.sh.append(("badge", (x, y, kind)))
        return self

    def text(self, x, y, s, size=22, layer="TXT", color=None, bold=False):
        self.sh.append(("text", (x, y, s, size, layer, color, bold)))
        return self


# ----------------------------------------------------------------------------
# PNG 渲染
# ----------------------------------------------------------------------------
LAYER_COLOR = {"OBJ": BLACK, "CEN": GRAY, "REF": CYAN,
               "DIM": BLUE, "TXT": NAVY, "HATCH": (170, 182, 196)}
LAYER_WIDTH = {"OBJ": 4, "CEN": 2, "REF": 2, "DIM": 2, "HATCH": 2}
BADGE = {"H": "—", "V": "|", "O": "◎", "=": "=", "P": "•",
         "S": "↔", "T": "⊥", "M": "▣", "C": "∥"}


def dashed(d, pts, color, width, dash):
    (x1, y1), (x2, y2) = pts
    L = math.hypot(x2 - x1, y2 - y1)
    if L < 1:
        return
    ux, uy = (x2 - x1) / L, (y2 - y1) / L
    seg, gap = (20, 7) if dash == 1 else (26, 6)
    p = 0.0
    on = True
    while p < L:
        q = min(L, p + (seg if on else gap))
        if on:
            d.line((x1 + ux * p, y1 + uy * p, x1 + ux * q, y1 + uy * q),
                   fill=color, width=width)
        p = q
        on = not on
        if dash == 2 and not on:      # 点划线：间隙段中间补一个点
            m = p + gap / 2
            if m < L:
                d.ellipse((x1 + ux * m - 1.5, y1 + uy * m - 1.5,
                           x1 + ux * m + 1.5, y1 + uy * m + 1.5), fill=color)


def arrow(d, x, y, ang, color=BLUE, size=13):
    a = math.radians(ang)
    bx, by = x - size * math.cos(a), y - size * math.sin(a)
    n = (math.cos(a + math.pi / 2), math.sin(a + math.pi / 2))
    d.polygon([(x, y),
               (bx + 4.5 * n[0], by + 4.5 * n[1]),
               (bx - 4.5 * n[0], by - 4.5 * n[1])], fill=color)


def textbox(d, x, y, s, font, color, anchor="mm", pad=6, bg=None):
    bb = d.textbbox((0, 0), s, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    if anchor == "mm":
        x0, y0 = x - tw / 2, y - th / 2
    elif anchor == "lm":
        x0, y0 = x, y - th / 2
    elif anchor == "rm":
        x0, y0 = x - tw, y - th / 2
    else:
        x0, y0 = x, y
    if bg:
        d.rectangle((x0 - pad, y0 - pad - 2, x0 + tw + pad, y0 + th + pad),
                    fill=bg)
    d.text((x0 - bb[0], y0 - bb[1]), s, font=font, fill=color)
    return tw, th


def render_png(page, path):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    s = page.scale

    # 顶部标题带
    d.rectangle((0, 0, W, 118), fill=NAVY)
    d.rectangle((0, 114, W, 118), fill=(239, 108, 30))
    textbox(d, 60, 42, page.title, F(40, True), WHITE, "lm")
    textbox(d, 60, 88, page.subtitle, F(20), (196, 214, 232), "lm")
    textbox(d, W - 60, 58, "SIS · 参数化草图与零件三视图", F(22), WHITE, "rm")

    # 绘图区（淡网格，接近 CAD 草图背景）
    d.rectangle((DRAW_L, DRAW_T, DRAW_R, DRAW_B), fill=(247, 249, 252),
                outline=(216, 226, 236), width=2)
    for gx in range(DRAW_L + 40, DRAW_R, 40):
        d.line((gx, DRAW_T, gx, DRAW_B), fill=(237, 242, 248), width=1)
    for gy in range(DRAW_T + 40, DRAW_B, 40):
        d.line((DRAW_L, gy, DRAW_R, gy), fill=(237, 242, 248), width=1)

    P = page.px
    f_dim = F(22)
    f_small = F(19)

    for kind, v in page.sh:
        if kind == "line":
            x1, y1, x2, y2, layer, dash = v
            a, b = P(x1, y1), P(x2, y2)
            col, wd = LAYER_COLOR[layer], LAYER_WIDTH[layer]
            if dash:
                dashed(d, (a, b), col, wd, dash)
            else:
                d.line((a[0], a[1], b[0], b[1]), fill=col, width=wd)

        elif kind == "circle":
            x, y, r, layer, dash = v
            cx, cy = P(x, y)
            rr = r * s
            box = (cx - rr, cy - rr, cx + rr, cy + rr)
            if dash:
                # 点划圆：按弧段近似
                seg = 24
                for i in range(seg):
                    if dash == 2 and i % 2:
                        continue
                    a1 = 2 * math.pi * i / seg
                    a2 = 2 * math.pi * (i + 0.62) / seg
                    pts = [(cx + rr * math.cos(a1 + (a2 - a1) * k / 6),
                            cy - rr * math.sin(a1 + (a2 - a1) * k / 6)) for k in range(7)]
                    d.line(pts, fill=LAYER_COLOR[layer], width=LAYER_WIDTH[layer])
            else:
                d.ellipse(box, outline=LAYER_COLOR[layer], width=LAYER_WIDTH[layer])

        elif kind == "arc":
            x, y, r, a1, a2, layer, dash = v
            cx, cy = P(x, y)
            rr = r * s
            pts = []
            n = 48
            for i in range(n + 1):
                a = math.radians(a1 + (a2 - a1) * i / n)
                pts.append((cx + rr * math.cos(a), cy - rr * math.sin(a)))
            d.line(pts, fill=LAYER_COLOR[layer], width=LAYER_WIDTH[layer])

        elif kind in ("dimh", "dimv"):
            if kind == "dimh":
                x1, x2, y_obj, y_dim, label, alabel = v
                a, b = P(x1, y_dim), P(x2, y_dim)
                e1, e2 = P(x1, y_obj), P(x2, y_obj)
                d.line((e1[0], e1[1], a[0] + (6 if x1 < x2 else -6), a[1]), fill=BLUE, width=2)
                d.line((e2[0], e2[1], b[0] + (-6 if x1 < x2 else 6), b[1]), fill=BLUE, width=2)
                d.line((a[0], a[1], b[0], b[1]), fill=BLUE, width=2)
                arrow(d, a[0], a[1], 0 if x1 < x2 else 180)
                arrow(d, b[0], b[1], 180 if x1 < x2 else 0)
                tx, ty = (a[0] + b[0]) / 2, a[1] - 20
            else:
                y1, y2, x_obj, x_dim, label, alabel = v
                a, b = P(x_dim, y1), P(x_dim, y2)
                e1, e2 = P(x_obj, y1), P(x_obj, y2)
                d.line((e1[0], e1[1], a[0], a[1] + 6), fill=BLUE, width=2)
                d.line((e2[0], e2[1], b[0], b[1] - 6), fill=BLUE, width=2)
                d.line((a[0], a[1], b[0], b[1]), fill=BLUE, width=2)
                arrow(d, a[0], a[1], -90 if y1 < y2 else 90)
                arrow(d, b[0], b[1], 90 if y1 < y2 else -90)
                tx, ty = a[0] - 34, (a[1] + b[1]) / 2
            textbox(d, tx, ty, label, f_dim, BLUE, "mm", pad=7, bg=(247, 249, 252))

        elif kind == "leader":
            x, y, tx, ty, label, alabel = v
            a, b = P(x, y), P(tx, ty)
            d.line((a[0], a[1], b[0], b[1]), fill=BLUE, width=2)
            d.line((b[0], b[1], b[0] + (70 if tx >= x else -70), b[1]), fill=BLUE, width=2)
            ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            arrow(d, a[0], a[1], ang + 180)
            textbox(d, b[0] + (40 if tx >= x else -40), b[1] - 16, label,
                    f_small, BLUE, "mm", pad=6, bg=(247, 249, 252))

        elif kind == "badge":
            x, y, k = v
            bx, by = P(x, y)
            d.rounded_rectangle((bx - 17, by - 17, bx + 17, by + 17), radius=5,
                                fill=GREEN, outline=WHITE, width=2)
            textbox(d, bx, by - 1, BADGE.get(k, "•"), F(19, True), WHITE, "mm")

        elif kind == "text":
            x, y, txt, size, layer, color, bold = v
            bx, by = P(x, y)
            textbox(d, bx, by, txt, F(size, bold), color or LAYER_COLOR[layer], "mm")

    # 原点标记（仅草图页：SW 风格红/蓝轴）
    if page.view == "SKETCH":
        ox, oy = P(0, 0)
        d.line((ox, oy, ox + 62, oy), fill=RED, width=3)
        arrow(d, ox + 62, oy, 0, RED, 12)
        d.line((ox, oy, ox, oy - 62), fill=CYAN, width=3)
        arrow(d, ox, oy - 62, -90, CYAN, 12)
        textbox(d, ox + 74, oy - 4, "X", F(18, True), RED, "lm")
        textbox(d, ox + 8, oy - 80, "Y", F(18, True), CYAN, "lm")

    # 状态徽章
    if page.status:
        d.rounded_rectangle((DRAW_R - 470, DRAW_T + 22, DRAW_R - 22, DRAW_T + 82),
                            radius=10, fill=(232, 245, 236), outline=GREEN, width=2)
        textbox(d, DRAW_R - 246, DRAW_T + 52, page.status, F(24, True), GREEN, "mm")

    # 右侧信息栏
    d.rectangle((INFO_L, DRAW_T, INFO_R, DRAW_B), fill=WHITE,
                outline=(216, 226, 236), width=2)
    y = DRAW_T + 24
    for item in page.info:
        kind = item[0]
        if kind == "h":
            textbox(d, INFO_L + 24, y + 12, item[1], F(24, True), NAVY, "lm")
            y += 52
            d.line((INFO_L + 20, y, INFO_R - 20, y), fill=LIGHT, width=2)
            y += 16
        elif kind == "row":
            textbox(d, INFO_L + 24, y + 12, item[1], F(19), (92, 110, 130), "lm")
            textbox(d, INFO_R - 24, y + 12, item[2], F(20, True), NAVY, "rm")
            y += 42
        elif kind == "note":
            textbox(d, INFO_L + 24, y + 12, item[1], F(18), (92, 110, 130), "lm")
            y += 38
        elif kind == "legend":
            bx, by = INFO_L + 34, y + 18
            d.rounded_rectangle((bx - 15, by - 15, bx + 15, by + 15), radius=4, fill=GREEN)
            textbox(d, bx, by, BADGE.get(item[2], "•"), F(17, True), WHITE, "mm")
            textbox(d, INFO_L + 68, y + 18, item[1], F(19), NAVY, "lm")
            y += 40
        elif kind == "gap":
            y += 18

    # 底部标题栏
    d.rectangle((0, 1670, W, H), fill=WHITE)
    d.line((0, 1670, W, 1670), fill=NAVY, width=3)
    d.rectangle((DRAW_L, 1700, INFO_R, 1850), outline=NAVY, width=2)
    cols = [(DRAW_L, 420), (490, 620), (1110, 700), (1810, 920)]
    for x0, wdt in cols[:-1]:
        d.line((x0 + wdt, 1700, x0 + wdt, 1850), fill=(190, 204, 218), width=2)
    d.line((DRAW_L, 1774, INFO_R, 1774), fill=(190, 204, 218), width=2)
    f = [(page.code, "图号 / DWG NO."),
         (page.title, "名称 / TITLE"),
         ("1:1 (DXF, mm)", "比例 / SCALE"),
         ("第一角投影", "投影 / PROJECTION"),
         ("未指定（模型按默认密度 / 外观着色）", "材料 / MATERIAL"),
         ("GB/T 1804-m · 未注圆角 R2", "公差 / TOLERANCE"),
         ("2026-11-12", "日期 / DATE"),
         ("SIS / v6 参数", "版本 / REV")]
    for i, (val, key) in enumerate(f):
        c = i % 4
        r = i // 4
        x0 = [DRAW_L, 490, 1110, 1810][c]
        yy = 1700 + r * 74
        textbox(d, x0 + 18, yy + 15, key, F(15), GRAY, "lm")
        textbox(d, x0 + 18, yy + 47, val, F(20, True), NAVY, "lm")
    textbox(d, W - 60, 1872,
            "二维工程图 · 依据 v6 参数绘制 · 非 SOLIDWORKS 界面截图 / 非原生 SLDDRW",
            F(17), GRAY, "rm")

    im.save(path, optimize=True)
    return im.size


# ----------------------------------------------------------------------------
# DXF R12 渲染（1:1 mm；文字用 ASCII 避免 R12 中文编码问题）
# ----------------------------------------------------------------------------
DXF_LAYERS = [("OBJ", 7), ("CEN", 4), ("REF", 5), ("DIM", 5),
              ("TXT", 7), ("HATCH", 8)]


class Dxf:
    def __init__(self):
        self.e = []

    def add(self, code, val):
        self.e.append(f"{code}\n{val}\n")

    def ent(self, typ, layer, pairs):
        self.add(0, typ)
        self.add(8, layer)
        for c, v in pairs:
            self.add(c, v)

    def line(self, x1, y1, x2, y2, layer="OBJ"):
        self.ent("LINE", layer, [(10, f"{x1:.3f}"), (20, f"{y1:.3f}"), (30, "0"),
                                 (11, f"{x2:.3f}"), (21, f"{y2:.3f}"), (31, "0")])

    def circle(self, x, y, r, layer="OBJ"):
        self.ent("CIRCLE", layer, [(10, f"{x:.3f}"), (20, f"{y:.3f}"),
                                   (30, "0"), (40, f"{r:.3f}")])

    def arc(self, x, y, r, a1, a2, layer="OBJ"):
        self.ent("ARC", layer, [(10, f"{x:.3f}"), (20, f"{y:.3f}"), (30, "0"),
                                (40, f"{r:.3f}"), (50, f"{a1:.2f}"), (51, f"{a2:.2f}")])

    def text(self, x, y, s, h=4.0, layer="TXT", rot=0):
        s = s.encode("ascii", "replace").decode("ascii")
        self.ent("TEXT", layer, [(10, f"{x:.3f}"), (20, f"{y:.3f}"), (30, "0"),
                                 (40, f"{h:.2f}"), (1, s), (50, f"{rot:.1f}")])

    def save(self, path):
        out = ["0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1009\n0\nENDSEC\n",
               "0\nSECTION\n2\nTABLES\n0\nTABLE\n2\nLAYER\n70\n%d\n" % len(DXF_LAYERS)]
        for name, col in DXF_LAYERS:
            out.append(f"0\nLAYER\n2\n{name}\n70\n0\n62\n{col}\n6\nCONTINUOUS\n")
        out.append("0\nENDTAB\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n")
        out.extend(self.e)
        out.append("0\nENDSEC\n0\nEOF\n")
        with open(path, "w", encoding="ascii") as fh:
            fh.write("".join(out))


def render_dxf(page, path):
    dx = Dxf()
    for kind, v in page.sh:
        if kind == "line":
            x1, y1, x2, y2, layer, dash = v
            dx.line(x1, y1, x2, y2, layer)
        elif kind == "circle":
            x, y, r, layer, dash = v
            dx.circle(x, y, r, layer)
        elif kind == "arc":
            x, y, r, a1, a2, layer, dash = v
            dx.arc(x, y, r, a1, a2, layer)
        elif kind in ("dimh", "dimv"):
            if kind == "dimh":
                x1, x2, y_obj, y_dim, label, alabel = v
                ext = 2.0
                dx.line(x1, y_obj, x1, y_dim + ext, "DIM")
                dx.line(x2, y_obj, x2, y_dim + ext, "DIM")
                dx.line(x1, y_dim, x2, y_dim, "DIM")
                dx.text((x1 + x2) / 2 - 6, y_dim + 3, alabel, 4.0, "TXT")
                for xa, ang in ((x1, 180), (x2, 0)):
                    dx.line(xa, y_dim, xa + (3 if ang == 180 else -3), y_dim + 1, "DIM")
                    dx.line(xa, y_dim, xa + (3 if ang == 180 else -3), y_dim - 1, "DIM")
            else:
                y1, y2, x_obj, x_dim, label, alabel = v
                ext = 2.0
                dx.line(x_obj, y1, x_dim + (ext if x_dim > x_obj else -ext), y1, "DIM")
                dx.line(x_obj, y2, x_dim + (ext if x_dim > x_obj else -ext), y2, "DIM")
                dx.line(x_dim, y1, x_dim, y2, "DIM")
                dx.text(x_dim + 3, (y1 + y2) / 2, alabel, 4.0, "TXT", 90)
        elif kind == "leader":
            x, y, tx, ty, label, alabel = v
            dx.line(x, y, tx, ty, "DIM")
            dx.line(tx, ty, tx + (16 if tx >= x else -16), ty, "DIM")
            dx.text(tx + (2 if tx >= x else -30), ty + 3, alabel, 4.0, "TXT")
        elif kind == "text":
            x, y, txt, size, layer, color, bold = v
            t = txt.encode("ascii", "replace").decode("ascii")
            dx.text(x, y, t, 4.0, "TXT")
    dx.save(path)


# ----------------------------------------------------------------------------
# 三张参数化草图
# ----------------------------------------------------------------------------
def sketch_rack():
    p = Page("SIS-SK-01", "排架底板 · 参数化草图",
             "前视基准面 XY  |  单位 mm  |  几何与尺寸取自 SW 生成宏（150×40×8 / 3×Φ4.5 / 中心距 50）",
             9.0, 1050, 830, "SKETCH")
    p.rect(-75, -20, 75, 20)
    for x in (-50, 0, 50):
        p.circle(x, 0, 2.25)
        p.circle(x, 0, 5.0, "REF", 2)       # 导向套 Φ10 外圆（构造线）
        p.cline_v(-26, 26, x)
    p.cline_h(-95, 95, 0)
    p.cline_v(-58, 58, 0)
    # 尺寸链
    p.dim_h(-75, 75, -20, -42, "150", "150")
    p.dim_v(-20, 20, 75, 97, "40", "40")
    p.dim_h(-50, 0, 6, 34, "50", "50")
    p.dim_h(0, 50, 6, 34, "50", "50")
    p.dim_h(-75, -50, -20, -68, "25", "25")
    p.leader(-50 + 2.25, 0, -62, 50, "3×Φ4.5 通孔", "3xD4.5 THRU")
    p.leader(50 + 5, 0, 86, 52, "3×Φ10 导向套", "3xD10 BUSH")
    # 约束符号
    for x, y, k in [(-36, 20, "H"), (36, 20, "H"), (-75, -10, "V"), (75, 10, "V"),
                    (0, 0, "S"), (-50, 0, "O"), (0, 0, "O"), (50, 0, "O")]:
        p.badge(x, y, k)
    p.status = "约束方案：完全定义（0 自由度）"
    p.info = [
        ("h", "尺寸链 / DIMENSIONS"),
        ("row", "底板轮廓", "150 × 40"),
        ("row", "拉伸厚度", "8"),
        ("row", "通孔", "3 × Φ4.5"),
        ("row", "导向套", "3 × Φ10 / Φ4.5"),
        ("row", "孔中心距", "50 / 50"),
        ("row", "孔至端面", "25"),
        ("h", "几何约束 / CONSTRAINTS"),
        ("legend", "水平 / 竖直（矩形四边）", "H"),
        ("legend", "对称（关于原点）", "S"),
        ("legend", "同心（导向套与通孔）", "O"),
        ("legend", "相等（三孔等径）", "="),
        ("legend", "点在中心线上", "P"),
        ("gap",),
        ("note", "约束状态按上列清单推定；"),
        ("note", "未在 SOLIDWORKS 内实测。"),
        ("note", "DXF 导入后按此清单补加。"),
        ("h", "来源 / SOURCE"),
        ("note", "SW_装配_三棒签_生成宏.txt"),
        ("note", "v6 交付说明 §6"),
    ]
    return p


def sketch_frame():
    p = Page("SIS-SK-02", "机架底板 · 参数化草图",
             "前视基准面 XY  |  单位 mm  |  300×200×20 底板 + 4 根 40×40 立柱（中心 ±120 / ±70）",
             5.4, 1050, 830, "SKETCH")
    p.rect(-150, -100, 150, 100)
    for x in (-120, 120):
        for y in (-70, 70):
            p.rect(x - 20, y - 20, x + 20, y + 20)
            p.cline_h(x - 26, x + 26, y)
            p.cline_v(y - 26, y + 26, x)
    p.cline_h(-172, 172, 0)
    p.cline_v(-122, 122, 0)
    p.dim_h(-150, 150, -100, -122, "300", "300")
    p.dim_v(-100, 100, 150, 172, "200", "200")
    p.dim_h(-120, 120, 92, 116, "240", "240")
    p.dim_v(-70, 70, -142, -164, "140", "140")
    p.dim_h(-140, -120, 70, 96, "20", "20")
    for x, y, k in [(-70, 100, "H"), (70, 100, "H"), (-150, -40, "V"), (150, 40, "V"),
                    (-120, 70, "="), (120, -70, "="), (0, 0, "S")]:
        p.badge(x, y, k)
    p.status = "约束方案：完全定义（0 自由度）"
    p.info = [
        ("h", "尺寸链 / DIMENSIONS"),
        ("row", "底板轮廓", "300 × 200"),
        ("row", "底板厚度", "20"),
        ("row", "立柱截面", "4 × 40 × 40"),
        ("row", "立柱中心距 X", "240 (±120)"),
        ("row", "立柱中心距 Y", "140 (±70)"),
        ("row", "立柱至板边", "10"),
        ("row", "立柱高度", "380"),
        ("h", "几何约束 / CONSTRAINTS"),
        ("legend", "水平 / 竖直", "H"),
        ("legend", "对称（四角布列）", "S"),
        ("legend", "相等（四立柱截面）", "="),
        ("legend", "重合（截面中心）", "P"),
        ("gap",),
        ("note", "机架为 v6 装配唯一固定"),
        ("note", "基准件，安装面 Z=0。"),
        ("h", "来源 / SOURCE"),
        ("note", "SW 生成宏 buildFrame()"),
        ("note", "v6 交付说明 §6"),
    ]
    return p


def sketch_stations():
    p = Page("SIS-SK-03", "三工位布局 · 参数化草图",
             "装配布局基准  |  单位 mm  |  三签中心 −50 / 0 / +50、定位座 Φ30、木签截面 10×2、单缸行程 30",
             8.0, 1050, 830, "SKETCH")
    for i, x in enumerate((-50, 0, 50)):
        p.circle(x, 0, 15, "REF", 2)          # 雪糕定位座 Φ30
        p.circle(x, 0, 2.25)                  # 导向孔 Φ4.5
        p.rect(x - 5, -1, x + 5, 1)           # 木签 10×2 截面
        p.cline_v(-24, 24, x)
        p.text(x, -22, "工位 %d" % (i + 1), 20, "TXT", NAVY)
    p.cline_h(-92, 92, 0)
    p.cline_v(-46, 46, 0)
    p.dim_h(-50, 0, 18, 42, "50", "50")
    p.dim_h(0, 50, 18, 42, "50", "50")
    p.dim_v(-1, 1, 55, 76, "2", "2")
    p.dim_h(-55, -45, -1, -24, "10", "10")
    p.leader(-50 + 15, 0, -74, 56, "3×Φ30 定位座", "3xD30 SEAT")
    p.leader(50 + 2.25, 0, 76, 52, "3×Φ4.5 导向孔", "3xD4.5 GUIDE")
    p.dim_h(-50, 50, -36, -58, "三工位跨距 100", "SPAN 100")
    for x, y, k in [(-50, 0, "O"), (0, 0, "O"), (50, 0, "O"),
                    (0, 0, "S"), (-25, 0, "="), (25, 0, "=")]:
        p.badge(x, y, k)
    p.status = "约束方案：完全定义（0 自由度）"
    p.info = [
        ("h", "布局参数 / LAYOUT"),
        ("row", "工位中心", "−50 / 0 / +50"),
        ("row", "工位中心距", "50"),
        ("row", "定位座外径", "Φ30 × 40"),
        ("row", "导向孔", "Φ4.5"),
        ("row", "木签截面", "10 × 2 × 110"),
        ("row", "单缸行程", "30"),
        ("h", "节拍（固件口径）"),
        ("row", "错峰启动", "0 / 125 / 250 ms"),
        ("row", "到位 / 保持", "450 / 500 ms"),
        ("row", "复位", "350 ms"),
        ("h", "几何约束 / CONSTRAINTS"),
        ("legend", "同心（孔 / 座 / 签）", "O"),
        ("legend", "对称（关于中工位）", "S"),
        ("legend", "相等（三工位）", "="),
        ("legend", "水平共线", "H"),
        ("note", "布局草图为装配定位依据，"),
        ("note", "非零件加工图。"),
    ]
    return p


# ----------------------------------------------------------------------------
# 三张零件三视图（第一角投影：主视 / 俯视 / 左视）
# ----------------------------------------------------------------------------
def ortho_rack():
    p = Page("SIS-DR-01", "排架（导向板）· 零件三视图",
             "第一角投影  |  单位 mm  |  150×40×8 底板 + 3 组 Φ10/Φ4.5 导向套（高 6）",
             5.0, 900, 900, "DRAWING")
    # 主视图（XY 面投影，放在上方：X 横 / Z 竖，用局部坐标 y 表示为 Z）
    # 为在同一 XY 画布表达三视图，采用布局偏移：主视中心 (0,+60)、俯视 (0,-60)、左视 (+250,+60)
    # 主视：宽 150、高 8 底板
    p.rect(-75, 56, 75, 64)
    for x in (-50, 0, 50):
        p.rect(x - 5, 64, x + 5, 70)                 # 导向套外轮廓 Φ10 × 6
        p.line(x - 2.25, 56, x - 2.25, 70, "REF", 1)  # 通孔虚线
        p.line(x + 2.25, 56, x + 2.25, 70, "REF", 1)
        p.cline_v(52, 74, x)
    p.cline_h(-90, 90, 60)
    # 俯视图（下方）
    p.rect(-75, -80, 75, -40)
    for x in (-50, 0, 50):
        p.circle(x, -60, 5)
        p.circle(x, -60, 2.25)
        p.cline_v(-86, -34, x)
    p.cline_h(-90, 90, -60)
    # 左视图（右侧，宽 40 / 高 8 + 导向套）
    L = 175
    p.rect(L - 20, 56, L + 20, 64)
    p.rect(L - 5, 64, L + 5, 70)
    p.line(L - 2.25, 56, L - 2.25, 70, "REF", 1)
    p.line(L + 2.25, 56, L + 2.25, 70, "REF", 1)
    p.cline_v(52, 74, L)
    # 视图标签
    p.text(0, 40, "主视图", 21, "TXT", NAVY, True)
    p.text(0, -96, "俯视图", 21, "TXT", NAVY, True)
    p.text(L, 40, "左视图", 21, "TXT", NAVY, True)
    # 尺寸
    p.dim_h(-75, 75, 56, 86, "150", "150")
    p.dim_h(-50, 0, -40, -26, "50", "50")
    p.dim_h(0, 50, -40, -26, "50", "50")
    p.dim_v(-80, -40, 75, 95, "40", "40")
    p.dim_v(56, 64, -75, -95, "8", "8")
    p.leader(50 + 5, 67, 92, 100, "3×Φ10/Φ4.5 导向套 h6", "3xD10/D4.5 BUSH")
    p.leader(50 + 2.25, -60, 96, -12, "3×Φ4.5 通孔", "3xD4.5 THRU")
    p.status = "第一角投影"
    p.info = [
        ("h", "关键尺寸 / KEY DIM."),
        ("row", "底板", "150 × 40 × 8"),
        ("row", "通孔", "3 × Φ4.5"),
        ("row", "导向套", "Φ10 / Φ4.5"),
        ("row", "导向套高", "6"),
        ("row", "孔中心距", "50 / 50"),
        ("row", "孔至端面", "25"),
        ("h", "技术要求 / NOTES"),
        ("note", "1. 单位 mm；未注公差"),
        ("note", "   GB/T 1804-m，未注圆角 R2。"),
        ("note", "2. 三孔与木签为间隙配合，"),
        ("note", "   轴线对基准 A 同轴。"),
        ("note", "3. 导向套孔 h6，去毛刺。"),
        ("note", "4. 材料：模型未赋真实材质，"),
        ("note", "   当前按默认密度 / 外观着色。"),
        ("h", "来源 / SOURCE"),
        ("note", "SW 生成宏 buildRack()"),
        ("note", "v6 交付说明 §6"),
    ]
    return p


def ortho_frame():
    p = Page("SIS-DR-02", "机架底板 · 零件三视图",
             "第一角投影  |  单位 mm  |  300×200×20 底板 + 4 根 40×40 立柱（真实高 380）；基准 A = 安装面 Z=0",
             1.9, 900, 980, "DRAWING")
    # 主视图（X 横 / Z 竖）：底板 300×20，两根可见立柱 40×380
    p.rect(-150, 0, 150, 20)
    for x in (-120, 120):
        p.rect(x - 20, 20, x + 20, 400)
        p.cline_v(-4, 410, x)
    p.cline_h(-170, 170, 10)
    # 俯视图（下方，Y 向 200）
    p.rect(-150, -280, 150, -80)
    for x in (-120, 120):
        for y in (-230, -90):
            p.rect(x - 20, y - 20, x + 20, y + 20)
    p.cline_h(-170, 170, -180)
    # 左视图（右侧，宽 200）
    L = 245
    p.rect(L - 100, 0, L + 100, 20)
    for y in (-70, 70):
        p.rect(L + y - 20, 20, L + y + 20, 400)
    p.cline_h(L - 120, L + 120, 10)
    p.text(0, -55, "主视图", 21, "TXT", NAVY, True)
    p.text(0, -320, "俯视图", 21, "TXT", NAVY, True)
    p.text(L, -55, "左视图", 21, "TXT", NAVY, True)
    p.dim_h(-150, 150, 0, -25, "300", "300")
    p.dim_h(-120, 120, -280, -300, "240", "240")
    p.dim_v(-280, -80, 150, 175, "200", "200")
    p.dim_v(20, 400, -150, -190, "380", "380")
    p.dim_v(-230, -90, -150, -180, "140", "140")
    p.leader(140, 300, 205, 355, "4×40×40 立柱，高 380", "4x 40x40 POST H380")
    p.leader(140, -90, 205, -30, "立柱至板边 10", "EDGE 10")
    p.status = "第一角投影"
    p.info = [
        ("h", "关键尺寸 / KEY DIM."),
        ("row", "底板", "300 × 200 × 20"),
        ("row", "立柱截面", "4 × 40 × 40"),
        ("row", "立柱高度", "380"),
        ("row", "中心距 X / Y", "240 / 140"),
        ("row", "立柱至板边", "10"),
        ("row", "地脚", "M12 调节脚垫"),
        ("row", "视图布局", "主 / 俯 / 左"),
        ("h", "技术要求 / NOTES"),
        ("note", "1. 单位 mm；未注公差"),
        ("note", "   GB/T 1804-m，未注圆角 R2。"),
        ("note", "2. 基准 A：机架安装面 Z=0。"),
        ("note", "3. 四立柱对基准 A 垂直，"),
        ("note", "   现场找平后紧固。"),
        ("note", "4. 材料：模型未赋真实材质，"),
        ("note", "   v6 仅上料支架按 2700 kg/m³。"),
        ("h", "来源 / SOURCE"),
        ("note", "SW 生成宏 buildFrame()"),
        ("note", "v6 交付说明 §4 / §6"),
    ]
    return p


def ortho_plate():
    p = Page("SIS-DR-03", "推板 · 零件三视图",
             "第一角投影  |  单位 mm  |  150×30×12 刚性推板，三缸同步驱动，单缸行程 30",
             6.0, 900, 900, "DRAWING")
    p.rect(-75, 56, 75, 68)
    p.cline_h(-90, 90, 62)
    p.rect(-75, -75, 75, -45)
    for x in (-50, 0, 50):
        p.cline_v(-81, -39, x)
    p.cline_h(-90, 90, -60)
    L = 165
    p.rect(L - 15, 56, L + 15, 68)
    p.cline_h(L - 30, L + 30, 62)
    p.text(0, 40, "主视图", 21, "TXT", NAVY, True)
    p.text(0, -92, "俯视图", 21, "TXT", NAVY, True)
    p.text(L, 40, "左视图", 21, "TXT", NAVY, True)
    p.dim_h(-75, 75, 56, 86, "150", "150")
    p.dim_v(56, 68, -75, -95, "12", "12")
    p.dim_v(-75, -45, 75, 95, "30", "30")
    p.dim_h(-50, 0, -45, -28, "50", "50")
    p.dim_h(0, 50, -45, -28, "50", "50")
    p.text(0, 110, "三缸作用点 −50 / 0 / +50，节拍 0 / 125 / 250 ms 错峰", 20, "TXT", NAVY)
    p.status = "第一角投影"
    p.info = [
        ("h", "关键尺寸 / KEY DIM."),
        ("row", "推板", "150 × 30 × 12"),
        ("row", "气缸作用点", "−50 / 0 / +50"),
        ("row", "单缸行程", "30"),
        ("row", "气缸规格", "3 × Φ32 × 30"),
        ("row", "气源", "0.6 MPa"),
        ("h", "技术要求 / NOTES"),
        ("note", "1. 单位 mm；未注公差"),
        ("note", "   GB/T 1804-m，未注圆角 R2。"),
        ("note", "2. 推板为运动件，装配中"),
        ("note", "   保留插签方向移动自由度，"),
        ("note", "   不得完全锁死。"),
        ("note", "3. 三缸推杆同步找正，"),
        ("note", "   错峰节拍由固件控制。"),
        ("h", "来源 / SOURCE"),
        ("note", "SW 生成宏 buildPushPlate()"),
        ("note", "v6 交付说明 §6"),
    ]
    return p


def main():
    pages = [sketch_rack(), sketch_frame(), sketch_stations(),
             ortho_rack(), ortho_frame(), ortho_plate()]
    names = ["草图_01_排架底板", "草图_02_机架底板", "草图_03_三工位布局",
             "三视图_01_排架", "三视图_02_机架底板", "三视图_03_推板"]
    made = []
    for p, n in zip(pages, names):
        png = os.path.join(OUT, n + ".png")
        dxf = os.path.join(OUT, n + ".dxf")
        render_png(p, png)
        render_dxf(p, dxf)
        made.append((n, png, dxf))
        print("OK", n, os.path.getsize(png), os.path.getsize(dxf))

    # A3 横向合订 PDF：每页嵌入一张 PNG
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A3, landscape
        pdf = os.path.join(OUT, "参数化草图与零件三视图_图纸册_20261112.pdf")
        c = canvas.Canvas(pdf, pagesize=landscape(A3))
        pw, ph = landscape(A3)
        for _, png, _ in made:
            im = Image.open(png)
            r = min((pw - 24) / im.width, (ph - 24) / im.height)
            w, h = im.width * r, im.height * r
            c.drawImage(png, (pw - w) / 2, (ph - h) / 2, w, h)
            c.showPage()
        c.save()
        print("PDF", pdf, os.path.getsize(pdf))
    except Exception as e:
        print("PDF_SKIP", e)
    return made


if __name__ == "__main__":
    main()
