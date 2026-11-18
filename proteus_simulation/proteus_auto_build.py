# -*- coding: utf-8 -*-
"""
三棒签插签设备 · Proteus 构建辅助脚本（诚实版 / v1.1）
=========================================================
实测结论（多轮实测v11 + v2 多轮验证）：Proteus 画布底色为米色、引脚几何无法靠盲脚本稳定检测，
"自动放件 + 自动连线 + 自动填 hex" 在盲坐标下不可靠，且乱点会脏工程。本脚本只做**命令全部已验证**的部分：
    启动工程 -> 点启动恢复框「否」-> 扫模态框 -> 整图 -> 保存 -> 打开 U1 属性框（留开等手填）
放置 3×LED、连线共地、填 hex + 频率 这三步**必须本机肉眼在 ISIS 完成**（约 2 分钟，见 proteus_manual_steps.md）。
完成后另跑 `--phase2`：自动 CMD_RUN 跑仿真 + ffmpeg 录屏 + 保存。

运行：
    1) 校准（仅打印窗口矩形+关键点坐标，不改动工程）：
       D:\\ANACONDA\\python.exe proteus_auto_build.py --calibrate
    2) phase1（启动+预处理，属性框留开等手填）：
       D:\\ANACONDA\\python.exe proteus_auto_build.py
    3) 本机在 ISIS 手放件/连线/填 hex 后，phase2 跑仿真并录屏：
       D:\\ANACONDA\\python.exe proteus_auto_build.py --phase2

安全：启动前默认 taskkill 残留 PDS 实例（避免"恢复上次会话开错设计"）；加 --no-kill 可跳过。
"""

import os
import sys
import time
import subprocess
import logging

try:
    import win32gui
    import win32con
    import win32api
    from PIL import ImageGrab
except ImportError as e:
    sys.stderr.write("缺少依赖 pywin32 / Pillow，请先安装后再运行。\n")
    raise

# ============================================================
# CONFIG —— 所有已验证常量集中放这里，改机只动这一块
# ============================================================
PROTEUS_EXE = r"C:\Program Files (x86)\Labcenter Electronics\Proteus 8 Professional\BIN\PDS.EXE"
PROJECT      = r"F:\伊利雪糕三棒签插签设备项目\proteus_simulation\StickInsert_ref_copy.pdsprj"
HEX_SRC      = r"F:\伊利雪糕三棒签插签设备项目\proteus_simulation\control.hex"
HEX_MD5      = "add4cedc80a26f4666e09a4603a884c9"   # 1415B 真版，严禁旧 1055/1366B
FREQ_MHZ     = "11.0592"

# WM_COMMAND 命令 ID（来自多轮实测/v10 实测，直接复用，禁止重取证）
CMD_SAVE      = 0x0204   # 保存
CMD_VIEW_ALL  = 0x014B   # 整张图纸 F8
CMD_ZOOM_IN   = 0x0149   # 放大 F6（已验证可用，但本脚本不依赖其坐标）
CMD_RUN       = 0x0233   # 开始仿真

# —— 相对主窗口左上角的偏移（基准：窗口 79,19）——
# 说明：仅 DEVICES 列表 / 窗口框类偏移较稳；画布内容（引脚、放置点）会因缩放/平移失效，
# 故本脚本不盲点画布，放置/连线留本机肉眼做。以下偏移仅作 --calibrate 参考显示。
# DEVICES 列表项（左侧器件库）
OFF_BTN_BUTTON = (225 - 79, 356 - 19)   # BUTTON
OFF_BTN_LEDRED = (225 - 79, 372 - 19)   # LED-RED
OFF_BTN_RES    = (225 - 79, 388 - 19)   # RES
# U1 区域（参考 v10）
OFF_U1_BODY_L, OFF_U1_BODY_T, OFF_U1_BODY_R, OFF_U1_BODY_B = (673-79, 500-19, 855-79, 860-19)
OFF_U1_TEXT   = (700 - 79, 528 - 19)    # "U1" 位号文字（双击此处开属性）
# MCU 引脚末端（0x014B 整图后，相对窗口偏移；仅供校准参考，不作为盲点依据）
OFF_P10 = (827-79, 819-19)
OFF_P11 = (827-79, 835-19)
OFF_P12 = (827-79, 851-19)
# 放置 3 个 LED 的画布落点（仅供参考显示，实际由本机肉眼放置）
OFF_PLACE_LED = [(900-79, 819-19), (900-79, 835-19), (900-79, 851-19)]

# 录屏：若本机有 ffmpeg 则在 PATH 中自动启用；否则退化为"截图连拍"
FFMPEG = "ffmpeg"
RECORD_SECONDS = 4

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proteus_auto_build.log")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto_out")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("proteus_auto")


# ============================================================
# 窗口 / 控件 工具
# ============================================================
def find_proteus_window():
    """按标题包含 'Proteus' 或工程基名定位主窗口。"""
    target_base = os.path.splitext(os.path.basename(PROJECT))[0].lower()
    found = []
    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        cls = win32gui.GetClassName(hwnd)
        if ("proteus" in title.lower()) or (target_base in title.lower()):
            found.append((hwnd, title, cls))
    win32gui.EnumWindows(cb, None)
    # 优先取标题含工程名或 Proteus 且非对话框的顶层窗口
    for hwnd, title, cls in found:
        if cls != "#32770":
            return hwnd, title
    if found:
        return found[0][0], found[0][1]
    return None, ""


def enum_dialogs():
    """枚举同桌面可见 #32770 模态框，返回 [(hwnd, title)]。"""
    dlg = []
    def cb(hwnd, _):
        if win32gui.GetClassName(hwnd) == "#32770" and win32gui.IsWindowVisible(hwnd):
            dlg.append((hwnd, win32gui.GetWindowText(hwnd)))
    win32gui.EnumWindows(cb, None)
    return dlg


def click_button_by_text(dlg_hwnd, text):
    """在模态框内找文字匹配 text 的按钮，真实鼠标点击其中心。返回是否点到。"""
    hit = []
    def cb(hwnd, _):
        if win32gui.GetClassName(hwnd) in ("Button", "TButton"):
            t = win32gui.GetWindowText(hwnd)
            if text in t:
                hit.append(hwnd)
    win32gui.EnumChildWindows(dlg_hwnd, cb, None)
    if not hit:
        return False
    rc = win32gui.GetWindowRect(hit[0])
    cx, cy = (rc[0] + rc[2]) // 2, (rc[1] + rc[3]) // 2
    real_click(cx, cy)
    return True


def esc_modals():
    """清掉所有可见 #32770（不含主窗口），发 ESC 一发即关。返回清掉的数量。"""
    n = 0
    for hwnd, title in enum_dialogs():
        log.info("发现模态框: %r -> 发 ESC", title)
        win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_ESCAPE, 0)
        win32api.PostMessage(hwnd, win32con.WM_KEYUP, win32con.VK_ESCAPE, 0)
        time.sleep(0.3)
        n += 1
    return n


# ============================================================
# 真实输入（关键：用真实键鼠事件，绝不用 WM_COMMAND 发回车）
# ============================================================
def real_click(x, y, double=False):
    win32api.SetCursorPos((x, y))
    time.sleep(0.05)
    if double:
        for _ in range(2):
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(0.08)
    else:
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.12)


def real_key(vk):
    """真实键盘事件（用于 VK_RETURN 开属性框，不是 WM_COMMAND）。"""
    win32api.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.1)


def post_cmd(hwnd, cmd_id):
    """发 Proteus 菜单命令（这些本就是命令 ID，合法用法）。"""
    win32api.PostMessage(hwnd, win32con.WM_COMMAND, cmd_id, 0)
    time.sleep(0.3)


def to_screen(hwnd, ox, oy):
    rc = win32gui.GetWindowRect(hwnd)
    return rc[0] + ox, rc[1] + oy


def screenshot(name):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    img = ImageGrab.grab()
    img.save(path)
    log.info("截图已存: %s (%dx%d)", path, img.width, img.height)
    return path


def record_screen():
    """优先 ffmpeg 录屏；失败退化为每秒 1 帧连拍。"""
    os.makedirs(OUT_DIR, exist_ok=True)
    try:
        subprocess.run([FFMPEG, "-y", "-f", "gdigrab", "-i", "desktop",
                        "-t", str(RECORD_SECONDS), "-r", "10",
                        os.path.join(OUT_DIR, "sim_record.mp4")],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log.info("ffmpeg 录屏完成: sim_record.mp4")
    except Exception:
        log.warning("ffmpeg 不可用，退化为截图连拍")
        for i in range(RECORD_SECONDS):
            screenshot("sim_frame_%d.png" % i)
            time.sleep(1)


# ============================================================
# U1 属性框（真实事件四步兜底链；盲填坐标不可靠，故只负责"打开"）
# ============================================================
def open_u1_properties(hwnd):
    """依次尝试四种真实方式打开 U1 属性框，成功返回 True。"""
    # 1) 双击 "U1" 文字
    x, y = to_screen(hwnd, *OFF_U1_TEXT)
    real_click(x, y, double=True)
    time.sleep(0.5)
    if enum_dialogs():
        return True
    # 2) 单击选中 U1 本体 -> 真实 VK_RETURN
    x, y = to_screen(hwnd, (OFF_U1_BODY_L + OFF_U1_BODY_R) // 2, (OFF_U1_BODY_T + OFF_U1_BODY_B) // 2)
    real_click(x, y)
    time.sleep(0.2)
    real_key(win32con.VK_RETURN)
    time.sleep(0.5)
    if enum_dialogs():
        return True
    # 3) 右键 -> Properties（真实点击菜单首项匹配）
    real_click(x, y, double=False)
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
    time.sleep(0.4)
    # 菜单是浮动窗口，尝试 ESC 收掉避免卡住
    esc_modals()
    # 4) 工具栏 Edit（尽力，坐标因版本差异较大，标 WARNING）
    log.warning("U1 属性框前三种方式未弹出，请本机手动开属性填 hex（工程已保存）")
    return False


def fill_u1_hex(hwnd):
    """打开 U1 属性框并**保留打开**，等本机手动填 hex + 频率（盲填坐标不可靠，不再自动取消）。"""
    ok = open_u1_properties(hwnd)
    if not ok:
        log.warning("U1 属性框未能自动打开，请本机双击 U1 手动开属性填 hex")
        return False
    log.info("U1 属性框已打开 —— 请手动填：Program File=control.hex(1415B, MD5 %s)，Clock=%s MHz，然后点 OK",
             HEX_MD5, FREQ_MHZ)
    return True


# ============================================================
# 校准 / 启动前清场 / phase2
# ============================================================
def calibrate(hwnd):
    rc = win32gui.GetWindowRect(hwnd)
    log.info("主窗口矩形: left=%d top=%d right=%d bottom=%d (w=%d h=%d)",
             rc[0], rc[1], rc[2], rc[3], rc[2]-rc[0], rc[3]-rc[1])
    checks = {
        "LED-RED列表": OFF_BTN_LEDRED,
        "U1文字": OFF_U1_TEXT,
        "U1中心": ((OFF_U1_BODY_L+OFF_U1_BODY_R)//2, (OFF_U1_BODY_T+OFF_U1_BODY_B)//2),
        "P1.0末端(参考)": OFF_P10,
        "放置点1(参考)": OFF_PLACE_LED[0],
    }
    for k, (ox, oy) in checks.items():
        log.info("  %s -> 屏幕 (%d, %d)", k, rc[0]+ox, rc[1]+oy)
    log.info("校准完成：DEVICES 列表/窗口框类偏移较稳；画布内容偏移仅参考，放置/连线请本机肉眼做。")


def kill_existing_proteus():
    """启动前清掉残留 PDS 实例，避免'恢复上次会话开错设计'（多轮实测/v11 实证陷阱）。
    本机另有在用 Proteus 时加 --no-kill 跳过。"""
    try:
        r = subprocess.run(["taskkill", "/IM", "PDS.EXE", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode == 0:
            log.info("已终止残留 PDS 实例（--no-kill 可跳过）")
            time.sleep(1)
    except Exception:
        pass


def run_phase2(hwnd):
    """phase2：仿真运行 + 录屏 + 保存（CMD_RUN 等命令全部已验证，不碰画布几何）。"""
    post_cmd(hwnd, CMD_RUN)
    time.sleep(1.0)
    screenshot("04_running.png")
    record_screen()
    post_cmd(hwnd, CMD_SAVE)
    log.info("phase2 完成：仿真已运行并录屏，工程已保存")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # phase2：在已开工程上跑仿真并录屏（手动放件/连线/填 hex 之后用）
    if "--phase2" in sys.argv:
        hwnd, title = find_proteus_window()
        if not hwnd:
            log.error("phase2 找不到 Proteus 主窗口，请先 phase1 或本机手动开工程")
            return
        log.info("主窗口: %r", title)
        run_phase2(hwnd)
        return

    log.info("=== phase1：启动 Proteus 自动化 ===")
    if "--no-kill" not in sys.argv:
        kill_existing_proteus()
    # 1) 启动工程
    try:
        subprocess.Popen([PROTEUS_EXE, PROJECT])
    except Exception as e:
        log.error("启动 Proteus 失败: %s", e)
        return
    time.sleep(6)  # 等主窗/恢复框出现

    hwnd, title = find_proteus_window()
    if not hwnd:
        log.error("找不到 Proteus 主窗口，退出")
        return
    log.info("主窗口: %r", title)

    if "--calibrate" in sys.argv:
        calibrate(hwnd)
        return

    # 2) 启动恢复框：点「否」
    handled = False
    for dhwnd, dtitle in enum_dialogs():
        if "恢复" in dtitle or "recover" in dtitle.lower() or "保存的工程" in dtitle:
            log.info("发现启动恢复框: %r -> 点「否」", dtitle)
            if not click_button_by_text(dhwnd, "否"):
                click_button_by_text(dhwnd, "No")
            handled = True
            time.sleep(1)
    if not handled:
        log.info("未发现启动恢复框（可能已关），继续")
    esc_modals()

    # 3) 整图，留干净基线截图 + 保存
    post_cmd(hwnd, CMD_VIEW_ALL)
    time.sleep(0.5)
    post_cmd(hwnd, CMD_SAVE)
    screenshot("01_ready.png")

    # 4) 打开 U1 属性框并保留打开，等本机手填 hex（不再自动取消）
    fill_u1_hex(hwnd)

    # 5) 放置器件 / 连线 需肉眼，脚本不盲点（避免脏工程）。手动步骤见 proteus_manual_steps.md
    log.info("===== 以下需本机肉眼在 ISIS 完成（约 2 分钟）=====")
    log.info("  a) DEVICES 停靠面板点 LED-RED×3，放到 U1 左侧 P1.0/1.1/1.2 旁（左列第 7/8/9 行）")
    log.info("  b) 每颗 LED 阴极经 RES 连到 GND；P1.0/1/1.2 各接一颗 LED 阳极")
    log.info("  c) 在已打开的 U1 属性框填 1415B hex(MD5 %s) + %s MHz，点 OK", HEX_MD5, FREQ_MHZ)
    log.info("  d) 完成后另开终端跑：python proteus_auto_build.py --phase2 （自动跑仿真+录屏+保存）")
    log.info("=== phase1 结束（工程已保存，U1 属性框留开等手填）===")


if __name__ == "__main__":
    main()
