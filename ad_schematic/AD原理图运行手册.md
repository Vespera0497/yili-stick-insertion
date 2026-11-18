# Altium Designer 原理图 —— 本机运行手册（针对 AD21）

> 本手册解决的问题：豆包线程里 AD 原理图只留了脚本、从没真正跑出 `.SchDoc`。
> 由于 AD 是图形界面软件，只能在**你的本机**生成工程，下面的步骤请在本机 AD21 中执行。

---

## 一、前置说明（AD21 的库现状）

- AD21 **默认库不含** `AT89C52`、`PLC.IntLib` 这类符号。
- 本项目原理图用的是 **PLC（西门子 S7-1200）** 方案，脚本里已经把 PLC 改成
  **"画框 + 引脚标注"**，不依赖任何外部库，所以能直接解析、编译不报 ERC。
- 其余符号（继电器 `Relay-SPST`、按钮 `SW-PB`、熔断 `Fuse`、端子排 `Header 8`、
  `+24V`/`GND` 电源端口）都取自 AD 自带的
  `Miscellaneous Devices.IntLib` / `Miscellaneous Connectors.IntLib`，可正常解析。

> 如果你想要"真正的 S7-1200 元件符号"（带引脚、带 3D），需从 Altium Vault / 官方
> 库或第三方库导入一个 PLC 符号替换画框；本脚本给出的是可编译的骨架版。

---

## 二、生成步骤（约 3 分钟）

1. 打开 **Altium Designer 21**。
2. `File -> New -> Project -> PCB Project`，给工程起名
   （如 `StickInsert.PrjPcb`），保存到项目目录 `ad_schematic/`。
3. 在工程上右键 `Add New to Project -> Schematic`，
   **新建一个原理图页并保持它处于打开/激活状态**（例如 `StickInsert_Control.SchDoc`）。
4. `DXP -> Run Script... -> Browse`，选中
   `ad_schematic/GenerateStickInsertSchematic.pas`，
   在弹出的函数列表里选 **`GenerateStickInsertSchematic`** 执行。
5. 脚本会把元件、电源端口、网络标签、说明文字放到**当前这个原理图页**上，
   并弹出"布局已生成"提示。
6. `File -> Save` 保存该原理图页。

---

## 三、编译前必须做：把引脚连到网络标签（关键一步）

脚本放出的是"布局骨架 + 网络标签"，**元件引脚还没有导线接到网络标签上**，
直接编译会出现大量"引脚悬空"的 ERC 警告，而且网络不会真正连通。

请按下面的**连线清单**在 AD 里用 `Place -> Wire` 把引脚接到对应网络标签：

| 网络标签 | 连接对象 |
|---|---|
| `+24V` | 各元件 VCC/电源引脚、PLC 电源脚 |
| `GND` | 各元件 GND 引脚、PLC 地脚 |
| `Q0.0_YV1` | PLC 输出脚 → YV1 继电器线圈一端 |
| `Q0.1_YV2` | PLC 输出脚 → YV2 继电器线圈一端 |
| `Q0.2_YV3` | PLC 输出脚 → YV3 继电器线圈一端 |
| `I0.0_SQ1` | SQ1 按钮 → PLC 输入脚 |
| `I0.1_SQ2` | SQ2 按钮 → PLC 输入脚 |
| `I0.2_SQ3` | SQ3 按钮 → PLC 输入脚 |
| `I0.3_SB1` | SB1 急停(常闭) → PLC 输入脚 |
| `I0.4_FR1` | FR1 过载 → PLC 输入脚 |

> 小技巧：同一网络只需在导线上放一个同名 Net Label 即可自动连通，不必每个引脚都拉线。
> 嫌逐个连麻烦，也可以在 PLC 画框的对应边上放引脚（`Place -> Pin`）再连线。

---

## 四、编译与验证

1. `Project -> Compile PCB Project` 编译。
2. 看 `Messages` 面板：理想状态是 **0 Error**；若有 "Unconnected pin" 类 Warning，
   回到第三步把对应引脚连上即可。
3. 编译通过后即可 `File -> New -> PCB` 进入版图设计（本项目交付以原理图为准，
   版图非必备）。

---

## 五、与 Proteus 仿真的关系（易混淆点）

- **AD 原理图**用 **PLC（S7-1200）** 作为主控；
- **Proteus 仿真**用 **STC89C52 单片机**（见 `proteus_simulation/仿真说明.md`）。
- 两者是"同一控制逻辑、不同实现平台"的简化表达，算法完全一致
  （短缸 250ms / 中缸 125ms / 长缸 0ms 差异化延时补偿）。
- 若你希望原理图和仿真主控一致，可把 AD 里的 PLC 画框替换为 51 单片机符号，
  并在 I/O 表里对齐 P1.0~P1.2（电磁阀）、P2.0~P2.3（传感器/急停）、P3.0~P3.1（指示灯）。
