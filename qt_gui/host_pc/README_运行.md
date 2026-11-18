# 上位机（S2）三步运行

环境：D:\ANACONDA\python.exe（已装 pyserial 3.5；PySide6 6.12.0 装了但 QtCore 损坏，见下）

1. 接上设备的 CH340/CP2102 USB 口，确认设备管理器里有虚拟串口。
2. `cd F:\伊利雪糕三棒签插签设备项目\qt_gui\host_pc`
3. **日常启动（推荐，自动选后端）**：`D:\ANACONDA\python.exe start.py`
   - Qt 可用 → 走 `main.py`（Qt 版）；Qt 不可用 → 自动落 `main_tk.py`（tkinter 回退版，零依赖）。
   - 两版共用 protocol.py / push.py，功能一致：自动连串口、启动/停止/复位/参数下装、
     九位 IO 指示灯、事件日志、SEQ 丢帧统计、>500ms 通信中断判定、SQLite 推送。

   直接指定后端也可以：
   `D:\ANACONDA\python.exe main_tk.py`             tkinter 正常启动
   `D:\ANACONDA\python.exe main_tk.py --simulate`  无硬件演示：回放协议示例帧 + 合成工作循环
   `D:\ANACONDA\python.exe main_tk.py --selftest`  构建界面+注入示例帧+截屏 host_tk_selftest.png 后退出

## 已知阻塞（本机环境，非代码缺陷）——已有 tkinter 回退，不阻塞使用
PySide6 6.12.0 的 QtCore 在本机 import 失败：`DLL load failed while importing QtCore`。
已排除：不是插件路径问题（os.add_dll_directory 加 PySide6 目录与 plugins 后仍失败）；
shiboken6 与 PySide6 包本身可导入。多为缺 MSVC 运行时或该 wheel 安装损坏。
修法（择一，需用户确认后再动本机环境，不修也不影响使用）：
  A. 安装 Microsoft Visual C++ 2015-2022 Redistributable (x64) 后重试；
  B. pip install --force-reinstall PySide6；
  C. 换用 PyQt5（pip install PyQt5）。

## 已验证部分
- protocol.py：`python test_protocol.py` -> 35 项断言全通过（R1 四条示例帧逐字段还原、
  逐字节/多段切分、噪声重同步、双 AA、非法 LEN、篡改 SUM、方向位、哨兵、负温、100 组往返）。
- push.py：`python push.py` -> 写出 stickinsert.db，state/state_history/events/meta 四表均有数据。
- main_tk.py：`python main_tk.py --selftest` -> 界面构建成功（780x620）、识别到 2 个串口、
  自动连 COM1、注入协议示例状态帧渲染正确（RUNNING/1234 次/620ms/25.1℃/101.3kPa/IO 0x0089，
  YV1/SQ1/LED_RUN 亮与其逐位一致），截图 host_tk_selftest.png；已做进程内 DPI-aware 修正。
- start.py：Qt 失败自动落 tkinter 的完整链路实测通过。
