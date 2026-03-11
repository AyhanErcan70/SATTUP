# RECOVERY

## Purpose
This file is a quick checklist to get the project running again after a fresh Windows install / crash / format.

## Prerequisites
- Python: 3.12.x (tested with 3.12.8)
- Git for Windows

## 1) Restore the repository
- Clone the repo or restore the project folder to the same path.
- Ensure large/binary project assets are present (e.g. `assets/`).

## 2) Create and use a virtual environment
From the project root:

```powershell
py -3.12 -m venv .venv

# (Optional) If PowerShell blocks activation scripts:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If you prefer to avoid activation, use the venv Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## 3) Known dependency pitfall (PyQt6 sip)
If you hit:

`ModuleNotFoundError: No module named 'PyQt6.sip'`

Make sure `requirements.txt` contains:
- `PyQt6-sip==...` (dash) and not `PyQt6_sip==...` (underscore).

## 4) Run the app

```powershell
.\.venv\Scripts\python.exe main.py
```

## 5) Licensing (after format)
The app stores the license file under:
- `%APPDATA%\SATTUP\.sys_config.bin`

After a format this file may be missing; the app may ask for the license again.

## 6) Database notes
Database files are ignored by Git (`*.db`). Keep an external backup of:
- `database\*.db`

If the DB is missing, the app may start with empty/seeded tables.

## 7) Git first-time setup (new machine)
If commit fails with "Author identity unknown":

```powershell
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

## 8) After recovery sanity check
- App starts without tracebacks
- Main modules open
- Data is present as expected
- `git status` is clean (except intentional changes)
