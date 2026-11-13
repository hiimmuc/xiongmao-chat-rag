"""Turn an uploaded file into text pieces ready for embedding (used by the worker)."""

from io import BytesIO
from pathlib import Path

import tiktoken
from pypdf import PdfReader

from app.core.config import settings


def extract_text(name, data):
    """Return [(page_number_or_None, text)] for a text PDF, TXT or Markdown file.

    Raises:
        ValueError: For unsupported, encrypted, scanned or oversized files."""
    suffix = Path(name).suffix.lower()
    if suffix in (".txt", ".md"):
        text = data.decode("utf-8")
        if "\x00" in text or not text.strip():
            raise ValueError("Empty or binary text is unsupported")
        return [(None, text)]
    if suffix != ".pdf" or not data.startswith(b"%PDF-"):
        raise ValueError("Only text PDF, TXT and Markdown are supported")
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("Password-protected PDFs are unsupported")
    if not 1 <= len(reader.pages) <= settings().max_document_pages:
        raise ValueError("PDF page limit exceeded")
    pages = [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
    if any(not text.strip() for _, text in pages):
        raise ValueError("Scanned or image-only PDF pages are unsupported; OCR is not enabled")
    return pages


def chunk_text(text, size=800, overlap=100):
    """Split text into token windows of `size` with `overlap` tokens shared between neighbours."""
    if size <= overlap or overlap < 0:
        raise ValueError("Invalid chunk bounds")
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text, disallowed_special=())
    return [enc.decode(tokens[i : i + size]) for i in range(0, len(tokens), size - overlap)]
