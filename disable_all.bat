@echo off
cd /d C:\BlinkDVR
call venv\Scripts\activate
python arm_control.py disable "Outdoor 4 - front"
python arm_control.py disable "Outdoor 4 - back door"
python arm_control.py disable "Outdoor 4 - car"
python arm_control.py disable "Mini - white"
python arm_control.py disable "Mini - black"
python arm_control.py status
pause
