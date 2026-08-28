@echo off
:: Disable DailyWake (do not delete — v3 wrapper may be diagnosed later).
:: Run from an elevated prompt if schtasks returns Access is denied.
schtasks /change /tn "DailyWake" /disable
schtasks /query /tn "DailyWake" /fo list | findstr /i "Status Last"
