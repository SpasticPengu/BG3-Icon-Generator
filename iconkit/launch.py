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
    stopped = False
    while True:
        p = subprocess.Popen([sys.executable, "-m", "iconkit.editor", *args], cwd=ROOT)
        while True:
            try:
                code = p.wait()
                break
            except KeyboardInterrupt:                  # the editor gets the Ctrl+C too and stops by itself
                stopped = True
        if code not in (0, 75) and not stopped:        # an error: keep the window open so the message can be read
            input("\nThe editor stopped because of an error; see the messages above. Press Enter to close this window.")
        if code != 75:
            return code
        if subprocess.call([str(UV), "pip", "sync", "requirements.lock", "--python", sys.executable, "--require-hashes", "--quiet"], cwd=ROOT):
            input("\nInstalling the packages required by the update failed; see the messages above. Press Enter to close this "
                  "window, then run Start.bat again.")
            return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
