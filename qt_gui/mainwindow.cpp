#include "mainwindow.h"
#include <QtCharts/QChart>
#include <QtCharts/QLineSeries>
#include <QtCharts/QValueAxis>
#include <QtCharts/QChartView>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QPushButton>
#include <QLabel>
#include <QGroupBox>
#include <QSpinBox>
#include <QDoubleSpinBox>
#include <QTextEdit>
#include <QProgressBar>
#include <QMessageBox>

using namespace QtCharts;

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
    , ui(nullptr)
    , m_ctrl(new CylinderControl(this))
    , m_chart(nullptr)
    , m_axisX(nullptr)
    , m_axisY(nullptr)
    , m_chartMaxMs(900)
{
    // 手动构建 UI（不依赖 .ui 文件，确保可编译）
    auto *central = new QWidget(this);
    auto *mainLayout = new QHBoxLayout(central);

    // ===== 左侧：控制面板 =====
    auto *leftPanel = new QWidget;
    auto *leftLayout = new QVBoxLayout(leftPanel);
    leftLayout->setSpacing(8);

    // 标题
    auto *title = new QLabel(QStringLiteral("伊利雪糕三棒签同步插签控制系统"));
    title->setStyleSheet("font-size:16px;font-weight:bold;color:#1565C0;");
    leftLayout->addWidget(title);

    // 控制按钮
    auto *btnGroup = new QGroupBox(QStringLiteral("控制"));
    auto *btnLayout = new QHBoxLayout(btnGroup);
    auto *btnStart = new QPushButton(QStringLiteral("启动"));
    auto *btnStop  = new QPushButton(QStringLiteral("停止"));
    auto *btnReset = new QPushButton(QStringLiteral("复位"));
    auto *btnEstop = new QPushButton(QStringLiteral("急停"));
    btnStart->setStyleSheet("background:#4CAF50;color:white;font-weight:bold;");
    btnEstop->setStyleSheet("background:#F44336;color:white;font-weight:bold;");
    btnLayout->addWidget(btnStart);
    btnLayout->addWidget(btnStop);
    btnLayout->addWidget(btnReset);
    btnLayout->addWidget(btnEstop);
    leftLayout->addWidget(btnGroup);

    connect(btnStart, &QPushButton::clicked, this, &MainWindow::onStartClicked);
    connect(btnStop,  &QPushButton::clicked, this, &MainWindow::onStopClicked);
    connect(btnReset, &QPushButton::clicked, this, &MainWindow::onResetClicked);
    connect(btnEstop, &QPushButton::clicked, this, &MainWindow::onEmergencyStop);

    // 参数设置
    auto *paramGroup = new QGroupBox(QStringLiteral("参数设置（差异化延时补偿）"));
    auto *paramLayout = new QGridLayout(paramGroup);
    QDoubleSpinBox *spinDelay[3];
    QDoubleSpinBox *spinStroke[3];
    for (int i = 0; i < 3; ++i) {
        paramLayout->addWidget(new QLabel(QStringLiteral("气缸%1 行程(mm)").arg(i+1)), i*2, 0);
        spinStroke[i] = new QDoubleSpinBox;
        spinStroke[i]->setRange(10, 200); spinStroke[i]->setValue(m_ctrl->state(i).stroke);
        paramLayout->addWidget(spinStroke[i], i*2, 1);
        paramLayout->addWidget(new QLabel(QStringLiteral("气缸%1 延时(ms)").arg(i+1)), i*2+1, 0);
        spinDelay[i] = new QDoubleSpinBox;
        spinDelay[i]->setRange(0, 500); spinDelay[i]->setValue(m_ctrl->state(i).delayMs);
        paramLayout->addWidget(spinDelay[i], i*2+1, 1);
    }
    auto *btnApply = new QPushButton(QStringLiteral("应用参数"));
    paramLayout->addWidget(btnApply, 6, 0, 1, 2);
    leftLayout->addWidget(paramGroup);

    connect(btnApply, &QPushButton::clicked, this, [this, spinDelay, spinStroke]() {
        for (int i = 0; i < 3; ++i) {
            m_ctrl->setStroke(i, spinStroke[i]->value());
            m_ctrl->setDelay(i, spinDelay[i]->value());
        }
        appendLog(QStringLiteral("[参数] 已应用新的行程与延时参数"));
    });

    // 气缸状态
    auto *stateGroup = new QGroupBox(QStringLiteral("气缸实时状态"));
    auto *stateLayout = new QVBoxLayout(stateGroup);
    QLabel *lblPos[3], *lblStatus[3];
    QProgressBar *bar[3];
    for (int i = 0; i < 3; ++i) {
        auto *row = new QHBoxLayout;
        lblPos[i] = new QLabel(QStringLiteral("气缸%1: 0.0mm").arg(i+1));
        lblStatus[i] = new QLabel(QStringLiteral("待机"));
        lblStatus[i]->setStyleSheet("color:#888;");
        bar[i] = new QProgressBar;
        bar[i]->setRange(0, 100);
        row->addWidget(lblPos[i]);
        row->addWidget(lblStatus[i]);
        stateLayout->addLayout(row);
        stateLayout->addWidget(bar[i]);
    }
    leftLayout->addWidget(stateGroup);

    // 存储状态控件指针（用lambda捕获）
    connect(m_ctrl, &CylinderControl::stateUpdated, this, [this, lblPos, lblStatus, bar]() {
        for (int i = 0; i < 3; ++i) {
            const auto &s = m_ctrl->state(i);
            lblPos[i]->setText(QStringLiteral("气缸%1: %2mm").arg(i+1).arg(s.position, 0, 'f', 1));
            int pct = s.stroke > 0 ? int(s.position / s.stroke * 100) : 0;
            bar[i]->setValue(pct);
            if (s.overload) {
                lblStatus[i]->setText(QStringLiteral("过载"));
                lblStatus[i]->setStyleSheet("color:#F44336;font-weight:bold;");
            } else if (s.arrived) {
                lblStatus[i]->setText(QStringLiteral("到位"));
                lblStatus[i]->setStyleSheet("color:#4CAF50;font-weight:bold;");
            } else if (m_ctrl->isRunning()) {
                lblStatus[i]->setText(QStringLiteral("运行"));
                lblStatus[i]->setStyleSheet("color:#FF9800;");
            } else {
                lblStatus[i]->setText(QStringLiteral("待机"));
                lblStatus[i]->setStyleSheet("color:#888;");
            }
        }
        updateChart();
    });

    // 日志
    auto *logGroup = new QGroupBox(QStringLiteral("运行日志"));
    auto *logLayout = new QVBoxLayout(logGroup);
    auto *logEdit = new QTextEdit;
    logEdit->setReadOnly(true);
    logEdit->setMaximumHeight(120);
    logLayout->addWidget(logEdit);
    leftLayout->addWidget(logGroup);
    leftLayout->addStretch();

    connect(m_ctrl, &CylinderControl::logMessage, this, [logEdit](const QString &m) {
        logEdit->append(m);
    });
    connect(m_ctrl, &CylinderControl::allArrived, this, [this, logEdit](int spread) {
        QString msg = spread <= 15
            ? QStringLiteral("[结果] 同步性 PASS —— 到位时间差 %1ms，三根棒签同步精准插入").arg(spread)
            : QStringLiteral("[结果] 到位时间差 %1ms，需优化延时补偿").arg(spread);
        logEdit->append(msg);
        QMessageBox::information(this, QStringLiteral("插签完成"), msg);
    });

    // ===== 右侧：实时曲线 =====
    auto *rightPanel = new QWidget;
    auto *rightLayout = new QVBoxLayout(rightPanel);
    setupChart();
    auto *chartView = new QChartView(m_chart);
    chartView->setRenderHint(QPainter::Antialiasing);
    rightLayout->addWidget(chartView);

    mainLayout->addWidget(leftPanel, 1);
    mainLayout->addWidget(rightPanel, 2);
    setCentralWidget(central);
    resize(1100, 700);
    setWindowTitle(QStringLiteral("伊利雪糕三棒签同步插签控制系统 v1.0"));
}

MainWindow::~MainWindow() = default;

void MainWindow::setupChart()
{
    m_chart = new QChart;
    m_chart->setTitle(QStringLiteral("三气缸位置-时间曲线（差异化延时同步控制）"));
    m_chart->setAnimationOptions(QChart::NoAnimation);

    const char *colors[3] = {"#E53935", "#FB8C00", "#1E88E5"};
    for (int i = 0; i < 3; ++i) {
        m_series[i] = new QLineSeries;
        m_series[i]->setName(QStringLiteral("气缸%1 (行程%2mm)").arg(i+1).arg(m_ctrl->state(i).stroke, 0, 'f', 0));
        QPen pen(QColor(colors[i]));
        pen.setWidth(2);
        m_series[i]->setPen(pen);
        m_chart->addSeries(m_series[i]);
    }

    m_axisX = new QValueAxis;
    m_axisX->setTitleText(QStringLiteral("时间 (ms)"));
    m_axisX->setRange(0, m_chartMaxMs);
    m_axisY = new QValueAxis;
    m_axisY->setTitleText(QStringLiteral("位置 (mm)"));
    m_axisY->setRange(0, 70);

    m_chart->addAxis(m_axisX, Qt::AlignBottom);
    m_chart->addAxis(m_axisY, Qt::AlignLeft);
    for (int i = 0; i < 3; ++i) {
        m_series[i]->attachAxis(m_axisX);
        m_series[i]->attachAxis(m_axisY);
    }
}

void MainWindow::updateChart()
{
    if (!m_ctrl->isRunning() && m_ctrl->elapsedMs() == 0) return;
    int t = m_ctrl->elapsedMs();
    for (int i = 0; i < 3; ++i) {
        m_series[i]->append(t, m_ctrl->state(i).position);
    }
    if (t > m_chartMaxMs) {
        m_chartMaxMs = t + 100;
        m_axisX->setMax(m_chartMaxMs);
    }
}

void MainWindow::onStartClicked() { m_ctrl->start(); }
void MainWindow::onStopClicked()  { m_ctrl->stop(); }
void MainWindow::onResetClicked()
{
    m_ctrl->reset();
    for (int i = 0; i < 3; ++i) m_series[i]->clear();
    m_chartMaxMs = 900;
    m_axisX->setMax(900);
}
void MainWindow::onEmergencyStop() { m_ctrl->emergencyStop(); }
void MainWindow::onApplyParams() {}
void MainWindow::updateUI() {}
void MainWindow::onCylinderArrived(int) {}
void MainWindow::onAllArrived(int) {}
void MainWindow::onOverload(int) {}
void MainWindow::onSyncDeviation(double) {}
void MainWindow::appendLog(const QString &) {}
void MainWindow::loadParamsToUI() {}
