# Portable build for a single generated PicoWave program.
#
# The Python pipeline compiles generated files automatically via gcc; this
# CMake file is provided so a generated file can also be built by hand on
# Linux or Windows, against either the offline mock SDK or the real PicoSDK.
#
# Usage (offline mock):
#   cmake -B build-cmake -DGEN_SOURCE=generated/acquisition_001.c -DUSE_MOCK=ON
#   cmake --build build-cmake
#
# Usage (real PicoSDK):
#   cmake -B build-cmake -DGEN_SOURCE=generated/acquisition_001.c -DUSE_MOCK=OFF
#   cmake --build build-cmake
cmake_minimum_required(VERSION 3.16)
project(picowave_generated C)

set(CMAKE_C_STANDARD 99)

option(USE_MOCK "Link the offline mock ps2000 shim instead of the real driver" ON)
set(GEN_SOURCE "" CACHE FILEPATH "Path to the generated .c file to build")
set(PICO_INCLUDE "/opt/picoscope/include" CACHE PATH "Real PicoSDK include dir")
set(PICO_LIB     "/opt/picoscope/lib"     CACHE PATH "Real PicoSDK library dir")

if(NOT GEN_SOURCE)
    message(FATAL_ERROR "Set -DGEN_SOURCE=generated/acquisition_XXX.c")
endif()

get_filename_component(GEN_NAME "${GEN_SOURCE}" NAME_WE)

if(USE_MOCK)
    add_executable(${GEN_NAME} "${GEN_SOURCE}" "${CMAKE_SOURCE_DIR}/mock/ps2000_mock.c")
    target_include_directories(${GEN_NAME} PRIVATE "${CMAKE_SOURCE_DIR}/mock")
else()
    add_executable(${GEN_NAME} "${GEN_SOURCE}")
    target_include_directories(${GEN_NAME} PRIVATE "${PICO_INCLUDE}")
    target_link_directories(${GEN_NAME} PRIVATE "${PICO_LIB}")
    target_link_libraries(${GEN_NAME} PRIVATE ps2000)
endif()

if(UNIX)
    target_link_libraries(${GEN_NAME} PRIVATE m)
endif()
