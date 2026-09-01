import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_v3_demo_catalog_is_owned_complete_and_commercially_unambiguous() -> None:
    path = ROOT / "data/demo/catalog.v3.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert len(rows) == 60
    assert {row["category"] for row in rows} == {"手机", "电脑", "耳机", "相机"}
    assert len({row["product_id"] for row in rows}) == 60
    assert len({row["offer"]["offer_id"] for row in rows}) == 60
    assert all(row["offer"]["verification"] == "DEMO_FIXTURE" for row in rows)
    assert all(row["evidence_refs"] for row in rows)
    assert all(row["license_status"] == "project_authored_demo_only" for row in rows)
    assert all((ROOT / "data/demo" / row["image_ref"]).is_file() for row in rows)
    assert not any("apps/backend" in json.dumps(row) for row in rows)
