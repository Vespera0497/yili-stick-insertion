/*
 * 三棒签同步插签设备 - 51单片机控制代码 (v2: 控制逻辑 + UART 通信)
 * 芯片：STC89C52RC / AT89C52 (DIP-40), 11.0592MHz
 * 协议：doc\UART_PROTOCOL_v1.md v1.0 (R1 锁定)
 * 变更：LED_RUN/LED_ALARM 由 P3.0/P3.1 挪到 P3.2/P3.3，释放硬件 UART 脚；
 *       叠加 9600/8N1 上行状态帧/事件帧/命令应答 + 下行命令解析。
 *
 * 关键实现约定（照协议，不自创）：
 *  - 帧 = AA 55 | LEN | TYPE | PAYLOAD[LEN] | SUM，SUM=(LEN+TYPE+PAYLOAD)&0xFF，LEN 1..15
 *  - 多字节字段一律 **小端**（LSB 先）。Keil C51 整数为大端，因此所有打包/解包
 *    都用手写的移位，绝不依赖结构体或数组的内存布局。
 *  - SB1 常闭：P2.3=0 表示急停按下；DIO bit6 上报 **1=急停触发**（取反在固件内做，协议 §4）。
 *  - 温度/传感器未接：TMP 发 0x7FFF、PRS 发 0xFFFF 哨兵（协议 §4）。
 *  - 循环成功**没有**事件码（协议 §5 未定义，且 §1.5 禁止自创），成功次数由状态帧 CNT 承载。
 *  - 原 delay_ms(500) 阻塞改为 timer_ms 时间戳等待，否则 10Hz 状态帧会被卡住。
 *  - 一帧 19 字节 @9600 = 19.8ms，发送为查询式阻塞（最坏阻塞 19.8ms/100ms），
 *    控制时序由 Timer0 的 timer_ms 驱动，不受该阻塞影响。
 */

#include <reg52.h>
#include <intrins.h>

/* ================= 引脚定义 ================= */
sbit YV1 = P1^0;         /* 电磁阀1 短缸30mm */
sbit YV2 = P1^1;         /* 电磁阀2 中缸45mm */
sbit YV3 = P1^2;         /* 电磁阀3 长缸60mm */
sbit SQ1 = P2^0;         /* 气缸1到位 */
sbit SQ2 = P2^1;         /* 气缸2到位 */
sbit SQ3 = P2^2;         /* 气缸3到位 */
sbit SB1 = P2^3;         /* 急停（常闭，断开=按下） */
sbit LED_RUN   = P3^2;   /* 运行灯，低有效 —— 已从 P3^0 挪走 */
sbit LED_ALARM = P3^3;   /* 告警灯，低有效 —— 已从 P3^1 挪走 */

/* ================= 参数 ================= */
#define DELAY1_MS      250
#define DELAY2_MS      125
#define DELAY3_MS        0
#define SYNC_MS        650     /* 三缸全到位判定时刻 */
#define TIMEOUT_MS    1000     /* 超时告警，可被 0x04 参数下装改 */
#define HOLD_MS        500     /* 成功后保持 */
#define FRAME_MS       100     /* 状态帧周期 = 10Hz */

/* 协议 TYPE / 事件码 / 结果码 */
#define T_STATE      0x01
#define T_EVENT      0x02
#define T_ACK        0x03
#define T_CMD        0x81
#define E_ESTOP      0x01
#define E_TIMEOUT    0x02
#define E_FAILLIMIT  0x03
#define E_ALARM      0x04
#define E_RESET      0x05
#define R_OK         0x00
#define R_BADCMD     0x01
#define R_BADSTATE   0x02
#define R_BADPARAM   0x03

/* MODE */
#define MD_IDLE      0
#define MD_RUN       1
#define MD_ESTOP     2
#define MD_FAULT     3

/* ================= 全局 ================= */
static void rx_byte(unsigned char b);      /* 前向声明：UART_ISR 里要用 */

unsigned int  timer_ms = 0;
bit system_running = 0;
bit sync_pass      = 0;

unsigned char mode_state = MD_IDLE;
unsigned long cnt_ok     = 0;   /* 累计插签成功次数 -> CNT[4] */
unsigned int  cyc_last   = 0;   /* 最近一次循环节拍 ms -> CYC[2] */
unsigned int  timeout_ms = TIMEOUT_MS;
unsigned int  hold_to    = 0;
bit           estop_latched = 0;
bit           estop_prev      = 0;
unsigned char fail_streak     = 0;
unsigned char seq_tx          = 0;   /* 状态帧 SEQ */
unsigned long evt_seq         = 0;   /* 事件帧 SEQ[4] */
bit           tx_busy         = 0;
bit           frame_due       = 0;   /* Timer0 每 FRAME_MS 置位 */
unsigned int  ms_since_frame  = 0;

/* ================= Timer0 1ms ================= */
void Timer0_Init(void)
{
    TMOD |= 0x01;
    TH0 = 0xFC; TL0 = 0x66;
    ET0 = 1;
    TR0 = 1;
}

void Timer0_ISR(void) interrupt 1
{
    TH0 = 0xFC; TL0 = 0x66;
    if (timer_ms < 65535) timer_ms++;
    if (++ms_since_frame >= FRAME_MS) { ms_since_frame = 0; frame_due = 1; }
}

/* ================= UART 9600/8N1, Timer1 模式2 ================= */
void UART_Init(void)
{
    TMOD |= 0x20;          /* T1 模式2 自动重载 */
    TH1 = 0xFD; TL1 = 0xFD;/* 11.0592MHz -> 9600 */
    SCON = 0x50;           /* 8N1 + 允许接收 */
    TR1 = 1;
    ES   = 1;
    EA   = 1;
}

void uart_send_byte(unsigned char b)
{
    while (tx_busy) {; }
    TI = 0; tx_busy = 1;
    SBUF = b;
}

/* ---- 接收只在中断里入环形缓冲，解析/发送一律留在主循环 ----
   否则 send_frame/uart_send_byte 会同时被主循环和 ISR 调用（链接器
   WARNING L15 MULTIPLE CALL TO SEGMENT），中断会在主循环填 gbuf 填到一半时
   改写它，上位机收到撕裂帧。 */
static volatile unsigned char rx_head = 0, rx_tail = 0;
static unsigned char xdata rx_ring[8];

void UART_ISR(void) interrupt 4
{
    unsigned char b, n;
    if (RI) {
        RI = 0;
        b = SBUF;
        n = (unsigned char)((rx_head + 1) & 7);
        if (n != rx_tail) { rx_ring[rx_head] = b; rx_head = n; }  /* 满则丢弃 */
    }
    if (TI) { TI = 0; tx_busy = 0; }
}

/* 主循环里排空环形缓冲，逐字节喂给状态机 */
static void rx_poll(void)
{
    while (rx_tail != rx_head) {
        rx_byte(rx_ring[rx_tail]);
        rx_tail = (unsigned char)((rx_tail + 1) & 7);
    }
}

/* ================= 组帧发送 =================
   C51 的局部数组全落在 data 段，多个发送函数的局部缓冲会叠加把 128 字节
   直接寻址区顶穿（实测 data=131.7 -> ERROR L105）。故只用一个模块级共享
   缓冲 gbuf[]，且发送时直接从 gbuf 逐字节写出，不再复制第二份。 */
static unsigned char gbuf[16];

static void send_frame(unsigned char type, unsigned char len)
{
    unsigned char i, sum;
    if (len == 0 || len > 15) return;          /* 协议 §2 LEN 1..15 */
    sum = len + type;
    for (i = 0; i < len; i++) sum += gbuf[i];
    uart_send_byte(0xAA); uart_send_byte(0x55);
    uart_send_byte(len);  uart_send_byte(type);
    for (i = 0; i < len; i++) uart_send_byte(gbuf[i]);
    uart_send_byte(sum);                       /* 低 8 位 */
}

/* 小端手工打包，避开 C51 大端 */
static void put16(unsigned char *d, unsigned int  v) { d[0] = (unsigned char)(v & 0xFF); d[1] = (unsigned char)(v >> 8); }
static void put32(unsigned char *d, unsigned long v)
{
    d[0] = (unsigned char)(v        & 0xFF);
    d[1] = (unsigned char)((v >>  8) & 0xFF);
    d[2] = (unsigned char)((v >> 16) & 0xFF);
    d[3] = (unsigned char)((v >> 24) & 0xFF);
}

/* 0x01 状态帧：SEQ MODE DIO[2] CNT[4] CYC[2] TMP[2] PRS[2] = 14B */
static void send_state(void)
{
    unsigned int dio = 0;

    if (YV1) dio |= 0x0001;
    if (YV2) dio |= 0x0002;
    if (YV3) dio |= 0x0004;
    if (SQ1) dio |= 0x0008;
    if (SQ2) dio |= 0x0010;
    if (SQ3) dio |= 0x0020;
    if (SB1 == 0) dio |= 0x0040;      /* 常闭断开 = 急停触发 -> 归一为 1 */
    if (LED_RUN   == 0) dio |= 0x0080;/* 低有效：0=亮 */
    if (LED_ALARM == 0) dio |= 0x0100;

    gbuf[0] = seq_tx++;
    gbuf[1] = mode_state;
    put16(gbuf + 2, dio);
    put32(gbuf + 4, cnt_ok);
    put16(gbuf + 8, cyc_last);
    put16(gbuf + 10, 0x7FFF);         /* TMP 哨兵：未接 */
    put16(gbuf + 12, 0xFFFF);         /* PRS 哨兵：未接 */
    send_frame(T_STATE, 14);
}

/* 0x02 事件帧：EVT SEQ[4] PAR = 6B */
static void send_event(unsigned char evt, unsigned char par)
{
    gbuf[0] = evt;
    evt_seq++;
    put32(gbuf + 1, evt_seq);
    gbuf[5] = par;
    send_frame(T_EVENT, 6);
}

/* 0x03 命令应答：CMD RESULT = 2B */
static void send_ack(unsigned char cmd, unsigned char res)
{
    gbuf[0] = cmd; gbuf[1] = res;
    send_frame(T_ACK, 2);
}

/* ================= 下行帧接收状态机（协议 §10） ================= */
#define RS_HDR0 0
#define RS_HDR1 1
#define RS_LEN  2
#define RS_TYP  3
#define RS_PAY  4
#define RS_SUM  5
static unsigned char rx_st = RS_HDR0, rx_len = 0, rx_idx = 0, rx_type = 0, rx_sum = 0;
static unsigned char rx_pl[8];       /* 下行命令最长 3B，留 8B 足够且省 data */

static void exec_cmd(void)
{
    unsigned char  cmd;
    unsigned int   par;
    if (rx_len < 1) return;
    cmd = rx_pl[0];
    par = (rx_len >= 3) ? (unsigned int)(rx_pl[1] | ((unsigned int)rx_pl[2] << 8)) : 0;
    switch (cmd) {
        case 0x01:                          /* 启动 */
            if (estop_latched) { send_ack(cmd, R_BADSTATE); break; }
            timer_ms = 0; sync_pass = 0; hold_to = 0;
            system_running = 1; mode_state = MD_RUN;
            LED_RUN = 0; LED_ALARM = 1;
            send_ack(cmd, R_OK);
            break;
        case 0x02:                          /* 停止：复位三缸 */
            YV1 = 0; YV2 = 0; YV3 = 0;
            system_running = 0;
            mode_state = estop_latched ? MD_ESTOP : MD_IDLE;
            send_ack(cmd, R_OK);
            break;
        case 0x03:                          /* 复位：清计数与节拍 */
            cnt_ok = 0; cyc_last = 0; fail_streak = 0;
            YV1 = 0; YV2 = 0; YV3 = 0;
            system_running = 0; sync_pass = 0; timer_ms = 0; hold_to = 0;
            timeout_ms = TIMEOUT_MS;
            mode_state = estop_latched ? MD_ESTOP : MD_IDLE;
            send_ack(cmd, R_OK);
            send_event(E_RESET, 0);
            break;
        case 0x04:                          /* 参数下装：超时阈值 ms */
            if (par < 100 || par > 60000) { send_ack(cmd, R_BADPARAM); break; }
            timeout_ms = par;
            send_ack(cmd, R_OK);
            break;
        default:
            send_ack(cmd, R_BADCMD);
            break;
    }
}

static void rx_byte(unsigned char b)
{
    switch (rx_st) {
        case RS_HDR0: if (b == 0xAA) rx_st = RS_HDR1; break;
        case RS_HDR1: if (b == 0x55) rx_st = RS_LEN;
                      else if (b == 0xAA) rx_st = RS_HDR1;
                      else rx_st = RS_HDR0;
                      break;
        case RS_LEN:  if (b >= 1 && b <= 15) { rx_len = b; rx_idx = 0; rx_sum = b; rx_st = RS_TYP; }
                      else rx_st = RS_HDR0;                 /* 非法 LEN -> 重找帧头 */
                      break;
        case RS_TYP:  rx_type = b; rx_sum += b; rx_st = RS_PAY; break;
        case RS_PAY:  rx_sum += b;
                      if (rx_idx < 8) rx_pl[rx_idx] = b;   /* 只留前 8B，仍按全 LEN 算 SUM */
                      rx_idx++;
                      if (rx_idx >= rx_len) rx_st = RS_SUM;
                      break;
        case RS_SUM:  if (b == rx_sum && (rx_type & 0x80)) { exec_cmd(); }
                      rx_st = RS_HDR0;                      /* 方向不符/校验失败一律丢弃 */
                      break;
        default: rx_st = RS_HDR0; break;
    }
}

/* ================= 急停 ================= */
bit Check_EStop(void)
{
    bit now = (SB1 == 0);
    if (now) {
        YV1 = 0; YV2 = 0; YV3 = 0;
        LED_RUN = 1; LED_ALARM = 0;
        system_running = 0;
        estop_latched = 1;
        mode_state = MD_ESTOP;
        if (!estop_prev) send_event(E_ESTOP, 0);   /* 边沿触发 */
        estop_prev = 1;
        return 1;
    }
    if (estop_prev) {                              /* 急停释放 */
        estop_prev = 0;
        estop_latched = 0;
        mode_state = MD_IDLE;
    }
    return 0;
}

/* ================= 主函数 ================= */
void main(void)
{
    YV1 = 0; YV2 = 0; YV3 = 0;
    LED_RUN = 1; LED_ALARM = 1;

    Timer0_Init();
    UART_Init();
    EA = 1;

    mode_state = MD_IDLE;
    send_event(E_RESET, 1);          /* 上电复位完成，协议 §5 要求 */

    while (1)
    {
        rx_poll();

        if (Check_EStop()) {
            if (frame_due) { frame_due = 0; send_state(); }
            continue;
        }

        if (!system_running) {
            timer_ms = 0; sync_pass = 0; hold_to = 0;
            system_running = 1;
            LED_RUN = 0; LED_ALARM = 1;
            mode_state = MD_RUN;
        }

        if (timer_ms >= DELAY3_MS) YV3 = 1;
        if (timer_ms >= DELAY2_MS) YV2 = 1;
        if (timer_ms >= DELAY1_MS) YV1 = 1;

        if (!sync_pass && SQ1 == 1 && SQ2 == 1 && SQ3 == 1 && timer_ms >= SYNC_MS) {
            sync_pass  = 1;
            cyc_last   = timer_ms;
            cnt_ok++;
            fail_streak = 0;
            LED_ALARM  = 1;
            hold_to    = timer_ms + HOLD_MS;     /* 非阻塞保持，替代 delay_ms(500) */
        }

        if (sync_pass && timer_ms >= hold_to) {
            YV1 = 0; YV2 = 0; YV3 = 0;
            system_running = 0;
            mode_state = MD_IDLE;
        }

        if (system_running && !sync_pass && timer_ms >= timeout_ms) {
            LED_ALARM = 0;
            YV1 = 0; YV2 = 0; YV3 = 0;
            system_running = 0;
            mode_state = MD_FAULT;
            if (fail_streak < 255) fail_streak++;
            send_event(E_TIMEOUT, fail_streak);
            if (fail_streak >= 3) send_event(E_FAILLIMIT, fail_streak);
        }

        if (frame_due) { frame_due = 0; send_state(); }
    }
}
