"""Document → SystemProfile extraction (P1).

Pipeline per document: bytes → per-page text (pypdf for text PDFs, vision →
OCR → manual for scans/photos) → model JSON fill → sanitize → merge.
Documents are untrusted data: policy, hard limits, status, and version can
only come from a human (P2), never from extraction; every doc-sourced value
must carry an exact quote found in the source text, or the field is rejected.
Conflicting values across documents are flagged, never auto-resolved.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from core.schemas.profile import (
    ExpectedBehaviour,
    FailureDefinition,
    HardLimit,
    ModeRelaxation,
    NormalRange,
)

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES = 5

PDF_EXTENSIONS = (".pdf",)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")
TEXT_EXTENSIONS = (".txt", ".md")

IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

#: Model output keys that survive sanitizing. Everything else (policy, hard
#: limits, status, version, baseline, system_id) is human-only and dropped.
ALLOWED_KEYS = (
    "name",
    "kind",
    "appliance_type",
    "owner_contact",
    "environment",
    "normal_ranges",
    "expected_behaviours",
    "modes",
    "failure_definitions",
)

#: Mergeable list sections and the key that identifies one entry.
MERGE_KEYS = {
    "normal_ranges": "metric",
    "expected_behaviours": "name",
    "modes": "mode",
    "failure_definitions": "name",
}

_LIST_MODELS = {
    "normal_ranges": NormalRange,
    "expected_behaviours": ExpectedBehaviour,
    "modes": ModeRelaxation,
    "failure_definitions": FailureDefinition,
}

_WS = re.compile(r"\s+")


class ExtractError(RuntimeError):
    """A document could not be read or parsed."""


class OcrUnavailable(RuntimeError):
    """No OCR engine on this machine; manual entry is the fallback."""


@dataclass
class ExtractedDoc:
    filename: str
    kind: str  # "pdf" | "image" | "text"
    pages: list[str]  # text per page; images yield one pseudo-page
    sha256: str
    needs_manual: bool = False
    rejected: list[str] = field(default_factory=list)


def classify_file(filename: str) -> Optional[str]:
    suffix = Path(filename).suffix.lower()
    if suffix in PDF_EXTENSIONS:
        return "pdf"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in TEXT_EXTENSIONS:
        return "text"
    return None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


def extract_text_pages(pdf_bytes: bytes) -> list[str]:
    """Text of each PDF page; raises ExtractError on unreadable input."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ExtractError("pypdf is not installed") from exc
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:
        raise ExtractError(f"could not read PDF: {exc}") from exc


def pdf_has_text(pages: list[str], threshold: int = 20) -> bool:
    """Scanned PDFs extract to ~nothing; those need vision/OCR instead."""
    return any(len((page or "").strip()) >= threshold for page in pages)


def ocr_image(image_bytes: bytes) -> str:
    """Tesseract OCR; raises OcrUnavailable when no engine is installed."""
    tesseract = shutil.which("tesseract")
    if tesseract is None:
        raise OcrUnavailable("tesseract is not installed")
    with tempfile.NamedTemporaryFile(suffix=".png") as handle:
        handle.write(image_bytes)
        handle.flush()
        try:
            completed = subprocess.run(
                [tesseract, handle.name, "stdout"],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            raise ExtractError("OCR timed out") from exc
    if completed.returncode != 0:
        raise ExtractError(f"OCR failed: {completed.stderr[:200]}")
    return completed.stdout


def read_image_text(
    image_bytes: bytes,
    mime: str,
    vision_fn: Optional[Callable[[bytes, str, str], str]] = None,
) -> tuple[str, bool]:
    """Vision first, OCR fallback; returns (text, needs_manual)."""
    prompt = (
        "Transcribe every visible line of this document photo exactly, "
        "top to bottom. Return plain text only, no commentary."
    )
    if vision_fn is not None:
        try:
            text = vision_fn(image_bytes, mime, prompt)
            if text.strip():
                return text, False
        except Exception:
            pass
    try:
        text = ocr_image(image_bytes)
        if text.strip():
            return text, False
    except (OcrUnavailable, ExtractError):
        pass
    return "", True


def doc_to_pages(
    filename: str,
    data: bytes,
    vision_fn: Optional[Callable[[bytes, str, str], str]] = None,
) -> ExtractedDoc:
    """Bytes → per-page text with the vision/OCR/manual fallback chain."""
    kind = classify_file(filename)
    if kind is None:
        raise ExtractError(f"unsupported file type: {filename}")
    if len(data) > MAX_FILE_BYTES:
        raise ExtractError(f"{filename} exceeds the 10 MB limit")
    digest = sha256_bytes(data)
    if kind == "text":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ExtractError(f"{filename} is not UTF-8 text") from exc
        return ExtractedDoc(filename, kind, [text], digest)
    if kind == "pdf":
        pages = extract_text_pages(data)
        if pdf_has_text(pages):
            return ExtractedDoc(filename, kind, pages, digest)
        # Scanned PDF: rasterizing needs pymupdf; without it, manual entry.
        import importlib.util

        if importlib.util.find_spec("fitz") is None:
            return ExtractedDoc(filename, kind, [""], digest, needs_manual=True)
        raise ExtractError("scanned-PDF rasterizing is not implemented yet")
    suffix = Path(filename).suffix.lower()
    text, needs_manual = read_image_text(data, IMAGE_MIME[suffix], vision_fn)
    return ExtractedDoc(filename, kind, [text], digest, needs_manual)


def _entry_model(section: str):
    return _LIST_MODELS[section]


def sanitize_extraction(
    raw: dict, doc: ExtractedDoc
) -> tuple[dict[str, Any], list[str]]:
    """Whitelist keys, verify quotes, validate entries.

    Returns (partial_profile, rejected_reasons). Human-only keys are dropped
    silently (they must never come from a document); doc-sourced entries
    whose quote is missing or not found in the source text are rejected.
    """
    partial: dict[str, Any] = {}
    rejected: list[str] = []
    source_text = normalize("\n".join(doc.pages))
    for key in ALLOWED_KEYS:
        if key not in raw:
            continue
        value = raw[key]
        if key in _LIST_MODELS:
            kept: list[dict] = []
            entries = value if isinstance(value, list) else []
            for index, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    rejected.append(f"{key}[{index}]: not an object")
                    continue
                provenance = (
                    entry.get("provenance")
                    if isinstance(entry.get("provenance"), dict)
                    else {}
                )
                quote = provenance.get("quote", "")
                if not quote or not quote.strip():
                    rejected.append(
                        f"{key}[{index}]: missing source quote"
                    )
                    continue
                if normalize(quote) not in source_text:
                    rejected.append(
                        f"{key}[{index}]: quote not found in {doc.filename}"
                    )
                    continue
                try:
                    model = _entry_model(key).model_validate(entry)
                except ValueError as exc:
                    rejected.append(f"{key}[{index}]: {exc}")
                    continue
                kept.append(model.model_dump(mode="json"))
            partial[key] = kept
        elif key == "environment" and isinstance(value, dict):
            partial[key] = {
                str(item): str(text)
                for item, text in value.items()
                if isinstance(item, str)
            }
        elif isinstance(value, str):
            partial[key] = value
    return partial, rejected


def _entry_value(section: str, entry: dict) -> dict:
    """Entry minus provenance, for conflict comparison."""
    return {key: val for key, val in entry.items() if key != "provenance"}


def merge_partials(
    partials: list[tuple[str, dict[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Merge doc extractions; conflicts are flagged, never auto-resolved."""
    merged: dict[str, Any] = {}
    conflicts: list[dict[str, Any]] = []
    seen: dict[str, dict[str, tuple[str, dict]]] = {
        section: {} for section in MERGE_KEYS
    }
    seen_env: dict[str, tuple[str, str]] = {}
    for doc_name, partial in partials:
        for section, id_key in MERGE_KEYS.items():
            for entry in partial.get(section, []) or []:
                ident = entry.get(id_key, "")
                current = seen[section].get(ident)
                if current is None:
                    seen[section][ident] = (doc_name, entry)
                    continue
                other_doc, other = current
                if _entry_value(section, other) != _entry_value(section, entry):
                    conflicts.append(
                        {
                            "field": section,
                            "key": ident,
                            "values": [
                                {
                                    "doc": other_doc,
                                    "value": _entry_value(section, other),
                                    "quote": other.get("provenance", {}).get(
                                        "quote", ""
                                    ),
                                },
                                {
                                    "doc": doc_name,
                                    "value": _entry_value(section, entry),
                                    "quote": entry.get("provenance", {}).get(
                                        "quote", ""
                                    ),
                                },
                            ],
                        }
                    )
                    del seen[section][ident]
        for item, text in (partial.get("environment", {}) or {}).items():
            current = seen_env.get(item)
            if current is None:
                seen_env[item] = (doc_name, text)
            elif current[1] != text:
                conflicts.append(
                    {
                        "field": "environment",
                        "key": item,
                        "values": [
                            {"doc": current[0], "value": current[1]},
                            {"doc": doc_name, "value": text},
                        ],
                    }
                )
                del seen_env[item]
        for key in ("name", "kind", "appliance_type", "owner_contact"):
            if key in partial and key not in merged:
                merged[key] = partial[key]
    for section, entries in seen.items():
        merged[section] = [entry for _, entry in entries.values()]
    merged["environment"] = {
        item: text for item, (_, text) in seen_env.items()
    }
    return merged, conflicts


EXTRACTION_SYSTEM = (
    "Fill a SystemProfile JSON object from the document. Quote the exact "
    "source text for every value (provenance.quote). Leave unknown fields "
    "empty; never guess numbers. Only use these keys: name, kind, "
    "appliance_type, owner_contact, environment, normal_ranges, "
    "expected_behaviours, modes, failure_definitions."
)


def fill_profile_from_text(
    doc_name: str,
    text: str,
    model_fn: Callable[[str, str], dict],
) -> dict:
    """Call the model for one document; `model_fn` returns parsed JSON."""
    user = (
        f"Document: {doc_name}\n\n{text[:12000]}"
        if len(text) > 12000
        else f"Document: {doc_name}\n\n{text}"
    )
    raw = model_fn(EXTRACTION_SYSTEM, user)
    if not isinstance(raw, dict):
        raise ExtractError(f"model returned non-object JSON for {doc_name}")
    return raw


def default_model_fn(system: str, user: str) -> dict:
    """Production model call: Muse Spark with a JSON-schema response."""
    import json as jsonlib

    from core.infer import meta_client

    response = meta_client._client().chat.completions.create(
        model=meta_client.DIAGNOSIS_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
    )
    return jsonlib.loads(response.choices[0].message.content)
