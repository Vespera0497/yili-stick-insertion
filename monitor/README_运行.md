# 三棒签 · 监控 Web 看板（S3）三步运行

零第三方依赖（Python 内置 http.server + 静态页 1s 轮询）。数据源**只读**
`qt_gui\host_pc\stickinsert.db`（S2 上位机 push.py 的四张表），绝不写库。

## 运行

1. `cd F:\伊利雪糕三棒签插签设备项目\monitor`
2. `D:\ANACONDA\python.exe app.py`          （默认 http://127.0.0.1:8765；可带端口参数覆盖）
3. 浏览器开 `http://127.0.0.1:8765/`

无硬件演示（看板 + 造数一起跑，页面显示"数据新鲜"）：

```
cd F:\伊利雪糕三棒签插签设备项目\qt_gui\host_pc
start /b D:\ANACONDA\python.exe feed_test.py     （约 10s 造 100 帧真实格式数据流）
cd ..\..\monitor
D:\ANACONDA\python.exe app.py
```

## 页面四类数据

| 区块 | 内容 |
|---|---|
| 实时运行状态 | 模式（IDLE/RUNNING/ESTOP/FAULT）、九位 IO 指示灯、丢帧/校验错、updated_at 超 3s 判"数据未刷新" |
| 产量与节拍 | 累计签签成功、当日产量（当日 CNT 最大−最小）、最近节拍、日均节拍 |
| 扩展指标（软件口径） | OEE(简化)=可用率×良率、良率、可用率、温度/气压（哨兵时显示 "-"）、当日告警数 |
| 故障与告警事件 | events 流水带时间戳、急停红色高亮、增量拉取（?after=ID） |

口径说明写在页面脚注，均为软件统计口径，不冒充实测值。

## 只读保证

`app.py` 的 `ro()`：优先 `file:...?mode=ro` URI 打开；若库残留 `-wal/-shm`（写进程异常
退出所致）导致 ro 无法建 shm，则退化为普通连接 + `PRAGMA query_only=ON`
（SQL 层强制只读）。两种路径都不产生任何写入。

## 诊断工具

- `probe.py` —— 探测 DB 路径/存在性/连接方式，定位 "unable to open database file" 类问题。
- `diag_db.py` —— 只读直查四张表行数与最近数据。

## 物证

- `monitor_shot.png` —— 无头 Edge 截的真实看板（数据新鲜 0s、RUNNING、OEE 100%、急停红显）。

## 已知边界

- 历史趋势目前只有数值，未画折线图（可后续加）。
- 真实设备联调依赖 S2 连上真 CH340；当前验证均为协议真实格式的合成数据流。
