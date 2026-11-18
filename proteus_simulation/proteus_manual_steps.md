# Proteus 仿真 · 本机手动收口指南（2 分钟）

> 背景：盲脚本在 Proteus 米色画布上无法稳定检测引脚几何，放件/连线/填 hex 三步必须肉眼做。
> 本指南给本机在 ISIS 里完成这三步，之后用脚本 `--phase2` 自动跑仿真+录屏。
> 所有事实来自多轮实测 实测，已纠正 v10「P1.0 在底部三行」的错误。

## 0. 打开工程
- 工程：`F:\伊利雪糕三棒签插签设备项目\proteus_simulation\StickInsert_ref_copy.pdsprj`
  （14,121 B 干净半建成：已含 AT89C52 + D1(LED-RED) + DEVICES 列表 AT89C52/BUTTON/LED-RED/RES）
- 若弹出「是否自动恢复保存的工程」→ 点 **否**（避免恢复旧会话幽灵器件）。
- 或用脚本 phase1 代开（会自动点否+扫模态+整图+保存+开 U1 属性框留你填）：
  `D:\ANACONDA\python.exe proteus_auto_build.py`

## 1. 三条关键事实（多轮实测 实测，已纠正 v10）
- **AT89C52 左列引脚顺序（自上而下）**：19 XTAL1 → 18 XTAL2 → 0 RST → 29 PSEN → 30 ALE → 28 EA → **1 P1.0（第 7 行）→ 2 P1.1（第 8 行）→ 3 P1.2（第 9 行）**。
  ⚠️ v10 说的「底部三行」是错的；P1.0 是左列第 7 行，按这个放件才不会全偏。
- **DEVICES 停靠列表坐标（最大化时屏幕参考）**：LED-RED ≈ (60,310)，BUTTON (60,292)，RES (60,328)。
  面板用窗口相对偏移较稳；画布内容需肉眼标定。
- **视图档位**：view-all（F8 / 0x014B）后放大 2 级（F6×2 / 0x0149×2）≈ 行距 55px（可点）；缩小 2 级 ≈ 7px（不可点）。参考工程里已有 D1 一颗 LED-RED。

## 2. 手动步骤
1. **视图**：按 F8 让整片入镜 → 再按 F6 放大 2 级，使引脚行距 ≈ 55px 可点。
2. **放 LED**：左侧 DEVICES 面板点 **LED-RED**，再点 U1 左侧 P1.0 / P1.1 / P1.2 附近空白放 3 颗（已有 D1 可复用或再加 3 颗）。
   每放一颗若弹 **「Replace or place new one?」** → 点 **New**。
3. **连线**（先点左侧线/连线工具进入连线模式，再点两端）：
   - 每颗 LED **阳极 → 对应 P1.0 / P1.1 / P1.2**；
   - 每颗 LED **阴极 → 经 RES（从 DEVICES 放 RES）→ GND**。
4. **填 hex**：双击 **U1** 打开属性框 → Program File 选 `control.hex`（**4810B，MD5 `17ab2aeaa907c0504321c7deb6275852`**，已含 UART 固件；旧 1415B 留作 `control.hex.bak_1415B` 回滚）→ Clock Frequency 填 **11.0592 MHz** → OK。
5. **运行**：点开始仿真（Play / 0x0233）。预期：LED3@0ms → LED2@125ms → LED1@250ms 顺序点亮；≥650ms **RUN 绿灯（P3.2）** 亮；急停断开全灭+**ALARM 红灯（P3.3）** 告警。
   - **可选 UART 验证**：DEVICES 放 **VIRTUAL TERMINAL**，其 RXD 接 U1 **P3.1（TXD）**，设 9600/8N1；运行后终端逐字节收状态帧（帧头 `0xD7`、14B、约 1Hz），可作 PPT/视频"串口数据"素材。
6. **录屏**：`D:\ANACONDA\python.exe proteus_auto_build.py --phase2`（自动 CMD_RUN + ffmpeg 10fps 录屏 + 保存）；或本机录屏软件。
7. **保存**：Ctrl+S。

## 3. 回传设计助手（收尾用）
- `proteus_simulation\auto_out\` 全部截图（01_ready.png / 04_running.png / sim_record.mp4 或连拍帧）
- 最终 `.pdsprj`
- 时序判读结论（LED3@0→LED2@125→LED1@250；≥650ms 绿灯；急停断开全灭）

设计助手据回传素材嵌 PPT 三栏 + 出三环节验收报告 + 剪演示视频。
