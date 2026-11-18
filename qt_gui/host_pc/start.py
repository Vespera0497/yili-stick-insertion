# -*- coding: utf-8 -*-
"""
三棒签插签设备 · 上位机自动启动器
优先 PySide6（Qt 版 main.py，界面更精致）；QtCore 加载失败时自动落到
Tkinter 回退版 main_tk.py（Python 内置、零依赖）。两种后端共用同一套
protocol.py / push.py，界面功能一致，SQLite 推送口径不变。

用法：python start.py [同 main.py 的参数，如 --simulate / --selftest]
"""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    try:
        from PySide6 import QtWidgets  # noqa: F401  探测 Qt 后端可用性
        print("[start] PySide6 可用 -> Qt 版 main.py")
        import main
        return main.main()
    except Exception as e:
        print("[start] PySide6 不可用（%s: %s）-> Tkinter 回退版 main_tk.py" % (
            type(e).__name__, str(e)[:80]))
        import main_tk
        return main_tk.main()


if __name__ == "__main__":
    sys.exit(main())
