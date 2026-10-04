"""
PDF extraction checks (pipeline/pdf.py). Test PDFs are built in memory by pdf_factory.py,
so no files and no GLiNER download are needed.
Run from the backend folder:   python -m tests.test_pdf
"""
import io

import config
from pipeline import detector
from pipeline.pdf import PdfError, ScannedPdfError, clean_text, extract_text
from tests.pdf_factory import build_pdf
from tests.samples import DEMO_NOTE, DEMO_PAGES


class NoGLiNER:
    """A GLiNER that finds nothing, so /analyze runs without the real model."""
    def predict_entities(self, text, labels, threshold=0.5):
        return []


def raises(exc_type, fn, *args):
    try:
        fn(*args)
    except exc_type:
        return True
    return False


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


def test_scanned_and_bad_files():
    assert raises(ScannedPdfError, extract_text, build_pdf([[]]))
    assert raises(PdfError, extract_text, b"hello, not a pdf")
    assert raises(PdfError, extract_text, b"%PDF-1.4\ngarbage that is not a pdf")


def test_page_and_size_limits():
    from pipeline import pdf
    assert raises(PdfError, extract_text, build_pdf([["Page text here."]] * (pdf.MAX_PAGES + 1)))
    assert not raises(PdfError, extract_text, build_pdf([["Page text here."]] * pdf.MAX_PAGES))
    assert raises(PdfError, extract_text, b"%PDF-1.4\n" + b"0" * pdf.MAX_BYTES)


def test_error_messages_never_echo_document_text():
    # Messages go straight to the user and may end up in logs, so they must be generic.
    secret = "Margaret Ellison 9123947241"
    for data in [build_pdf([[secret]] * 31), b"%PDF-1.4\n" + secret.encode()]:
        try:
            extract_text(data)
        except PdfError as e:
            assert "Margaret" not in str(e) and "9123" not in str(e), str(e)


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
    assert clean_text(["atrial ﬁbrillation noted"]) == "atrial fibrillation noted"


def test_flask_upload():
    config.USE_GLINER = True
    detector._model = NoGLiNER()
    import app as app_module
    c = app_module.app.test_client()

    def upload(data, name):
        return c.post("/documents", data={"file": (io.BytesIO(data), name)}, content_type="multipart/form-data")

    ok = upload(build_pdf(DEMO_PAGES), "Visit note.pdf")
    assert ok.status_code == 201 and DEMO_NOTE in ok.json["original_text"]
    assert ok.json["title"] == "Visit note" and ok.json["source"] == "pdf"

    scanned = upload(build_pdf([[]]), "scan.pdf")
    assert scanned.status_code == 422 and "scanned" in scanned.json["detail"]

    assert upload(b"plain text", "notes.pdf").status_code == 400


if __name__ == "__main__":
    test_extracts_demo_note_with_wrapped_lines_rejoined()
    test_multiple_pages_are_separated_by_a_blank_line()
    test_small_print_without_space_characters_keeps_words_apart()
    test_side_by_side_columns_are_split_with_a_tab()
    test_scanned_and_bad_files()
    test_clean_text_keeps_list_items_and_labels_on_their_own_lines()
    test_clean_text_fixes_ligatures_and_odd_spaces()
    test_flask_upload()
    print("all pdf tests passed")
