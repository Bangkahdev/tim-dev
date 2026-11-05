@echo off
where godot >nul 2>nul
if errorlevel 1 (
  echo Godot 4.x was not found in PATH. Install Godot 4.3+ and run this script again.
  pause
  exit /b 1
)
godot --path "%~dp0godot"
