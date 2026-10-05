# macOS build of Scrambled Echo with DPF's own makefiles (the Windows build is ../build.py).
#   make -C plugin/mac        ->  plugin/dist/mac/ScrambledEcho.vst3
# Universal (x86_64 + arm64): pass CFLAGS/CXXFLAGS/LDFLAGS with "-arch x86_64 -arch arm64", as the CI workflow does.

NAME = ScrambledEcho
FILES_DSP = ../src/ScrambledEchoPlugin.cpp
FILES_UI = $(filter-out $(FILES_DSP),$(wildcard ../src/*.cpp))

DPF_BUILD_DIR = ../build/mac
DPF_TARGET_DIR = ../dist/mac
UI_TYPE = opengl
USE_FILE_BROWSER = true

include ../third_party/DPF/Makefile.plugins.mk

BUILD_CXX_FLAGS += -std=gnu++17 -I../src

TARGETS += vst3

all: $(TARGETS)
