"""由六张工程图生成两张 PPT 证据拼图（1920×620，三格横排）。

只裁绘图区（去掉右侧信息栏与底部标题栏），等比缩放，不拉伸。
完整尺寸链、约束清单与标题栏保留在单张 PNG / PDF 图纸册里。
"""
import os
from PIL import Image, ImageDraw, ImageFont

D = r"F:\伊利雪糕三棒签插签设备项目\solidworks\参数化草图与三视图_20261112"
FONT_B = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_R = r"C:\Windows\Fonts\msyh.ttc"
NAVY = (24, 42, 67)
PALE = (241, 245, 249)
MUTED = (106, 128, 153)
ORANGE = (239, 108, 30)

GROUPS = [
    ("草图_证据拼图.png", "参数化草图 · 尺寸链与几何约束",
     [("草图_01_排架底板.png", "草图 01 · 排架底板 150×40×8"),
      ("草图_02_机架底板.png", "草图 02 · 机架底板 300×200×20"),
      ("草图_03_三工位布局.png", "草图 03 · 三工位布局 跨距 100")],
     "完整尺寸链 / 约束清单 / 标题栏见 A3 图纸册与单张 PNG；DXF 为 1:1 mm，可导入 SOLIDWORKS 草图"),
    ("三视图_证据拼图.png", "零件三视图 · 第一角投影",
     [("三视图_01_排架.png", "三视图 01 · 排架 150×40×8"),
      ("三视图_02_机架底板.png", "三视图 02 · 机架底板 300×200×20"),
      ("三视图_03_推板.png", "三视图 03 · 推板 150×30×12")],
     "主视 / 俯视 / 左视按第一角投影布置，与 v6 总装三视图相互独立；非实机运行证据"),
]

W, H = 1920, 620
HEAD, LABEL, CELL_H, FOOT = 56, 34, 460, 70


def build(out_name, title, items, footer):
    cv = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(cv)
    d.rectangle((0, 0, W, HEAD), fill=NAVY)
    d.rectangle((0, HEAD - 4, W, HEAD), fill=ORANGE)
    d.text((18, 12), title, font=ImageFont.truetype(FONT_B, 28), fill=(255, 255, 255))

    y_img = HEAD + LABEL
    for i, (fname, label) in enumerate(items):
        x0 = 10 + i * 640
        d.rectangle((x0, HEAD, x0 + 620, y_img), fill=PALE)
        d.rectangle((x0, HEAD, x0 + 5, y_img), fill=ORANGE)
        d.text((x0 + 16, HEAD + 5), label,
               font=ImageFont.truetype(FONT_B, 20), fill=NAVY)

        src = Image.open(os.path.join(D, fname)).convert("RGB")
        crop = src.crop((70, 165, 2030, 1640))          # 绘图区 1960×1475
        crop = crop.resize((610, 459), Image.LANCZOS)
        cv.paste(crop, (x0 + 5, y_img))
        d.rectangle((x0 + 5, y_img, x0 + 615, y_img + CELL_H),
                    outline=(220, 228, 237), width=2)

    d.rectangle((0, H - FOOT, W, H), fill=PALE)
    d.text((18, H - FOOT + 22), footer,
           font=ImageFont.truetype(FONT_R, 20), fill=MUTED)
    out = os.path.join(D, out_name)
    cv.save(out, optimize=True)
    print(out, cv.size, os.path.getsize(out))


if __name__ == "__main__":
    for g in GROUPS:
        build(*g)
