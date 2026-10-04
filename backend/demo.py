"""
Run the whole flow from the terminal, no frontend needed.

    python demo.py sample_note.txt
    python demo.py sample_note.txt --ask "Summarize this for Margaret Ellison's daughter"

Without --ask it stops before Gemini (nothing leaves your computer).
"""
import argparse

import pipeline
from pipeline import rules, tagging

parser = argparse.ArgumentParser()
parser.add_argument("file")
parser.add_argument("--ask", help="question to send to Gemini (needs GEMINI_API_KEY)")
args = parser.parse_args()

text = open(args.file, encoding="utf-8").read()

# 1-4) detect, merge, risk
result = pipeline.analyze(text)
print(f"\nRISK: {result['risk']}\n")
print(f"{'id':>3}  {'level':6} {'type':11} {'found_by':15} text")
for s in result["spans"]:
    print(f"{s['id']:>3}  {s['level']:6} {s['type']:11} {'+'.join(s['found_by']):15} {s['text']!r}")

# 5) "review": in the app the clinician clicks; here we accept the defaults (RED = remove)
#    and also remove YELLOW ones, as if the clinician approved everything.
remove_ids = {s["id"] for s in result["spans"]}

# 6) tag
tagged, mapping = tagging.tag_text(text, result["spans"], remove_ids)
print("\n----- WHAT GEMINI WOULD RECEIVE -----\n" + tagged)
print("----- MAPPING (stays local) -----")
for tag, value in mapping.items():
    print(f"  {tag:16} -> {value}")

# 7-8) optional: ask Gemini, restore names
if args.ask:
    import gemini_client
    question = tagging.tag_question(args.ask, mapping)
    problem = rules.looks_unsafe(tagged + question)
    if problem:
        raise SystemExit(f"Blocked: {problem}")
    print(f"\nQuestion sent: {question}")
    answer = gemini_client.ask(tagged, [], question)
    print("\n----- GEMINI ANSWER (tagged) -----\n" + answer)
    print("\n----- WHAT THE CLINICIAN SEES -----\n" + tagging.restore(answer, mapping))
