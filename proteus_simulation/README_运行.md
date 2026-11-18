# 三棒签插签设备 · 三步运行卡（README_运行）

本机实测汇总，命令与 ID 全部已验证可用，勿再探测。路径基准 `F:\伊利雪糕三棒签插签设备项目\`。
Python = `D:\ANACONDA\python.exe`（pywin32 / Pillow 已装，ffmpeg 在 `D:\ANACONDA\Library\bin`）。

## 1. Keil（出固件）

1. 打开 `keil_firmware\control.uvprojx`（标题应含「三棒签插签设备」，别开旧副本）。
2. 按 **F7** 重建 → `keil_firmware\control.hex`，**4810 字节 / MD5 `17ab2aeaa907c0504321c7deb6275852`**（已含 UART 固件）。旧无-UART 版 1415B 保留为 `keil_firmware\control.hex.bak_1415B`（MD5 `add4cedc80a26f4666e09a4603a884c9`），仅供回滚。
3. 把这个 hex 喂给 Proteus（见 §2 第 5 步）。

> **Ctrl+F5 调试器本机用不了**：µVision 缺 Atmel/AT89C52 器件库，会弹
> `Error: Device not found - Device:'AT89C52' Vendor:'Atmel'`。端口/灯态验证一律改走 Proteus。
> Keil 本身只编译，**不会显示灯亮灭**。

## 2. Proteus（看运行 —— 灯亮灭/气缸/UART 都在这）

前置：`proteus_simulation\StickInsert_ref_copy.pdsprj`（14,125 B，U1 已确认 **AT89C52**）。

1. 一键起场（自动杀残留实例、点恢复框「否」、清模态、F8 整图、保存、出基线截图）：
   `D:\ANACONDA\python.exe proteus_simulation\proteus_auto_build.py`
2. 人工放件：DEVICES 停靠面板点 **LED-RED**，在 U1 **左列第 7/8/9 行**（= P1.0/P1.1/P1.2）旁点 3 下，每放一颗重新点一次列表；弹「Replace or place new one?」选 **New**。
3. 连线：LED 阳极 → P1.0/1.1/1.2；阴极 → 各串一个 RES → GND。
4. 双击 **U1**（双击位号文字或选中后按键盘回车；点本体填充区无效）→ `Program File` 选 `proteus_simulation\control.hex`（4810 B，已含 UART 固件；旧 1415B 留作回滚：`proteus_simulation\control.hex.bak_1415B` 与 `keil_firmware\control.hex.bak_1415B`）→ `Clock Frequency` = **11.0592MHz** → OK。
5. 一键跑仿真 + 截图 + 10fps 录屏 + 保存（纯命令 ID，不碰画布，免疫 DPI 问题）：
   `D:\ANACONDA\python.exe proteus_simulation\proteus_auto_build.py --phase2`
   产物在 `proteus_simulation\auto_out\`：`04_running.png` + `sim_record.mp4`。
6. 预期时序：**LED3@0ms → LED2@125ms → LED1@250ms**；≥650ms 绿灯同步；急停断开 → 全灭 + 告警。
7. **UART 串口验证（新固件）**：DEVICES 放一个 **VIRTUAL TERMINAL**，其 RXD 引脚 → 接 U1 的 **P3.1（TXD）**，波特率设 **9600 / 8N1**。开始仿真后，终端会按协议逐字节收到状态帧（帧头 `0xD7` 起、14 字节、约 1Hz），可作 PPT/视频的“串口数据”素材。
   - ⚠️ 新固件把 **RUN / ALARM 指示灯挪到了 P3.2 / P3.3**（原 P3.0/P3.1 让给 UART）。若想在看板里看到这两个灯，需把 LED 阳极从原 P3.0/P3.1 改接到 P3.2/P3.3；三棒签 LED 仍在 P1.0/1.1/1.2 不变。

已验命令 ID：保存 `0x0204`｜整图 F8 `0x014B`｜放大 F6 `0x0149`｜缩小 F7 `0x014A`｜光标居中 F5 `0x0148`（放大态下会把目标推出视口，别用它平移）｜开始仿真 `0x0233`。

## 3. Altium Designer（8051 原理图重画）

1. **先确认只有一个 X2.EXE 实例**（双实例同开一个 PrjPcb 会互相覆写）。
2. 命令行带参加载：`"F:\Program Files\Altium\AD21\X2.EXE" "ad_schematic\StickInsert_Control.PrjPcb" "ad_schematic\GenerateStickInsert7.PrjScr"`
3. 点原理图页标签使其激活 → `File → Run Script` → 选 **Build8051** → OK → 弹窗显示放置计数。
4. 保存（Ctrl+S）。备份已在位：`StickInsert_Control.SchDoc.bak_20261030`（MD5 `73cbe4a146f8f0e4e807d5e3784ab320`）。
5. **Validate 必须人手点**：`Project → Validate PCB Project`，然后看 Messages 面板截图。
   本机实测：Validate/Compile **无法**用命令词或 PostMessage 触发（全库扫不到注册命令串）。

> v7 脚本要点：所有坐标经 `M(mil)=mil*10000` 换算（v6 用裸整数导致整图塌到原点）；
> 25 元件 / 123 引脚 / U1 编号 1..40 完整；静态审计非 NC 单端点网络 = 0。
> 已知残留风险：本机 `ISch_Wire` 不落盘（`RECORD=6` 恒 0），连通靠"标号坐在引脚尖端"表达，
> Validate 可能仍报 Floating Net Label —— 需真跑一次才知道，不预判结论。
> 纸张尺寸不在 Design 菜单，在 Properties → Page Options → Sheet Size（A4 = 11500×7600 mil）。

## 4. 上位机 / 监控看板 / SolidWorks 装配 —— **S1 已完成，S2/S3 待做**

- **S1 固件 UART 扩展已完成**：`keil_firmware\main.c`（12,669B，MD5 `2358f0785e2f7cb3c6d3846c761f3577`）新增 Timer1 模式2 9600 波特 UART、状态帧(0x01)/事件帧(0x02)/下行命令帧(0x81)/应答帧(0x09)四类，RUN/ALARM 灯挪至 P3.2/P3.3；产出 `keil_firmware\control.hex`（4810B，MD5 `17ab2aeaa907c0504321c7deb6275852`）。字节级验收通过。
- 上位机（Python + PyQt/PySide + pyserial）、监控 Web 看板：S2/S3 待做，见 STATUS 未做清单。
- 通信协议已锁定，三方直接引用：`doc\UART_PROTOCOL_v1.md`（同份在 `qwen_handoff\`，MD5 `2434105cef86aea672516e2dba2176b5`）。
- 目标运行方式（待实现）：上位机 `python main.py` 起 GUI 并自动连串口；监控 `python app.py` 起看板并自动读上位机推送。
- SolidWorks：需建单一总装配 `.SLDASM`（含爆炸视图、活塞/缸体行程标注），当前只有单零件视图。

## 5. 本机通用坑（写脚本必读）

- **DPI 混算**：非 DPI-aware 进程的 `GetWindowRect`/`SetCursorPos` 是虚拟化坐标（实测 1543×823），而 `ImageGrab`/`CopyFromScreen` 是真实 1920×1080，**比例 1.244**。量坐标只能用真实屏幕图，再 ÷1.244 换成点击坐标；`PrintWindow` 只用于判读画面（另有约 20px 偏移）。
- 键盘 `SendInput` 被低级钩子拦死（返回 0 / err=87）；鼠标 `SetCursorPos`+`mouse_event` 可用。
- PowerShell 5.1 按 ANSI 读 `.ps1`（中文需 UTF-8 BOM 或纯 ASCII）；AD 的 `.pas` 要 GBK+CRLF。
- 交付物出卡片先复制到 ASCII 目录 `F:\Qwen\`（中文路径不渲染卡片）。
- 每批可写操作后**立刻保存并核对磁盘字节数/时间戳**；绝不 kill 未保存实例。
