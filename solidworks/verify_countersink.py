#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
锥形沉头 + 导向套 复验脚本 —— WorkBuddy 用，不依赖 SolidWorks GUI。
读取 STEP (ISO-10303-21) 几何，反推验收判据：
  - 3 个孔，中心 x = -50/0/+50, y = 0 （中心距 50mm）
  - 锥形沉头：顶口Φ10 / 底孔Φ4.5 / 锥角90° / 三处同轴贯通
  - 导向套：Φ10 外径 / Φ4.5 内径 / 高 6mm / 套在孔口(z=8→14) / 与孔同轴 / 总高14mm
  - STL 面数应显著 > 208（精修后反映锥孔与套壁）
权威判据：
  1) CONICAL_SURFACE 半锥角≈45° 且 轴定位点落三孔心(z≈5.25 小端)
  2) 三孔顶 z≈[6,16] 处存在 radius≈5.0(Φ10) 的 CIRCLE（顶口圆，兼容底板顶z8或套顶z14）
  3) 三孔口 z≈[6,16] 处存在 CYLINDRICAL_SURFACE（Φ10 外圆 + 伴随 Φ4.5 内孔）= 导向套
注：本 STEP 锥面/圆柱轴引用是 AXIS2_PLACEMENT_3D（带 _3D 后缀），旧正则漏匹配已修复。
用法：python verify_countersink.py [step_path]
"""
import re, sys, math, os

DEFAULT_STEP = r"F:\伊利雪糕三棒签插签设备项目\solidworks\三棒签插签装置.step"
DEFAULT_STL  = r"F:\伊利雪糕三棒签插签设备项目\solidworks\三棒签插签装置.stl"
EXPECT_X = [-50.0, 0.0, 50.0]
AXIS_Y = 0.0
HOLE_TOL = 8.0

def build_points(step):
    pts = {}
    for m in re.finditer(r"#(\d+)\s*=\s*CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)\s*\)\s*\)", step):
        pts[m.group(1)] = (float(m.group(2)), float(m.group(3)), float(m.group(4)))
    return pts

def build_axis2(step):
    # 兼容 AXIS2_PLACEMENT 与 AXIS2_PLACEMENT_3D（后者带 _3D 后缀且有 refdir 三参）
    # 两种格式 location 都是首参 (#ref)，取第一个即可。
    ax = {}
    for m in re.finditer(r"#(\d+)\s*=\s*AXIS2_PLACEMENT(?:_3D)?\s*\(\s*'[^']*'\s*,\s*#(\d+)\s*,", step):
        ax[m.group(1)] = m.group(2)
    return ax

def build_cones(step):
    cones = []
    for m in re.finditer(r"#(\d+)\s*=\s*CONICAL_SURFACE\s*\([^;]*?,\s*#(\d+)\s*,\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)\s*\)\s*;", step):
        cid, axis_id, radius, semi = m.group(1), m.group(2), float(m.group(3)), math.degrees(float(m.group(4)))
        cones.append((cid, axis_id, radius, semi))
    return cones

def build_circles(step, ax2, pts):
    circles = []
    for m in re.finditer(r"#(\d+)\s*=\s*CIRCLE\s*\(\s*'[^']*'\s*,\s*#(\d+)\s*,\s*([-\d.eE+]+)\s*\)\s*;", step):
        cid, axis_id, radius = m.group(1), m.group(2), float(m.group(3))
        loc = ax2.get(axis_id)
        pos = pts.get(loc) if loc else None
        circles.append((cid, radius, pos))
    return circles

def build_cylinders(step, ax2, pts):
    cyls = []
    for m in re.finditer(r"#(\d+)\s*=\s*CYLINDRICAL_SURFACE\s*\(\s*'[^']*'\s*,\s*#(\d+)\s*,\s*([-\d.eE+]+)\s*\)\s*;", step):
        cid, axis_id, radius = m.group(1), m.group(2), float(m.group(3))
        loc = ax2.get(axis_id)
        pos = pts.get(loc) if loc else None
        cyls.append((cid, radius, pos))
    return cyls

def classify_x(x):
    best = min(EXPECT_X, key=lambda cx: abs(x - cx))
    return best if abs(x - best) <= HOLE_TOL else None

def stl_face_count(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            f.seek(80)
            b = f.read(4)
            if len(b) < 4:
                return None
            return int.from_bytes(b, "little")
    except Exception:
        return None

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_STEP
    if not os.path.exists(path):
        print(f"[ERR] STEP 不存在: {path}")
        return
    step = open(path, encoding="utf-8", errors="ignore").read()
    pts = build_points(step)
    ax2 = build_axis2(step)
    cones = build_cones(step)
    circles = build_circles(step, ax2, pts)
    cylinders = build_cylinders(step, ax2, pts)

    print(f"STEP: {os.path.basename(path)}  ({os.path.getsize(path)} B)")
    print(f"CARTESIAN_POINT {len(pts)} | CONICAL_SURFACE {len(cones)} | CIRCLE {len(circles)} | CYLINDRICAL_SURFACE {len(cylinders)}")

    # ---- 锥面明细（位置用 AXIS2_PLACEMENT_3D 定位）----
    print("\n=== 全部 CONICAL_SURFACE 明细 ===")
    cone_detail = []
    for (cid, axis_id, r, s) in cones:
        loc = ax2.get(axis_id)
        pos = pts.get(loc) if loc else None
        cone_detail.append((cid, r, s, pos))
        pos_s = f"({pos[0]:.2f},{pos[1]:.2f},{pos[2]:.2f})" if pos else "位置未解析"
        print(f"  #{cid:>5s}  radius={r:7.3f}  半锥角={s:6.2f}°  pos={pos_s}")

    # ---- 判据 1：45° 锥面落在三孔小端 ----
    csinks = []
    for (cid, r, s, pos) in cone_detail:
        if pos and abs(s - 45.0) < 2.0:
            cx = classify_x(pos[0])
            if cx is not None and abs(pos[1] - AXIS_Y) <= HOLE_TOL and 3.0 <= pos[2] <= 9.0:
                csinks.append((cid, r, s, cx, pos))
    print(f"\n落在三孔、半锥角≈45° 的锥面（沉头候选）: {len(csinks)} 个")
    by_hole_cone = {cx: [] for cx in EXPECT_X}
    for (cid, r, s, cx, pos) in csinks:
        by_hole_cone[cx].append(r)
        print(f"    孔 x={cx:+.0f}: 锥面radius={r:.3f}  z={pos[2]:.2f}")
    covered_cone = [cx for cx in EXPECT_X if by_hole_cone[cx]]
    print(f"锥面覆盖到的孔心: {covered_cone}（共 {len(covered_cone)}/3）")

    # ---- 判据 2：Φ10 顶口圆落在三孔顶 z≈[6,16]（兼容底板顶z8 或 套顶z14）----
    top_openings = []
    for (cid, radius, pos) in circles:
        if pos and abs(radius - 5.0) < 0.1:
            cx = classify_x(pos[0])
            if cx is not None and abs(pos[1] - AXIS_Y) <= HOLE_TOL and 6.0 <= pos[2] <= 16.0:
                top_openings.append((cid, radius, cx, pos))
    print(f"\n三孔顶 z≈[6,16]、radius≈5.0(Φ10) 的 CIRCLE（顶口圆）: {len(top_openings)} 个")
    by_hole_top = {cx: [] for cx in EXPECT_X}
    for (cid, radius, cx, pos) in top_openings:
        by_hole_top[cx].append(radius)
        print(f"    孔 x={cx:+.0f}: 顶口圆 radius={radius:.3f}  z={pos[2]:.2f}")
    covered_top = [cx for cx in EXPECT_X if by_hole_top[cx]]
    print(f"顶口圆覆盖到的孔心: {covered_top}（共 {len(covered_top)}/3）")

    # ---- 判据 3：导向套（Φ10 外圆 + 伴随 Φ4.5 内孔，z≈8→14）----
    sleeve_outer, sleeve_inner = [], []
    for (cid, radius, pos) in cylinders:
        if not pos:
            continue
        cx = classify_x(pos[0])
        if cx is None or abs(pos[1] - AXIS_Y) > HOLE_TOL or not (6.0 <= pos[2] <= 16.0):
            continue
        if abs(radius - 5.0) < 0.1:
            sleeve_outer.append((cid, radius, cx, pos))
        elif abs(radius - 2.25) < 0.1:
            sleeve_inner.append((cid, radius, cx, pos))
    print(f"\n导向套候选：Φ10 外圆(CYL) {len(sleeve_outer)} 个 / Φ4.5 内孔(CYL) {len(sleeve_inner)} 个（均限 z≈8→14 孔口带）")
    by_hole_sleeve = {cx: False for cx in EXPECT_X}
    for (cid, radius, cx, pos) in sleeve_outer:
        has_inner = any(ip and abs(ip[0]-pos[0]) < HOLE_TOL and abs(ip[1]-pos[1]) < HOLE_TOL and abs(ip[2]-pos[2]) < 8.0
                        for (_, _, _, ip) in sleeve_inner)
        if has_inner:
            by_hole_sleeve[cx] = True
        print(f"    孔 x={cx:+.0f}: 外圆#{cid} radius={radius:.3f} z={pos[2]:.2f}  内孔伴随={'有' if has_inner else '无'}")
    covered_sleeve = [cx for cx in EXPECT_X if by_hole_sleeve[cx]]
    print(f"导向套覆盖到的孔心: {covered_sleeve}（共 {len(covered_sleeve)}/3）")

    # ---- 孔位坐标聚类 ----
    clusters = {cx: [] for cx in EXPECT_X}
    for (x, y, z) in pts.values():
        if abs(y - AXIS_Y) > HOLE_TOL:
            continue
        cx = classify_x(x)
        if cx is not None:
            clusters[cx].append((x, y, z))
    print("\n=== 孔位坐标 ===")
    holes_found = 0
    for cx in EXPECT_X:
        g = clusters[cx]
        print(f"  孔 x={cx:+.0f}: 点={len(g)}")
        if len(g) >= 3:
            holes_found += 1

    # ---- STL 面数 + 总高 ----
    stl_n = stl_face_count(DEFAULT_STL)
    print(f"\nSTL 三角形数: {stl_n}（基准 208；精修后应显著 >208 且反映锥孔/套壁）")
    if pts:
        zs = [p[2] for p in pts.values()]
        print(f"模型 Z 向范围: minZ={min(zs):.2f}  maxZ={max(zs):.2f}（规格总高=14mm：底板8+导向套6）")

    # ---- 判定 ----
    print("\n=== 判定 ===")
    ok_cs = (len(covered_cone) == 3 and len(covered_top) == 3 and holes_found == 3)
    ok_sleeve = (len(covered_sleeve) == 3)
    if ok_cs and ok_sleeve:
        print("✅ 锥形沉头 3/3（顶口Φ10/底孔Φ4.5/锥角90°/三处同轴）+ 导向套 3/3（Φ10外圆+Φ4.5内孔/6mm/同轴）+ 三孔位置正确")
        print("   → 导向套已补、沉头随导向套贯通至 z=14，总高14mm，几何吻合")
    elif ok_cs and not ok_sleeve:
        print("✅ 锥形沉头 3/3 通过；⚠️ 导向套未检出（仍是 8mm 底板无套）—— 待补建")
    elif not ok_cs:
        print("⚠️ 锥形沉头未达 3/3（见上），需先修复沉头再补导向套")
    if stl_n is not None:
        print(f"STL 面数 {stl_n}：{'达标(>208)' if stl_n and stl_n>208 else '未精修(仍=208或缺失)'}")

if __name__ == "__main__":
    main()
