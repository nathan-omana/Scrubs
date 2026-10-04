"""
Run the whole flow from the terminal, no frontend needed.

    python demo.py sample_note.txt
    python demo.py sample_note.txt --ask "Summarize this for the patient's daughter"

Without --ask it stops before Gemini (nothing leaves your computer).
"""
import argparse

import config
import pipeline
from pipeline import rules, tagging

parser = argparse.ArgumentParser()
parser.add_argument("file")
parser.add_argument("--ask", help="question to send to Gemini (needs GEMINI_API_KEY)")
args = parser.parse_args()

text = open(args.file, encoding="utf-8").read()

# 1) detect, merge, tiers
flags = pipeline.analyze(text)
pseudonyms = tagging.Pseudonyms()
for f in flags:
    f["pseudonym"] = pseudonyms.get(config.TYPES[f["type"]][2], f["text"])

print(f"\n{'flag':4}  {'tier':4} {'label':21} {'masked':6} {'source':8} {'found_by':20} text")
for f in flags:
    print(f"{f['flag_code']:4}  {f['tier'].upper():4} {f['label']:21} {str(f['masked']):6} {f['source']:8} "
          f"{'+'.join(f['found_by']):20} {f['text']!r}")

# 2) "review": accept the defaults (HIGH and MED masked, LOW kept), as if the clinician clicked Done
pseudonymized = tagging.pseudonymize(text, flags)
mapping = tagging.mapping_of(flags)
print("\n----- WHAT GEMINI WOULD RECEIVE -----\n" + pseudonymized)
print("----- MAPPING (stays local) -----")
for pseudonym, value in mapping.items():
    print(f"  {pseudonym:16} -> {value}")

# 3) optional: ask Gemini, restore names
if args.ask:
    import gemini_client
    question = tagging.tag_question(args.ask, mapping)
    problem = rules.looks_unsafe(pseudonymized + question)
    if problem:
        raise SystemExit(f"Blocked: {problem}")
    print(f"\nQuestion sent: {question}")
    answer = gemini_client.ask(pseudonymized, [], question)
    print("\n----- GEMINI ANSWER (pseudonyms) -----\n" + answer)
    print("\n----- WHAT THE CLINICIAN SEES -----\n" + tagging.restore(answer, mapping))
