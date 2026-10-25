from __future__ import annotations

import json

from fastapi import APIRouter, File, UploadFile

from mma_secretary.paths import gold_fixture
from mma_secretary.services.import_export import import_xlsx
from mma_secretary.web.deps import svc
from mma_secretary.web.errors import bad_request

router = APIRouter()


@router.get("/api/participants")
def get_parts(sort: str = "seq"):
    return svc.list_participants(sort)


@router.post("/api/participants")
def post_part(data: dict):
    try:
        return svc.add_participant(data)
    except Exception as e:
        bad_request(e)


@router.put("/api/participants/{pid}")
def put_part(pid: int, data: dict):
    try:
        return svc.update_participant(pid, data)
    except Exception as e:
        bad_request(e)


@router.delete("/api/participants/{pid}")
def del_part(pid: int):
    svc.delete_participant(pid)
    return {"ok": True}


@router.post("/api/participants/{pid}/weigh")
def weigh(pid: int, data: dict):
    try:
        return svc.weigh_in(
            pid,
            data.get("weight"),
            data.get("status"),
            declared_weight=data.get("declared_weight"),
            update_declared="declared_weight" in data,
        )
    except Exception as e:
        bad_request(e)


@router.get("/api/participants/{pid}/weights")
def hist(pid: int):
    return svc.weight_history(pid)


@router.post("/api/participants/import")
async def import_parts(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        return import_xlsx(svc, raw)
    except Exception as e:
        bad_request(e)


@router.post("/api/demo")
def demo():
    """Загрузить 14 участников из эталонного файла 14.09.2024."""
    gold = gold_fixture()
    data = json.loads(gold.read_text(encoding="utf-8"))
    svc.seed_defaults()
    existing = {p["name"] for p in svc.list_participants()}
    for p in data["participants"]:
        if p["name"] in existing:
            continue
        svc.add_participant(
            {
                "seq": p["n"],
                "draw_number": p["draw"],
                "name": p["name"],
                "organization": p["org"],
                "rank": p["rank"],
                "birth_year": p["year"],
                "coach": p["coach"],
                "declared_weight": p["weight"],
            }
        )
    return {"ok": True, "n": len(svc.list_participants())}
