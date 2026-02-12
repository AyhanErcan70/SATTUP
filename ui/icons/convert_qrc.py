import os
import subprocess
import sys


def _venv_pyrcc5_path() -> str:
    scripts_dir = os.path.join(sys.prefix, "Scripts")
    exe = os.path.join(scripts_dir, "pyrcc5.exe")
    return exe


def _patch_pyqt5_to_pyqt6(py_file: str) -> None:
    with open(py_file, "r", encoding="utf-8") as f:
        content = f.read()

    if "from PyQt5 import QtCore" in content:
        content = content.replace("from PyQt5 import QtCore", "from PyQt6 import QtCore")
    if "from PyQt5 import QtGui" in content:
        content = content.replace("from PyQt5 import QtGui", "from PyQt6 import QtGui")
    if "from PyQt5 import QtWidgets" in content:
        content = content.replace("from PyQt5 import QtWidgets", "from PyQt6 import QtWidgets")

    with open(py_file, "w", encoding="utf-8") as f:
        f.write(content)


def convert_all_qrc_in_cwd() -> int:
    pyrcc5 = _venv_pyrcc5_path()
    if not os.path.exists(pyrcc5):
        print(f"pyrcc5.exe bulunamadı: {pyrcc5}")
        print("Çözüm: venv aktif mi? (sys.prefix Scripts kontrolü)")
        return 2

    qrc_files = [f for f in os.listdir(".") if f.lower().endswith(".qrc")]
    if not qrc_files:
        print("Bu klasörde .qrc bulunamadı.")
        return 0

    ok = True
    for qrc in sorted(qrc_files):
        out_file = os.path.splitext(qrc)[0] + "_rc.py"
        print(f"Converting {qrc} -> {out_file}")

        res = subprocess.run(
            [pyrcc5, qrc, "-o", out_file],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        if res.returncode != 0:
            ok = False
            print("pyrcc5 başarısız:")
            if res.stdout:
                print(res.stdout)
            if res.stderr:
                print(res.stderr)
            continue

        _patch_pyqt5_to_pyqt6(out_file)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(convert_all_qrc_in_cwd())