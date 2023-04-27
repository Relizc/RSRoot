:start
@echo off
java -Xms1024M -Xmx1024M -jar server.jar -nogui -o true
pause
goto start