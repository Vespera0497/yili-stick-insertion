#ifndef CYLINDERCONTROL_H
#define CYLINDERCONTROL_H

#include <QObject>
#include <QTimer>
#include <QVector>

/**
 * @brief 三气缸差异化延时同步插签控制器
 *
 * 实现伊利雪糕三棒签同步插签设备的核心控制逻辑：
 *  - 多气缸长短行程差异化延时补偿
 *  - 分级同步控制（独立行程校准 + 同步收尾）
 *  - 过载保护 / 偏差自检 / 闭环补偿
 *  - 10ms 控制周期（对应 PLC 扫描周期）
 */
class CylinderControl : public QObject
{
    Q_OBJECT
public:
    explicit CylinderControl(QObject *parent = nullptr);

    struct CylinderState {
        double stroke;       // 行程 mm
        double maxSpeed;     // 最大速度 mm/s
        double accel;        // 加速度 mm/s^2
        double delayMs;      // 差异化启动延时 ms
        double position;     // 当前位置 mm
        double speed;        // 当前速度 mm/s
        double load;         // 负载 %
        bool   arrived;      // 是否到位
        bool   overload;     // 过载告警
        int    arriveTimeMs; // 到位时刻 ms
    };

    void setStroke(int idx, double mm);
    void setDelay(int idx, double ms);
    void setMaxSpeed(int idx, double v);
    void setSyncTolerance(double mm);
    void setOverloadThreshold(double pct);

    const CylinderState &state(int idx) const { return m_states[idx]; }
    int cylinderCount() const { return 3; }
    bool isRunning() const { return m_running; }
    int elapsedMs() const { return m_elapsedMs; }
    double syncTolerance() const { return m_syncTolerance; }
    double lastSyncDeviation() const { return m_lastDeviation; }

public slots:
    void start();     // 启动插签循环
    void stop();      // 停止
    void reset();     // 复位
    void emergencyStop(); // 急停

signals:
    void stateUpdated();           // 状态更新（UI刷新）
    void cylinderArrived(int idx); // 某气缸到位
    void allArrived(int spreadMs); // 全部到位，spread=到位时间差
    void overloadAlarm(int idx);   // 过载告警
    void syncDeviation(double mm); // 同步偏差超限
    void logMessage(const QString &msg);

private slots:
    void tick();

private:
    double trajTimeMs(double distance, double vmax, double a) const;
    double trajPos(double elapsedMs, double distance, double vmax, double a) const;

    QVector<CylinderState> m_states;
    QTimer m_timer;
    int    m_elapsedMs;
    bool   m_running;
    double m_syncTolerance;
    double m_overloadThreshold;
    double m_lastDeviation;
    int    m_firstArriveMs;
    int    m_lastArriveMs;
};

#endif // CYLINDERCONTROL_H
