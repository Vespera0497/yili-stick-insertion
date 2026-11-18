# Proteus 建工程清单（给千问办公 GUI 搭建用，照抄即可）

> 目标：在 Proteus 8 里搭出三缸同步控制仿真，加载 `control.hex`，跑通时序。
> `control.hex` 已在本目录备好（与 Keil 工程同源，11.0592 MHz）。

## 一、元件清单（Proteus 8 库 Part 名）
| 用途 | Proteus 元件 | 数量 | 备注 |
|---|---|---|---|
| 主控 | `AT89C52` | 1 | 51 内核（亦可用 STC89C52RC 替代） |
| 电磁阀模拟 | `LED-RED` | 3 | 三缸电磁阀，红绿搭配均可；串 470Ω 限流 |
| 运行指示灯 | `LED-GREEN` | 1 | P3.0 |
| 告警指示灯 | `LED-RED` | 1 | P3.1 |
| 到位传感器 | `BUTTON` | 3 | 常开，P2.0/2.1/2.2 |
| 急停 | `BUTTON` | 1 | **常闭**：属性 `Normal State = Closed`，或仿真时保持按下 |
| 限流电阻 | `RES` | 5 | 5V/10mA ≈ 470Ω，每 LED 一只 |
| 电源/地 | `POWER`、`GROUND` | 各 1 | POWER 设 5V |

## 二、引脚 → 网络表（严格对应 `main.c`）
| 51 引脚 | main.c 符号 | 接法 |
|---|---|---|
| P1.0 | YV1 电磁阀1（短缸30mm） | → LED1 阳极（串 470Ω → GROUND） |
| P1.1 | YV2 电磁阀2（中缸45mm） | → LED2 阳极（串 470Ω → GROUND） |
| P1.2 | YV3 电磁阀3（长缸60mm） | → LED3 阳极（串 470Ω → GROUND） |
| P2.0 | SQ1 到位传感器1 | → 按钮1（一端接 P2.0，一端接 GROUND） |
| P2.1 | SQ2 到位传感器2 | → 按钮2 |
| P2.2 | SQ3 到位传感器3 | → 按钮3 |
| P2.3 | SB1 急停（常闭） | → 按钮4（常闭，平时导通；断开=急停） |
| P3.0 | LED_RUN 运行绿 | → LED-GREEN 阳极（串 470Ω → GROUND） |
| P3.1 | LED_ALARM 告警红 | → LED-RED 阳极（串 470Ω → GROUND） |
| VCC | — | → POWER 5V |
| GND | — | → GROUND |

## 三、加载固件与晶振
1. 双击 `AT89C52` → `Program File` = `.\control.hex`（本目录已备）。
2. 晶振（Clock）设为 **11.0592 MHz**（与 Keil 工程一致）。
3. OK 保存。

## 四、验收时序（对照 `main.c` 逻辑）
- 上电：**LED3（长缸，P1.2）立即亮**（延时 0ms）。
- 约 **125ms** 后 LED2（中缸，P1.1）亮。
- 约 **250ms** 后 LED1（短缸，P1.0）亮。
- 依次按 SQ1/SQ2/SQ3 → 三缸"同步到位"判定；全到位（≥650ms）绿灯、保持 500ms 后复位。
- 按急停（或释放常闭 SB1）→ 所有电磁阀 LED 熄灭、告警红灯亮。

## 五、完成后
- 保存工程为 `proteus_simulation\三棒签仿真.pdsprj`。
- 汇报：能否跑通、时序是否一致；不一致记录现象（固件时序常数或接线极性差异）。
- 接着做 SolidWorks 环节（`solidworks/` 已备宏）。
