"""
Run every test file, each in its own process (they change shared settings like config and
the fake GLiNER, so isolating them keeps results honest).

Run from the backend folder:   python -m tests.run_all
Add --model to also run the real GLiNER tests (slower, needs the model downloaded).
"""
import subprocess
import sys

FILES = ["test_smoke", "test_lexicon", "test_pdf", "test_api", "test_rules", "test_merge", "test_tagging",
         "test_detector", "test_privacy", "test_audit"]

if __name__ == "__main__":
    files = FILES + (["test_model"] if "--model" in sys.argv else [])
    failed = []
    for name in files:
        print(f"\n===== {name}")
        if subprocess.run([sys.executable, "-W", "ignore", "-m", f"tests.{name}"]).returncode != 0:
            failed.append(name)
    print("\n" + (f"FAILED: {', '.join(failed)}" if failed else f"ALL {len(files)} FILES PASSED"))
    sys.exit(1 if failed else 0)
