:start
@echo off
java -Xms1024M -Xmx1024M -jar server.jar -o true
rmdir "plugins/Citizens" /s /q