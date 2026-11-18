# AD 原理图 v16c1 短桩重铺 —— 真实 Validate 验收报告

验收对象：`ad_schematic\StickInsert_Control_8051_v16.SchDoc`
文件大小 120,320 字节，MD5 `241051e6b52819f4f76f1bc1393130b3`（验收全程只读，跑完后复核仍为该值）
验收时间：2026-11-03
验收工具：Altium Designer 21.0.8 自带编译器（DelphiScript 直接调用，不经 GUI 点击）

## 一、结论

改动范围内的问题已全部清零，且没有引入任何新告警。

| 指标 | 改线前（对照） | 改线后（目标） | 变化 |
|---|---|---|---|
| Validate 消息总数 | 148 | 109 | −39 |
| Error | 3 | 0 | −3 |
| Warning | 145 | 109 | −36 |
| Floating（网络对象未连上） | 36 | 0 | −36 |
| 单脚网络（only one pin） | 3 | 0 | −3 |
| Off grid（图元不在栅格上） | 83 | 83 | 0（范围外，未变差） |
| Footprint not found（封装库缺失） | 26 | 26 | 0（范围外，未变差） |
| 改线后新增的问题 | — | 0 | 0 |

消失的 39 条 = 36 条 Floating + 3 条单脚网络错误，与预测完全一致；逐条清单见附录 A，其余 109 条与改线前逐字相同（`ws_compare_accept.py` 按文本比对，新增 0 条、其它变化 0 条）。

## 二、验收方法（为什么这次的结果可信）

之前靠截屏抓消息面板，容易被 Altium 365 登录弹窗和 DPI 缩放干扰。这次改为在 AD 内部用 DelphiScript 直接驱动编译器并读取消息管理器，全程不点 GUI、不截图：

```pascal
WS := GetWorkSpace;
P  := WS.DM_Projects(0);
D  := P.DM_ProjectDocuments(0);
MM := WS.DM_MessagesManager;
MM.ClearMessages;
Ok := D.DM_Compile;                 // 返回 true
For I := 0 To MM.MessagesCount - 1 Do
    LogLine('MSG|' + MM.Messages(I).MsgClass + '|' + MM.Messages(I).Source +
            '|' + MM.Messages(I).Document + '|' + MM.Messages(I).Text);
```

冷启动 AD（先杀 X2 进程）→ 装载脚本工程 + 设计工程 + 原理图 → 运行上述过程 → 把全部消息落到文本文件；运行器不发 Ctrl+S，因此磁盘上的原理图不会被改写。

为排除「路径编码 / 复制件」造成的偏差，做了两次独立测量，结果完全相同：

1. **就地验证**：真实目标文件本身。因为 AD 在这个未登录的安装里打不开中文路径工程的成员文档（`DM_ProjectDocumentCount = 0`），改用目录联接 `F:\Qwen\adsch` → `…\ad_schematic`，工程文件 `F:\Qwen\vreal2.PrjPcb` 用纯 ASCII 相对路径指向真实目标。消息 `Document` 字段为 `adsch/StickInsert_Control_8051_v16.SchDoc`，即真实文件本体。证据：`F:\Qwen\ws_validate_vreal_inplace.txt`。
2. **等值副本验证**：`F:\Qwen\vctarg\vctarg.SchDoc`，与目标 MD5 逐字节相同（`241051e6…`）。证据：`F:\Qwen\ws_validate_vctarg.txt`。

对照组（改线前）用同一套方法测得 148 条，源文件是改动前的原始备份 `F:\Qwen\target_backup_pristine_e9cebcd7.SchDoc`（116,736 字节）。证据：`F:\Qwen\ws_validate_vcpre.txt`。

## 三、盘上对账（与 Validate 互相印证）

- 记录数护栏全部成立：`RECORD=1:26 / 2:123 / 17:33 / 25:72 / 27:105 / 28:1 / 29:148 / 31:1 / 34:26 / 41:176 / 44:26`（R27 走线 = 105 条短桩；R1/R2/R25/R17/R34 五个护栏未动）。
- 几何连通审计（`F:\Qwen\verify_laid.py`）：改线前 wires=70 / segs=500 / floating=31，改线后 wires=105 / segs=131 / floating=0。AD 自己报的 36 条 Floating 比几何审计的 31 条多 5 条（AD 还计入电源符号引脚容差等判定），两套口径改线后都归零。

## 四、范围外的已知项（本轮明确不处理）

1. 26 条 `Footprint … cannot be found`：工程未挂封装库，属 BOM/封装阶段，与连线无关。
2. 83 条 `Off grid …`：改线前就存在的图元栅格问题（引脚、网络标签、电源符号），本轮红线要求「只改连线」，未顺手挪动。
3. 3 条单脚网络错误本轮已随连线自然消失，无需 No-ERC 抑制。
4. 一处游离的 `RECORD=28` 文本框（护栏 28:1），非连线内容。

以上 1、2 两项若要清零，需要单独一轮（挂库 + 图元挪栅格），不在本次「只改连线（R27）与 No-ERC」的授权范围内。

## 五、红线复核

- 源装配体 `三棒签插签装置.SLDASM`（MD5 `d4bfee70`）：本轮未触碰。
- D 盘：零写入。
- 既有产物：未回滚、未删除；`ad_schematic` 目录在就地验证前后文件清单逐行一致（`dir_before_inplace.txt` / `dir_after_inplace.txt` 无差异），临时目录联接 `F:\Qwen\adsch` 已删除，删除后真实目录 105 项完好。
- 目标原理图：验收前后 MD5 均为 `241051e6b52819f4f76f1bc1393130b3`。

## 附录 A：改线后消失的 39 条（逐条）

Floating 网络标签（23 条）：DRV_YV1@(150,800)、DRV_YV2@(150,780)、DRV_YV2@(510,720)、DRV_YV3@(150,750)、LED_ALM_NODE@(780,500)、LED_ALM_NODE@(850,500)、LED_RUN_NODE@(780,550)、LED_RUN_NODE@(850,550)、MCU_TXD@(1050,660)、RESET@(290,290)、SQ1@(780,790)、SQ2@(780,760)、SQ3@(780,730)、USB_DM@(1050,630)、USB_DM@(1210,660)、USB_DP@(1050,650)、USB_DP@(1210,650)、XTAL2@(210,340)、YV1@(290,730)、YV1@(70,890)、YV2@(70,850)、YV3@(290,690)、YV3@(70,810)

Floating 电源对象（13 条）：+24V@(70,810)、+24V@(70,850)、+24V@(70,890)、+5V@(1050,610)、+5V@(780,500)、+5V@(780,550)、+5V@(780,730)、+5V@(780,760)、+5V@(780,790)、GND@(1190,680)、GND@(210,340)、GND@(290,290)、GND@(290,800)

Error 单脚网络（3 条）：Net LED_ALM has only one pin (Pin U1-13)、Net MCU_RXD has only one pin (Pin U1-10)、Net P0_0 has only one pin (Pin U1-32)

## 附录 B：证据文件

**随交付件归档（本目录 `validate_evidence\`）**：`pre_rewire_148msgs.txt`(改线前 148 条) · `post_rewire_inplace_109msgs.txt`(改线后就地 109 条) · `post_rewire_copy_109msgs.txt`(改线后等值副本 109 条) · `accept_diff_item_by_item.txt`(逐项比对) · `category_summary.txt`(分类汇总) · `ondisk_connectivity_audit.txt`(盘上连通审计 31→0)。项目根 `_一键自检.py` 第 5 组会校验这些文件的计数，证据与交付件同进同退。

工作目录原件（脚本与运行器）仍在 `F:\Qwen\`：

| 文件 | 内容 |
|---|---|
| `F:\Qwen\ws_validate_vcpre.txt` | 改线前对照：148 条原始消息 |
| `F:\Qwen\ws_validate_vreal_inplace.txt` | 改线后就地（真实目标）：109 条原始消息 |
| `F:\Qwen\ws_validate_vctarg.txt` | 改线后等值副本：109 条原始消息 |
| `F:\Qwen\val_accept_diff_inplace.txt` | 逐项比对（分类计数 + 消失/新增清单） |
| `F:\Qwen\val_summary_v16c1.txt` | 两份消息的分类汇总 |
| `F:\Qwen\floating_pre_post.txt` | 盘上几何连通审计（改线前 31 → 改线后 0） |
| `F:\Qwen\self_probe_ws8.pas` / `WsProbe8.PrjScr` | 可复用的编译+抓消息脚本 |
| `F:\Qwen\ws_run.py` | 冷启动运行器（不保存文件） |
