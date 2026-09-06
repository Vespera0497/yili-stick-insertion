# 伊利雪糕三棒签同步插签自动化设备

**项目类型**：AI协作项目（PLC控制电路 + C语言核心算法 + Qt上位机界面）
**时间**：2026.7 - 2026.9（内蒙古蒙辰轻工机械有限公司实习期间）
**技术栈**：Altium Designer（PLC原理图） / C语言（核心控制算法） / Qt6（上位机监控界面） / Python（仿真验证）

---

## 一、项目背景

传统雪糕插签设备仅支持单根棒签同步插入，无法满足伊利集团新款雪糕**三根不同位置、不同长度棒签同步成型插签**的新工艺需求。多气缸长短行程不一致极易出现插签偏移、雪糕破损、不同步、卡顿等生产故障。

本项目设计多气缸差异化同步插签自动化控制系统，在保证雪糕完整成型的前提下，实现三根长短不一棒签精准、同步、稳定插入，适配量产流水线标准。

## 二、项目结构

```
伊利雪糕三棒签插签设备项目/
├── src/                          # C语言核心控制算法
│   ├── stick_insert_control.c    # 标准C99，可gcc/Code::Blocks/Qt编译
│   └── stick_insert_control.py   # Python同算法仿真（直接运行验证）
├── qt_gui/                       # Qt6上位机监控界面
│   ├── CMakeLists.txt
│   ├── main.cpp
│   ├── mainwindow.h/cpp          # 主界面（控制按钮+参数+实时曲线+日志）
│   └── cylindercontrol.h/cpp     # 三气缸同步控制器（C++核心类）
├── ad_schematic/                 # Altium Designer PLC控制原理图
│   ├── GenerateStickInsertSchematic.pas  # AD脚本，运行自动生成原理图
│   └── 设计说明.md                # 电路模块、I/O分配、控制逻辑说明
├── doc/                          # 项目文档
├── CMakeLists.txt                # C语言版构建
└── README.md
```

## 三、核心技术方案

| 方案点 | 实现方式 |
|--------|----------|
| PLC控制电路 | Altium Designer绘制，含PLC+三路电磁阀+传感器+急停+过载保护+端子排 |
| 差异化延时补偿 | AI仿真筛选最优时序：短缸250ms/中缸125ms/长缸0ms，三缸同时到位 |
| 分级同步控制 | 长短气缸独立行程校准 + 同步收尾控制 |
| 核心算法 | C语言实现梯形速度曲线 + 10ms控制周期 + 脉冲输出 |
| 上位机监控 | Qt6 Widgets界面，实时显示三缸位置曲线、状态、参数调整、日志 |
| 容错机制 | 过载保护（负载>85%停机）、偏差自检（>1.5mm闭环补偿）、急停 |

## 四、运行与验证

### 4.1 C语言核心算法（仿真验证）

```bash
# Python版直接运行（已验证通过）
python src/stick_insert_control.py

# C语言版编译
gcc src/stick_insert_control.c -o stick_insert_control.exe -lm
./stick_insert_control.exe
```

验证输出：
```
差异化启动延时：气缸1 250ms / 气缸2 125ms / 气缸3 0ms
t= 650ms | 气缸1到位 气缸2到位 气缸3到位
三缸到位时间差：0.0 ms
>> 同步性判定：PASS —— 三根棒签同步精准插入
```

### 4.2 Qt上位机界面

```bash
# 用 Qt Creator 打开 qt_gui/CMakeLists.txt
# 或命令行：
cd qt_gui
cmake -S . -B build -DCMAKE_PREFIX_PATH=<Qt6路径>
cmake --build build
./build/StickInsertGUI
```

界面功能：
- 启动/停止/复位/急停控制按钮
- 三气缸实时状态（位置、速度、到位/过载状态、进度条）
- 参数设置（行程、延时补偿可在线调整）
- 实时位置-时间曲线（Qt Charts，三色区分三缸）
- 运行日志与同步性判定结果

### 4.3 Altium Designer原理图

1. 打开AD，新建PCB工程
2. DXP -> Run Script -> 选择 `ad_schematic/GenerateStickInsertSchematic.pas`
3. 执行 `GenerateStickInsertSchematic`，自动生成PLC控制原理图
4. 编译工程，检查无错误后可绘制PCB

## 五、与AI协作的分工

- **本人（核心主导）**：整体机械结构与三气缸长短布局方案设计；PLC控制电路原理图设计（AD）；插签工艺标准、同步动作逻辑、安全容错机制制定；C语言核心控制算法编写；Qt上位机界面开发；现场调试、误差修正、设备落地验证。
- **AI（辅助）**：推演多气缸长短行程同步干涉风险；提供同步控制逻辑优化方案；辅助优化C语言程序结构与冗余代码；模拟不同工况插签误差并给出优化思路；辅助Qt界面代码生成与调试。

## 六、项目成果

1. 三根不同长度棒签同步精准插入，雪糕成品完好无破损；
2. 插签精度、同步性达到伊利食品流水线量产标准（到位时间差0ms）；
3. 大幅降低人工调试周期，系统运行稳定、故障率极低；
4. 完整掌握AI辅助机械自动化设计、控制逻辑优化、程序迭代的工程协作方法。
