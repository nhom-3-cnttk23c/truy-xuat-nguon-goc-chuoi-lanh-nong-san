import csv
import json
import sys
from pathlib import Path

source = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
out = Path(sys.argv[2])
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    writer.writerow(
        [
            "key",
            "parent",
            "sprint",
            "type",
            "title",
            "jiraStatus",
            "acceptanceCriteria",
            "nonFunctionalRequirements",
            "codeEvidence",
            "acceptanceLimit",
        ]
    )
    for row in source["rows"]:
        writer.writerow(
            [
                row.get(k, "")
                for k in [
                    "key",
                    "parent",
                    "sprint",
                    "type",
                    "title",
                    "jiraStatus",
                    "acceptanceCriteria",
                    "nonFunctionalRequirements",
                    "evidence",
                ]
            ]
            + [
                "Snapshot Jira 12/10/2026; bằng chứng local theo nhóm, chưa nghiệm thu toàn bộ AC trên staging. Xem docs/ACCEPTANCE.md."
            ]
        )
print(f"Exported {len(source['rows'])} items")
