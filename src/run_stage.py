"""Run one pipeline configuration over the whole evaluation set.

Usage:  python src/run_stage.py --stage <baseline|context|verify|memory|judge|final>

Stages map onto the Improvement Changelog:
  baseline : one direct prompt with the schema (stage 0)
  context  : engineered extraction prompt, no tools        (iteration 1)
  verify   : + deterministic validator & correction loop   (iteration 2)
  memory   : + vendor memory                                (iteration 3)
  judge    : memory + second-opinion LLM judge              (iteration 4, removed)
  final    : alias of memory (the shipped configuration)
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import llm
from agent import run_agent, run_baseline
from memory import VendorMemory

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INVOICE_DIR = os.path.join(ROOT, "data", "invoices")

STAGES = {
    "baseline": {},
    "context": {"verify": False, "memory": False, "judge": False},
    "verify":  {"verify": True,  "memory": False, "judge": False},
    "memory":  {"verify": True,  "memory": True,  "judge": False},
    "judge":   {"verify": True,  "memory": True,  "judge": True},
    "final":   {"verify": True,  "memory": True,  "judge": False},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=sorted(STAGES))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out_dir = args.out or os.path.join(ROOT, "runs", args.stage)
    os.makedirs(out_dir, exist_ok=True)

    cfg = STAGES[args.stage]
    memory = None
    if cfg.get("memory"):
        mem_path = os.path.join(out_dir, "vendor_memory.json")
        if os.path.exists(mem_path):
            os.remove(mem_path)  # each run learns from scratch — no leakage between runs
        memory = VendorMemory(mem_path)

    invoices = sorted(f for f in os.listdir(INVOICE_DIR) if f.endswith(".txt"))
    llm.reset_call_count()
    t0 = time.time()

    for fname in invoices:
        inv_id = fname[:-4]
        with open(os.path.join(INVOICE_DIR, fname), encoding="utf-8") as f:
            document = f.read()
        print(f"[{args.stage}] {inv_id} ...", flush=True)

        if args.stage == "baseline":
            result, trajectory = run_baseline(document)
        else:
            result, trajectory = run_agent(
                document,
                verify=cfg["verify"],
                memory=memory,
                judge=cfg["judge"],
            )

        with open(os.path.join(out_dir, f"{inv_id}.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        with open(os.path.join(out_dir, f"trajectory_{inv_id}.jsonl"), "w", encoding="utf-8") as f:
            for event in trajectory:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")

    meta = {
        "stage": args.stage,
        "model": llm.DEFAULT_MODEL,
        "engine": llm.ENGINE,
        "invoices": len(invoices),
        "llm_calls": llm.call_count(),
        "wall_seconds": round(time.time() - t0, 1),
    }
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"[{args.stage}] done: {meta}", flush=True)


if __name__ == "__main__":
    main()
