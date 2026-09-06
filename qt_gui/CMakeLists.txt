cmake_minimum_required(VERSION 3.16)
project(StickInsertGUI VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

find_package(Qt6 REQUIRED COMPONENTS Widgets Charts SerialPort)

qt_add_executable(StickInsertGUI
    main.cpp
    mainwindow.cpp
    mainwindow.h
    mainwindow.ui
    cylindercontrol.h
    cylindercontrol.cpp
)

target_link_libraries(StickInsertGUI PRIVATE
    Qt6::Widgets
    Qt6::Charts
    Qt6::SerialPort
)
