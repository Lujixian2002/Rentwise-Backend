import csv
from pathlib import Path


def read_zori_rows(path: str = "data/zori.csv") -> list[dict[str, str]]:
    csv_path = Path(path)
    if not csv_path.exists():
        return []

    with csv_path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))
