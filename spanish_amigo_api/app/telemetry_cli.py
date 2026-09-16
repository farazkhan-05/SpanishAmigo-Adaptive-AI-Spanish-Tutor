from __future__ import annotations
import argparse, json
from app.database import SessionLocal
from app.services.telemetry import prune, report
def main() -> None:
    parser = argparse.ArgumentParser(description="Local/admin AI telemetry reporting")
    parser.add_argument("--hours", type=int, default=24); parser.add_argument("--prune", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.prune: print(json.dumps({"pruned": prune(db)}, sort_keys=True))
        else:
            result = report(db, args.hours)
            print(json.dumps(result, sort_keys=True, default=str))
            if result["sample_count"] < 20:
                print("Percentiles are descriptive only for small samples (fewer than 20 events).")
if __name__ == "__main__": main()
