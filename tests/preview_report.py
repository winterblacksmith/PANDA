"""Generate a synthetic report for PDF layout QA, optionally with real Ollama."""
import argparse
from pathlib import Path
import ollama
from conversation_report import generate_report

parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
parser.add_argument("--live-model", action="store_true")
args = parser.parse_args()
messages = [
    {"role": "user", "content": "For this demonstration, show forest stands older than 60 and explain the result."},
    {"role": "assistant", "results": [{
        "type": "fvs_query", "question": "Show stands older than 60",
        "content": "This synthetic test dataset contains 12 matching stands covering 450 acres. "
                   "The average recorded age is 72 years. A map was requested but no map image is attached.",
        "verified_summary": "Synthetic QA fixture: 12 stands; 450 acres; mean age 72 years.",
        "spec": {"min_age": 60, "make_map": True}, "data_backend": "SQLite",
        "sql_query": "SELECT * FROM sample_stands WHERE Age > ?", "sql_parameters": [60],
    }]},
    {"role": "user", "content": "Does that prove the entire region is old forest?"},
    {"role": "assistant", "content": "No. These figures describe only the filtered sample. "
        "We have not compared its acreage with the full region, and stand age does not prove old-growth status."},
    {"role": "user", "content": "Explain how the map is linked to the table. Also test symbols: <Acres> & MU_ID, 30° and m²."},
    {"role": "assistant", "content": "MU_ID links each stand to its polygon. TM_Value links the stand to TreeMap raster values. "
        "A repeated TreeMap identifier is not a unique stand boundary."},
]
client = ollama.Client(host="http://127.0.0.1:11434", timeout=180)
def chat(model, prompt, options):
    if not args.live_model:
        return "QA SUMMARY (synthetic): The example discussed 12 stands older than 60, totaling 450 acres. " \
               "It clarified the limits of the filtered sample and the spatial join identifiers."
    return client.chat(model=model, messages=[{"role": "user", "content": prompt}], options=options)["message"]["content"]
report = generate_report(messages, "synthetic-forest-example.csv", "Example conversation - synthetic QA data",
                         "qwen2.5:3b", chat)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_bytes(report.pdf)
print(f"Generated {len(report.pdf)} PDF bytes; live_model={args.live_model}; ai_summary={report.ai_generated}")
if args.live_model and not report.ai_generated:
    raise SystemExit("Live model summary failed")
