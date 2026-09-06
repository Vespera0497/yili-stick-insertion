#ifndef MAINWINDOW_H
#define MAINWINDOW_H

#include <QMainWindow>
#include "cylindercontrol.h"

QT_BEGIN_NAMESPACE
class QChart;
class QLineSeries;
class QValueAxis;
QT_END_NAMESPACE

class MainWindow : public QMainWindow
{
    Q_OBJECT
public:
    explicit MainWindow(QWidget *parent = nullptr);
    ~MainWindow();

private slots:
    void onStartClicked();
    void onStopClicked();
    void onResetClicked();
    void onEmergencyStop();
    void onApplyParams();
    void updateUI();
    void onCylinderArrived(int idx);
    void onAllArrived(int spreadMs);
    void onOverload(int idx);
    void onSyncDeviation(double mm);
    void appendLog(const QString &msg);

private:
    void setupChart();
    void updateChart();
    void loadParamsToUI();

    CylinderControl *m_ctrl;
    QChart *m_chart;
    QLineSeries *m_series[3];
    QValueAxis *m_axisX;
    QValueAxis *m_axisY;
    int m_chartMaxMs;
};

#endif // MAINWINDOW_H
