@echo off
SET venv_path=venv\Scripts\activate
IF EXIST %venv_path% (
    call %venv_path%
    echo Virtual environment activated.
) ELSE (
    echo Virtual environment not found. Please create it first.
)
