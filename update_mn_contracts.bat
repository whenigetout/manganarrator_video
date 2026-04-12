@echo off
setlocal
call conda activate manganarrator-video
pip install git+https://github.com/whenigetout/manganarrator_contracts.git#subdirectory=python
endlocal
