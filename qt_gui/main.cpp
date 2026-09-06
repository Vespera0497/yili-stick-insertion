#include <QApplication>
#include "mainwindow.h"

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("StickInsertGUI"));
    app.setOrganizationName(QStringLiteral("MengChen"));

    MainWindow w;
    w.show();
    return app.exec();
}
