# CMake toolchain file for Raspberry Pi 3 B+ (aarch64 / armhf)
#
# Usage:
#   cmake -B build/pi3 -S cpp \
#     -DCMAKE_TOOLCHAIN_FILE=cpp/cmake/pi3-toolchain.cmake \
#     -DCMAKE_PREFIX_PATH=/path/to/qt6-pi-sysroot \
#     -DTUNER_BUILD_APP=ON
#
# Prerequisites:
#   - Cross-compiler: aarch64-linux-gnu-g++ (or arm-linux-gnueabihf-g++ for 32-bit)
#   - Qt 6 cross-compiled for Pi with EGLFS backend
#   - Pi sysroot at SYSROOT_PATH

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

# Cross-compiler — adjust if using a different toolchain.
set(CMAKE_C_COMPILER   aarch64-linux-gnu-gcc)
set(CMAKE_CXX_COMPILER aarch64-linux-gnu-g++)

# Sysroot — set to your Pi's root filesystem copy.
# Example: set(CMAKE_SYSROOT /opt/pi-sysroot)
# set(CMAKE_SYSROOT "/opt/pi-sysroot")

# Search paths — only search the sysroot for libraries/headers.
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

# Pi 3 B+ specific: Cortex-A53 with NEON.
set(CMAKE_C_FLAGS   "${CMAKE_C_FLAGS}   -mcpu=cortex-a53 -mfpu=neon-fp-armv8" CACHE STRING "")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -mcpu=cortex-a53 -mfpu=neon-fp-armv8" CACHE STRING "")

# EGLFS is the preferred Qt platform plugin for Pi (no X11 needed).
# Set QT_QPA_PLATFORM=eglfs at runtime, or pass -platform eglfs.
