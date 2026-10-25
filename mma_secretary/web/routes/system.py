from __future__ import annotations

import json

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response

from mma_secretary.services.import_export import export_participants_xlsx, export_report_xlsx
from mma_secretary.web.deps import archives, svc
from mma_secretary.web.errors import bad_request

router = APIRouter()


@router.post("/api/undo")
def undo():
    try:
        return svc.undo()
    except Exception as e:
        bad_request(e)


@router.get("/api/export")
def export_json():
    payload = json.dumps(svc.export_bundle(), ensure_ascii=False, indent=2, default=str)
    return Response(
        payload,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=tournament.json"},
    )


@router.post("/api/import")
async def import_json(file: UploadFile = File(...)):
    data = json.loads(await file.read())
    svc.import_bundle(data)
    archives.set_current_id(None)
    return {"ok": True}


@router.get("/api/saves")
def list_saves():
    return archives.list()


@router.post("/api/saves")
def create_save(data: dict):
    return archives.save(data.get("name") or "")


@router.post("/api/saves/{sid}/load")
def load_save(sid: str):
    try:
        archives.load(sid)
        return {"ok": True}
    except Exception as e:
        bad_request(e)


@router.delete("/api/saves/{sid}")
def delete_save(sid: str):
    archives.delete(sid)
    return {"ok": True}


@router.post("/api/tournament/new")
def new_tournament():
    svc.reset_to_empty()
    archives.set_current_id(None)
    return {"ok": True}


@router.get("/api/export/participants.xlsx")
def x_parts():
    return Response(
        export_participants_xlsx(svc),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=participants.xlsx"},
    )


@router.get("/api/export/report.xlsx")
def x_rep():
    return Response(
        export_report_xlsx(svc),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=report.xlsx"},
    )
