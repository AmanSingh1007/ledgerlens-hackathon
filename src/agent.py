"""The LedgerLens agent pipeline.

extract -> validate (deterministic) -> correct (up to N retries)
        -> optional judge -> vendor-memory update -> human-review flag

Every step is recorded in a trajectory so a reviewer can follow exactly
what the agent saw, what its tools answered, and why it retried.
"""

import json

from llm import complete, extract_json
from prompts import BASELINE_PROMPT, CORRECTION_PROMPT, EXTRACT_PROMPT, JUDGE_PROMPT, SCHEMA
from validator import validate

MAX_CORRECTIONS = 2


def run_baseline(document: str):
    """Stage 0: one direct prompt. No tools, no retries, no memory."""
    trajectory = []
    prompt = BASELINE_PROMPT.format(schema=SCHEMA, document=document)
    trajectory.append({"step": "prompt", "role": "extractor", "content": prompt})
    reply = complete(prompt)
    trajectory.append({"step": "response", "role": "extractor", "content": reply})
    try:
        result = extract_json(reply)
    except Exception as e:
        trajectory.append({"step": "error", "content": f"unparseable reply: {e}"})
        result = {}
    return result, trajectory


def run_agent(document: str, verify=True, memory=None, judge=False):
    trajectory = []

    # 1. Vendor memory lookup (fuzzy match on the document header).
    memory_hints = ""
    profile = None
    if memory is not None:
        profile = memory.lookup(document)
        if profile:
            memory_hints = "\n" + memory.hints_for(profile) + "\n"
            trajectory.append({"step": "memory_read", "content": profile})
        else:
            trajectory.append({"step": "memory_read", "content": None})

    # 2. Extraction with engineered context.
    prompt = EXTRACT_PROMPT.format(schema=SCHEMA, document=document, memory_hints=memory_hints)
    trajectory.append({"step": "prompt", "role": "extractor", "content": prompt})
    reply = complete(prompt)
    trajectory.append({"step": "response", "role": "extractor", "content": reply})
    try:
        result = extract_json(reply)
    except Exception as e:
        trajectory.append({"step": "error", "content": f"unparseable reply: {e}"})
        result = {}

    # 3. Deterministic verification + correction loop.
    errors = []
    if verify:
        errors = validate(result)
        trajectory.append({"step": "validation", "errors": errors})
        attempts = 0
        while errors and attempts < MAX_CORRECTIONS:
            attempts += 1
            cprompt = CORRECTION_PROMPT.format(
                document=document,
                previous=json.dumps(result, indent=2),
                errors="\n".join(f"- {e}" for e in errors),
            )
            trajectory.append({"step": "prompt", "role": "corrector", "attempt": attempts, "content": cprompt})
            reply = complete(cprompt)
            trajectory.append({"step": "response", "role": "corrector", "attempt": attempts, "content": reply})
            try:
                result = extract_json(reply)
            except Exception as e:
                trajectory.append({"step": "error", "content": f"unparseable correction: {e}"})
                continue
            errors = validate(result)
            trajectory.append({"step": "validation", "attempt": attempts, "errors": errors})

    # 4. Optional second-opinion judge (the experiment we later removed).
    if judge and result:
        jprompt = JUDGE_PROMPT.format(document=document, extraction=json.dumps(result, indent=2))
        trajectory.append({"step": "prompt", "role": "judge", "content": jprompt})
        reply = complete(jprompt)
        trajectory.append({"step": "response", "role": "judge", "content": reply})
        try:
            verdict = extract_json(reply)
            if verdict.get("verdict") == "revise" and isinstance(verdict.get("revised"), dict):
                revised = verdict["revised"]
                revised_errors = validate(revised)
                if not revised_errors:
                    result = revised
                    errors = []
                    trajectory.append({"step": "judge_applied", "content": "revision accepted (passes validator)"})
                else:
                    trajectory.append({"step": "judge_rejected",
                                       "content": f"revision failed validator: {revised_errors}"})
        except Exception as e:
            trajectory.append({"step": "error", "content": f"unparseable judge reply: {e}"})

    # 5. Human-review flag: anything the loop could not reconcile goes to a person.
    result = dict(result) if isinstance(result, dict) else {}
    if errors:
        result["needs_human_review"] = True
        result["review_reasons"] = errors
        trajectory.append({"step": "human_review_flag", "errors": errors})

    # 6. Vendor memory write (validated extractions only).
    if memory is not None and result and not errors:
        memory.update(result, document)
        trajectory.append({"step": "memory_write", "vendor": result.get("vendor_name")})

    return result, trajectory
