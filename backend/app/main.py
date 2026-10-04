"""Scrubs API (CLAUDE.md section 10).

Built so far: document creation from a PDF or pasted text, list, and get.
Detection (Presidio + our model), flags, finalize, mapping and chat are not built yet;
documents come back with an empty `flags` list until the pipeline lands.
Storage is in memory for now and will move to TiDB.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from .pdf import PdfError, ScannedPdfError, extract_text

app = FastAPI(title="Scrubs API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip() for o in os.getenv("FRONTEND_ORIGINS", "http://localhost:3000").split(",") if o.strip()
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Flag(BaseModel):
    flag_code: str
    start_idx: int
    end_idx: int
    text: str
    label: str
    tier: Literal["high", "med", "low"]
    reason: str
    masked: bool
    locked: bool
    pseudonym: str
    source: Literal["presidio", "model"]


class Document(BaseModel):
    id: str
    title: str
    source: Literal["pdf", "paste"]
    original_text: str
    pseudonymized_text: str | None = None
    status: Literal["needs_review", "ready"] = "needs_review"
    created_at: str
    page_count: int | None = None
    flags: list[Flag] = []


class PastedDocument(BaseModel):
    title: str = ""
    text: str


_documents: dict[str, Document] = {}


def _new_document(title: str, source: Literal["pdf", "paste"], text: str, page_count: int | None = None) -> Document:
    doc = Document(
        id=f"doc-{uuid.uuid4().hex[:12]}",
        title=title,
        source=source,
        original_text=text,
        created_at=datetime.now(timezone.utc).isoformat(),
        page_count=page_count,
    )
    _documents[doc.id] = doc
    return doc


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/documents", response_model=Document, status_code=201)
async def create_document(request: Request) -> Document:
    """Multipart with a `file` field (PDF), or JSON `{title, text}` for pasted notes."""
    content_type = request.headers.get("content-type", "")

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if upload is None or isinstance(upload, str):
            raise HTTPException(400, "Attach the PDF in a form field named 'file'.")
        data = await upload.read()
        try:
            text, pages = extract_text(data)
        except ScannedPdfError as exc:
            raise HTTPException(422, str(exc)) from exc
        except PdfError as exc:
            raise HTTPException(400, str(exc)) from exc
        name = upload.filename or "Uploaded PDF"
        title = name[:-4] if name.lower().endswith(".pdf") else name
        return _new_document(title, "pdf", text, pages)

    if content_type.startswith("application/json"):
        try:
            body = PastedDocument.model_validate(await request.json())
        except (ValidationError, ValueError) as exc:
            raise HTTPException(400, "Send JSON with a 'text' field.") from exc
        if not body.text.strip():
            raise HTTPException(400, "The note text is empty.")
        return _new_document(body.title.strip() or "Pasted note", "paste", body.text)

    raise HTTPException(415, "Send a PDF as multipart/form-data or pasted text as JSON.")


@app.get("/documents", response_model=list[Document])
def list_documents() -> list[Document]:
    return sorted(_documents.values(), key=lambda d: d.created_at, reverse=True)


@app.get("/documents/{doc_id}", response_model=Document)
def get_document(doc_id: str) -> Document:
    doc = _documents.get(doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found.")
    return doc
