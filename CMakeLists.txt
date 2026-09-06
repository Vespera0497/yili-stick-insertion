cmake_minimum_required(VERSION 3.16)
project(StickInsertControl LANGUAGES C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

add_executable(stick_insert_control src/stick_insert_control.c)
