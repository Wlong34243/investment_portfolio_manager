# Decision Capture v1 — Ingest path for Cowork proposal drop files
#
# Drop contract:
#   - Cowork writes decision-proposals-YYYY-MM-DD.json to the Studio artifacts dir
#     (config.SPOTIFY_STUDIO_TRANSCRIPTS_DIR) — same folder as AI dispatch / Spotify digests.
#   - JSON array of decision records matching core/decisions/schema.py field names exactly.
#   - The emitting Cowork task NEVER writes this repo directly.
#
# Reads:
#   - config.SPOTIFY_STUDIO_TRANSCRIPTS_DIR/decision-proposals-YYYY-MM-DD.json
#   - data/decision_proposals/.ingested.json (sha256 ledger)
# Writes (only with --live):
#   - data/decision_proposals/<id>.json  (QUARANTINE — model may write here via ingest)
#
# Ingest forces status: proposed and provenance: extracted on every record.
# A file with any invalid record is rejected whole.

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from core.decisions.schema import DecisionRecord
from core.decisions.store import write_proposal
from core.decisions.validate import validate

REPO_ROOT = Path(__file__).resolve().parents[1]
PROPOSALS_DIR = REPO_ROOT / "data" / "decision_proposals"
LEDGER_PATH = PROPOSALS_DIR / ".ingested.json"

FILENAME_RE = re.compile(r"^decision-proposals-(\d{4}-\d{2}-\d{2})\.json$")


def _load_ledger() -> dict:
    if not LEDGER_PATH.exists():
        return {}
    try:
        return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: could not read ledger ({e}); treating as empty")
        return {}


def _save_ledger(ledger: dict) -> None:
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


def _validate_file_records(raw_list: list) -> tuple[list[DecisionRecord], list[str]]:
    if not isinstance(raw_list, list):
        return [], ["drop file must be a JSON array"]
    records: list[DecisionRecord] = []
    all_errors: list[str] = []
    for i, item in enumerate(raw_list):
        if not isinstance(item, dict):
            all_errors.append(f"record[{i}] is not an object")
            continue
        item = dict(item)
        item["status"] = "proposed"
        item["provenance"] = "extracted"
        try:
            rec = DecisionRecord.from_dict(item)
        except KeyError as e:
            all_errors.append(f"record[{i}] missing field: {e}")
            continue
        errs = validate(rec, target="ingest")
        if errs:
            all_errors.extend([f"record[{i}] {e}" for e in errs])
        else:
            records.append(rec)
    if all_errors:
        return [], all_errors
    return records, []


def ingest_file(src: Path, *, live: bool = False) -> dict:
    raw_bytes = src.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    ledger = _load_ledger()
    if sha256 in ledger:
        return {"skipped": True, "sha256": sha256, "file": src.name}

    try:
        raw_list = json.loads(raw_bytes.decode("utf-8"))
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"invalid JSON: {e}", "file": src.name}

    records, errors = _validate_file_records(raw_list)
    if errors:
        print(f"REJECTED whole file {src.name}:")
        for e in errors:
            print(f"  - {e}")
        return {"ok": False, "rejected": True, "errors": errors, "file": src.name}

    if not live:
        print(f"DRY RUN: would ingest {len(records)} record(s) from {src.name}")
        for rec in records:
            print(f"  -> data/decision_proposals/{rec.id}.json")
        return {"ok": True, "dry_run": True, "count": len(records), "file": src.name}

    for rec in records:
        out = write_proposal(rec, live=True)
        if not out.get("ok"):
            return {"ok": False, "error": out, "file": src.name}

    ledger[sha256] = {
        "source_file": src.name,
        "ingested_at": datetime.now().isoformat(),
        "record_ids": [r.id for r in records],
    }
    _save_ledger(ledger)
    print(f"SUCCESS: ingested {len(records)} record(s) from {src.name}")
    return {"ok": True, "ingested": len(records), "file": src.name, "sha256": sha256}


def main(days: int | None = None, live: bool = False) -> dict:
    result = {"ingested": [], "skipped": [], "rejected": [], "failed": []}
    studio_dir = Path(config.SPOTIFY_STUDIO_TRANSCRIPTS_DIR)
    if not studio_dir.exists():
        print(f"Studio directory not found: {studio_dir}")
        return result

    window = days if days is not None else getattr(config, "SPOTIFY_DIGEST_WINDOW_DAYS", 7)
    cutoff = (datetime.now() - timedelta(days=window)).date()
    sources = sorted(studio_dir.glob("decision-proposals-*.json"))
    if not sources:
        print(f"No decision-proposals-*.json in {studio_dir}")
        return result

    for src in sources:
        m = FILENAME_RE.match(src.name)
        if not m:
            print(f"SKIP (unparseable name): {src.name}")
            result["failed"].append(src.name)
            continue
        try:
            file_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            result["failed"].append(src.name)
            continue
        if file_date < cutoff:
            continue

        out = ingest_file(src, live=live)
        if out.get("skipped"):
            result["skipped"].append(src.name)
            print(f"SKIP (sha256 in ledger): {src.name}")
        elif out.get("rejected"):
            result["rejected"].append(src.name)
        elif out.get("ok"):
            result["ingested"].append(src.name)
        else:
            result["failed"].append(src.name)

    print(
        f"\n=== Decision Proposals Summary ({'LIVE' if live else 'DRY RUN'}) ===\n"
        f"  Ingested: {result['ingested'] or 'None'}\n"
        f"  Skipped: {result['skipped'] or 'None'}\n"
        f"  Rejected: {result['rejected'] or 'None'}\n"
        f"  Failed: {result['failed'] or 'None'}"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Cowork decision proposal drop files")
    parser.add_argument("--days", type=int, default=None, help="Window in days")
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Ingest a single drop file (validation + ledger only; still cannot write vault/)",
    )
    parser.add_argument("--live", action="store_true", help="Write files. Default: DRY RUN.")
    args = parser.parse_args()
    if args.file is not None:
        out = ingest_file(args.file.resolve(), live=args.live)
        raise SystemExit(0 if out.get("ok") or out.get("skipped") else 1)
    main(days=args.days, live=args.live)
