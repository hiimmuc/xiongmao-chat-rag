"""Turn an uploaded file into text pieces ready for embedding (used by the API and the worker)."""

import multiprocessing
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


def parse_child(conn, name, data):
    try:
        try:
            import resource  # Linux only; on Windows the 25-second timeout below still applies

            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
            resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
        except ImportError:
            pass
        pages = extract_text(name, data)
        if sum(len(text) for _, text in pages) > 2_000_000:
            raise ValueError("Extracted document is too large")
        conn.send((True, pages))
    except Exception:
        conn.send((False, "invalid_document"))
    finally:
        conn.close()


def isolated_parse(name, data):
    """extract_text in a child process, so hostile PDFs cannot hang or exhaust the caller."""
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe(False)
    process = ctx.Process(target=parse_child, args=(child, name, data))
    process.start()
    child.close()
    try:
        if not parent.poll(25):
            raise ValueError("document_parse_timeout")
        ok, result = parent.recv()
        if not ok:
            raise ValueError(result)
        return result
    finally:
        if process.is_alive():
            process.terminate()
        process.join(5)
        parent.close()


def chunk_text(text, size=800, overlap=100):
    """Split text into token windows of `size` with `overlap` tokens shared between neighbours."""
    if size <= overlap or overlap < 0:
        raise ValueError("Invalid chunk bounds")
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text, disallowed_special=())
    return [enc.decode(tokens[i : i + size]) for i in range(0, len(tokens), size - overlap)]
