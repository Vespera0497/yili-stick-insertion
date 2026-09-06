#include "cylindercontrol.h"
#include <cmath>

CylinderControl::CylinderControl(QObject *parent)
    : QObject(parent)
    , m_elapsedMs(0)
    , m_running(false)
    , m_syncTolerance(1.5)
    , m_overloadThreshold(85.0)
    , m_lastDeviation(0.0)
    , m_firstArriveMs(-1)
    , m_lastArriveMs(-1)
{
    m_timer.setInterval(10); // 10ms 控制周期
    connect(&m_timer, &QTimer::timeout, this, &CylinderControl::tick);

    // 默认配置：三根不同行程气缸（对应三根不同长度棒签）
    m_states.resize(3);
    const double strokes[3] = {30.0, 45.0, 60.0};
    const double loads[3]   = {30.0, 50.0, 70.0};
    for (int i = 0; i < 3; ++i) {
        m_states[i].stroke       = strokes[i];
        m_states[i].maxSpeed     = 120.0;
        m_states[i].accel        = 800.0;
        m_states[i].delayMs      = 0.0;
        m_states[i].position     = 0.0;
        m_states[i].speed        = 0.0;
        m_states[i].load         = loads[i];
        m_states[i].arrived      = false;
        m_states[i].overload     = false;
        m_states[i].arriveTimeMs = -1;
    }
    // AI仿真筛选的最优差异化延时：短缸晚启动，三者同时到位
    m_states[0].delayMs = 250.0;
    m_states[1].delayMs = 125.0;
    m_states[2].delayMs = 0.0;
}

void CylinderControl::setStroke(int idx, double mm)
{
    if (idx >= 0 && idx < 3) m_states[idx].stroke = mm;
}

void CylinderControl::setDelay(int idx, double ms)
{
    if (idx >= 0 && idx < 3) m_states[idx].delayMs = ms;
}

void CylinderControl::setMaxSpeed(int idx, double v)
{
    if (idx >= 0 && idx < 3) m_states[idx].maxSpeed = v;
}

void CylinderControl::setSyncTolerance(double mm)
{
    m_syncTolerance = mm;
}

void CylinderControl::setOverloadThreshold(double pct)
{
    m_overloadThreshold = pct;
}

void CylinderControl::start()
{
    if (m_running) return;
    reset();
    m_running = true;
    m_timer.start();
    emit logMessage(QStringLiteral("[系统] 插签循环启动，控制周期 10ms"));
}

void CylinderControl::stop()
{
    m_running = false;
    m_timer.stop();
    emit logMessage(QStringLiteral("[系统] 插签循环停止"));
}

void CylinderControl::reset()
{
    m_timer.stop();
    m_running = false;
    m_elapsedMs = 0;
    m_firstArriveMs = -1;
    m_lastArriveMs = -1;
    m_lastDeviation = 0.0;
    for (auto &s : m_states) {
        s.position = 0.0;
        s.speed = 0.0;
        s.arrived = false;
        s.overload = false;
        s.arriveTimeMs = -1;
    }
    emit stateUpdated();
}

void CylinderControl::emergencyStop()
{
    m_timer.stop();
    m_running = false;
    for (auto &s : m_states) {
        s.speed = 0.0;
    }
    emit logMessage(QStringLiteral("[急停] 紧急停止触发，所有气缸输出切断"));
    emit stateUpdated();
}

double CylinderControl::trajTimeMs(double distance, double vmax, double a) const
{
    double tAcc = vmax / a;
    double sAcc = 0.5 * a * tAcc * tAcc;
    if (distance <= 2.0 * sAcc) {
        return 2.0 * std::sqrt(distance / a) * 1000.0;
    }
    double sCruise = distance - 2.0 * sAcc;
    return (2.0 * tAcc + sCruise / vmax) * 1000.0;
}

double CylinderControl::trajPos(double elapsedMs, double distance, double vmax, double a) const
{
    double t = elapsedMs / 1000.0;
    if (t <= 0) return 0.0;
    double tAcc = vmax / a;
    double sAcc = 0.5 * a * tAcc * tAcc;
    double sCruise = distance - 2.0 * sAcc;
    if (t <= tAcc) return 0.5 * a * t * t;
    double t1 = t - tAcc;
    if (t1 <= sCruise / vmax) return sAcc + vmax * t1;
    double t2 = t1 - sCruise / vmax;
    if (t2 <= tAcc) return distance - 0.5 * a * t2 * t2;
    return distance;
}

void CylinderControl::tick()
{
    m_elapsedMs += 10;

    for (int i = 0; i < 3; ++i) {
        auto &s = m_states[i];

        // 过载保护
        if (s.load > m_overloadThreshold && !s.overload) {
            s.overload = true;
            emit overloadAlarm(i);
            emit logMessage(QStringLiteral("[ALARM] 气缸%1 过载保护触发 (负载 %2%)").arg(i+1).arg(s.load, 0, 'f', 1));
            continue;
        }
        if (s.overload) continue;

        double elapsed = m_elapsedMs - s.delayMs;
        if (elapsed <= 0) {
            s.position = 0.0;
            s.speed = 0.0;
        } else if (elapsed >= trajTimeMs(s.stroke, s.maxSpeed, s.accel)) {
            s.position = s.stroke;
            s.speed = 0.0;
        } else {
            s.position = trajPos(elapsed, s.stroke, s.maxSpeed, s.accel);
            s.speed = s.maxSpeed;
        }

        // 到位判断
        if (!s.arrived && s.position >= s.stroke - 0.01) {
            s.arrived = true;
            s.arriveTimeMs = m_elapsedMs;
            if (m_firstArriveMs < 0) m_firstArriveMs = m_elapsedMs;
            m_lastArriveMs = m_elapsedMs;
            emit cylinderArrived(i);
            emit logMessage(QStringLiteral("t=%1ms 气缸%2到位").arg(m_elapsedMs).arg(i+1));
        }
    }

    // 偏差自检
    QVector<int> active;
    for (int i = 0; i < 3; ++i)
        if (!m_states[i].arrived && !m_states[i].overload) active.append(i);
    if (active.size() == 3) {
        double maxDev = 0.0;
        for (int a = 0; a < active.size(); ++a)
            for (int b = a+1; b < active.size(); ++b) {
                double dev = std::fabs(m_states[active[a]].position - m_states[active[b]].position);
                if (dev > maxDev) maxDev = dev;
            }
        m_lastDeviation = maxDev;
        if (maxDev > m_syncTolerance) {
            emit syncDeviation(maxDev);
        }
    }

    emit stateUpdated();

    // 全部到位
    bool all = true;
    for (const auto &s : m_states) if (!s.arrived) { all = false; break; }
    if (all) {
        int spread = m_lastArriveMs - m_firstArriveMs;
        m_timer.stop();
        m_running = false;
        emit allArrived(spread);
        emit logMessage(QStringLiteral("[完成] 三缸全部到位，到位时间差 %1ms").arg(spread));
    }
}
