#!/usr/bin/env python3
"""Read-only freshness check of successful scheduled/manual/push runs."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--max-age-hours", type=float, default=72)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
repo = json.loads((root / "sources.json").read_text())["publish_repository"]
result = subprocess.run(["gh", "api", "repos/%s/actions/workflows/sync.yml/runs?branch=main&status=success&per_page=50" % repo],
                        capture_output=True, text=True, check=True)
runs = [run for run in json.loads(result.stdout)["workflow_runs"] if run["event"] in ("schedule", "push", "workflow_dispatch")]
if not runs:
    print("No successful publishing workflow run found")
    sys.exit(1)
latest = runs[0]
finished = datetime.datetime.fromisoformat(latest["updated_at"].replace("Z", "+00:00"))
age = (datetime.datetime.now(datetime.timezone.utc) - finished).total_seconds() / 3600
print(json.dumps({"last_success": latest["updated_at"], "age_hours": round(age, 2),
                  "url": latest["html_url"], "fresh": age <= args.max_age_hours}, indent=2))
sys.exit(0 if age <= args.max_age_hours else 1)
