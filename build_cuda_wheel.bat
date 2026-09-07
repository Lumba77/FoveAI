@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"

set CMAKE_ARGS=-DGGML_CUDA=on
set LLAMA_CUBLAS=1
set CMAKE_GENERATOR=NMake Makefiles
set CMAKE_CUDA_ARCHITECTURES=89
set CMAKE_BUILD_PARALLEL_LEVEL=12

C:\Users\danie\program\LUMAX\FoveAI\.venv\Scripts\python.exe -m pip install llama-cpp-python==0.3.34 --force-reinstall --no-deps --no-binary :all: -v
