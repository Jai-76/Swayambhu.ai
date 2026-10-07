from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse

from app.schemas.file import GeneratedFileOut
from app.services.generated_file_store import generated_file_store

router = APIRouter(tags=["files"])


@router.get("/files", response_model=list[GeneratedFileOut], response_model_exclude_none=True)
def list_files() -> list[GeneratedFileOut]:
    return [GeneratedFileOut(**asdict(f)) for f in generated_file_store.list_all()]


@router.get("/files/{file_id}")
def download_file(file_id: str):
    record = generated_file_store.get(file_id)
    if not record:
        raise HTTPException(404, "File nahi mila")
    path = generated_file_store.path_for(file_id)
    if not path or not path.exists():
        raise HTTPException(404, "File nahi mili")
    return FileResponse(path, filename=record.name)


@router.delete("/files/{file_id}", status_code=204)
def delete_file(file_id: str) -> Response:
    if not generated_file_store.delete(file_id):
        raise HTTPException(404, "File nahi mili")
    return Response(status_code=204)
