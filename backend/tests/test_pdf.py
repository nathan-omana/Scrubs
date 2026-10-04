import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.pdf import PdfError, ScannedPdfError, clean_text, extract_text

from .pdf_factory import build_pdf
from .samples import DEMO_NOTE, DEMO_PAGES

client = TestClient(app)


def test_extracts_demo_note_with_wrapped_lines_rejoined():
    text, pages = extract_text(build_pdf(DEMO_PAGES))
    assert pages == 1
    assert text.startswith("Hope Family Clinic\nVisit note\nDate: Sept 28\nClinician: Dr. Amrit Singh")
    # The paragraph wraps over several lines in the PDF; detection needs it as one run of text.
    assert DEMO_NOTE in text


def test_multiple_pages_are_separated_by_a_blank_line():
    text, pages = extract_text(build_pdf([["Page one text here."], ["Page two text here."]]))
    assert pages == 2
    assert text == "Page one text here.\n\nPage two text here."


def test_small_print_without_space_characters_keeps_words_apart():
    # Like an invoice at 7.2pt: the 2pt word gap is under pdfplumber's fixed 3pt default.
    lines = ["Felix Kongyuy / Good Fridays", "14653 107A Ave", "SURREY BC V3R 1V2"]
    text, _ = extract_text(build_pdf([lines], font_size=7.2, spaceless=True))
    for line in lines:
        assert line in text


def test_side_by_side_columns_are_split_with_a_tab():
    lines = ["Invoice Number   VANCOUVER BRITISH", "INV-0184   COLUMBIA V6B 0P9"]
    text, _ = extract_text(build_pdf([lines], font_size=7.2, spaceless=True))
    assert text == "Invoice Number\tVANCOUVER BRITISH\nINV-0184\tCOLUMBIA V6B 0P9"


def test_scanned_pdf_without_text_is_rejected():
    with pytest.raises(ScannedPdfError):
        extract_text(build_pdf([[]]))


@pytest.mark.parametrize("data", [b"hello, not a pdf", b"%PDF-1.4\ngarbage that is not a pdf"])
def test_bad_files_raise_pdf_error(data):
    with pytest.raises(PdfError):
        extract_text(data)


def test_clean_text_keeps_list_items_and_labels_on_their_own_lines():
    page = (
        "Discharge medications: apixaban and amoxicillin given as listed in the table below for\n"
        "the patient\n"
        "- Apixaban 2.5 mg PO BID\n"
        "- Amoxicillin 500 mg PO TID\n"
        "Phone: 604-555-0182\n"
        "Follow-\n"
        "up in 2 weeks."
    )
    assert clean_text([page]) == (
        "Discharge medications: apixaban and amoxicillin given as listed in the table below for the patient\n"
        "- Apixaban 2.5 mg PO BID\n"
        "- Amoxicillin 500 mg PO TID\n"
        "Phone: 604-555-0182\n"
        "Follow-up in 2 weeks."
    )


def test_clean_text_fixes_ligatures_and_odd_spaces():
    assert clean_text(["atrial ﬁbrillation noted"]) == "atrial fibrillation noted"


def test_post_pdf_creates_document():
    res = client.post(
        "/documents",
        files={"file": ("Visit note.pdf", build_pdf(DEMO_PAGES), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    doc = res.json()
    assert doc["title"] == "Visit note"
    assert doc["source"] == "pdf"
    assert doc["status"] == "needs_review"
    assert doc["page_count"] == 1
    assert DEMO_NOTE in doc["original_text"]
    assert client.get(f"/documents/{doc['id']}").json() == doc


def test_post_scanned_pdf_returns_422_with_message():
    res = client.post("/documents", files={"file": ("scan.pdf", build_pdf([[]]), "application/pdf")})
    assert res.status_code == 422
    assert "scanned" in res.json()["detail"]


def test_post_non_pdf_returns_400():
    res = client.post("/documents", files={"file": ("notes.pdf", b"plain text", "application/pdf")})
    assert res.status_code == 400


def test_post_pasted_text_creates_document():
    res = client.post("/documents", json={"title": "", "text": DEMO_NOTE})
    assert res.status_code == 201
    doc = res.json()
    assert doc["title"] == "Pasted note"
    assert doc["source"] == "paste"
    assert doc["original_text"] == DEMO_NOTE


def test_post_empty_paste_returns_400():
    assert client.post("/documents", json={"text": "   "}).status_code == 400
