"""
Tiny test runner shared by the test files (no pytest needed).

    if __name__ == "__main__":
        run(globals())

Runs every function whose name starts with test_, in file order, reports EVERY failure
(not just the first), and exits with code 1 if anything failed.
"""
import re
import sys
import traceback

import config
from pipeline import detector


class FakeGLiNER:
    """Pretends to be GLiNER: returns fixed phrases wherever they appear in the chunk."""

    def __init__(self, phrases: dict[str, str] | None = None):
        self.phrases = phrases or {}
        self.calls: list[str] = []        # every chunk it was asked to read

    def predict_entities(self, text, labels, threshold=0.5):
        self.calls.append(text)
        out = []
        for phrase, label in self.phrases.items():
            for m in re.finditer(re.escape(phrase), text):
                out.append({"start": m.start(), "end": m.end(), "text": phrase, "label": label, "score": 0.9})
        return out


def use_fake_gliner(phrases: dict[str, str] | None = None) -> FakeGLiNER:
    config.USE_GLINER = True
    detector._model = FakeGLiNER(phrases)
    return detector._model


def raises(exc_type, fn, *args, **kwargs) -> bool:
    try:
        fn(*args, **kwargs)
    except exc_type:
        return True
    return False


def run(namespace: dict) -> None:
    tests = [(name, fn) for name, fn in namespace.items() if name.startswith("test_") and callable(fn)]
    failed = []
    for name, fn in tests:
        try:
            fn()
        except Exception:
            failed.append(name)
            print(f"FAIL {name}\n{traceback.format_exc()}")
    module = namespace.get("__file__", "?").rsplit("/", 1)[-1]
    if failed:
        print(f"{module}: {len(failed)} of {len(tests)} failed: {', '.join(failed)}")
        sys.exit(1)
    print(f"{module}: all {len(tests)} passed")
