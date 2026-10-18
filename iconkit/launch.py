"""Start.bat's last step (D48): run the editor, and run it again after it installed an update (exit code 75), with the
libraries first brought in line with the new requirements.lock. Here, not in the batch: cmd asks "Terminate batch job
(Y/N)?" on Ctrl+C while a batch runs, even with nothing left to do (user 2026-10-19), so Start.bat hands the console
to this (start /b) and ends at once."""
import ctypes, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UV = Path(sys.prefix).parent / "uv" / "uv.exe"          # .runtime\env -> .runtime\uv


def main(args):
    ctypes.windll.kernel32.SetConsoleCtrlHandler(None, False)   # start /b turns Ctrl+C off; on again (the editor inherits it)
    while True:
        p = subprocess.Popen([sys.executable, "-m", "iconkit.editor", *args], cwd=ROOT)
        while True:
            try:
                code = p.wait()
                break
            except KeyboardInterrupt:                  # the editor gets the Ctrl+C too and stops by itself
                pass
        if code != 75:
            return code
        if subprocess.call([str(UV), "pip", "sync", "requirements.lock", "--python", sys.executable, "--require-hashes", "--quiet"], cwd=ROOT):
            input("\nUpdating the libraries failed (see above). Press Enter to close, then start again.")
            return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
