"""One validated prediction gateway for notebook, scripts and later API layers.

The caller must use a trusted model; data verification runs *before* predict().
Raw files and encoded image bytes are intentionally not accepted. A future web
endpoint must enforce upload/body byte limits before parsing or decoding.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from .config import MAX_ARRAY_BYTES, MAX_BATCH, MODEL_MANIFEST, MODEL_PATH
from .data import sha256_file


class InputValidationError(ValueError):
    """Controlled rejection of a malformed or excessive request."""


def _shape_of_list(obj: Any, depth: int = 0) -> tuple[int, ...]:
    """Discover bounded nesting before allowing NumPy to allocate a tensor."""
    if depth > 3:
        raise InputValidationError("Too many nested dimensions")
    if isinstance(obj, (list, tuple)):
        n = len(obj)
        if not n:
            raise InputValidationError("Empty input is not accepted")
        if n > 64:
            raise InputValidationError("Input dimensions exceed the safe structural limit")
        child_shape = _shape_of_list(obj[0], depth + 1)
        for item in obj[1:]:
            if _shape_of_list(item, depth + 1) != child_shape:
                raise InputValidationError("Ragged array is not supported")
        return (n,) + child_shape
    if isinstance(obj, (bool, np.bool_)) or not isinstance(obj, (int, float, np.number)):
        raise InputValidationError("Pixel data must be numeric, not string/object")
    if isinstance(obj, (complex, np.complexfloating)):
        raise InputValidationError("Complex pixel values are not supported")
    return ()


def validate_digits(raw: Any, max_batch_size: int = MAX_BATCH) -> np.ndarray:
    """Accept 8x8, 64, Nx8x8 or Nx64 numeric values in the [0,16] range.

    The maximum image count is 32 by default. Return a detached N x 64
    float64 array; NaN, Inf, objects, bytes and malformed images are rejected.
    """
    if not isinstance(max_batch_size, int) or not 1 <= max_batch_size <= MAX_BATCH:
        raise ValueError(f"max_batch_size must be between 1 and {MAX_BATCH}")
    if isinstance(raw, np.ndarray):
        array = raw
    elif isinstance(raw, (list, tuple)):
        shape = _shape_of_list(raw)
        if math.prod(shape) > 64 * max_batch_size:
            raise InputValidationError("Input exceeds maximum number of pixel values")
        array = np.asarray(raw)
    else:
        raise InputValidationError("Input must be a NumPy array or numeric list")
    if array.ndim not in (1, 2, 3):
        raise InputValidationError("Image must have 1, 2 or 3 dimensions")
    if array.size > 64 * max_batch_size or array.nbytes > MAX_ARRAY_BYTES:
        raise InputValidationError("Input exceeds the maximum allowed size")
    if array.dtype.kind not in "iuf":
        raise InputValidationError("Pixel values must have a real numeric dtype")

    if array.ndim == 1 and array.shape == (64,) or array.ndim == 2 and array.shape == (8, 8):
        batch = array.reshape(1, 64)
    elif array.ndim == 2 and array.shape[1] == 64:
        batch = array
    elif array.ndim == 3 and array.shape[1:] == (8, 8):
        batch = array.reshape(array.shape[0], 64)
    else:
        raise InputValidationError("Expected image shape 8x8 or batch N x 8x8 / N x 64")
    if not 1 <= batch.shape[0] <= max_batch_size:
        raise InputValidationError(f"Number of images must be between 1 and {max_batch_size}")
    batch = np.array(batch, dtype=np.float64, copy=True)
    if not np.isfinite(batch).all():
        raise InputValidationError("NaN and Inf are forbidden")
    if (batch < 0).any() or (batch > 16).any():
        raise InputValidationError("Pixel intensity must be between 0 and 16")
    return batch


def predict_digits(model: Any, raw: Any, max_batch_size: int = MAX_BATCH) -> np.ndarray:
    """Validate everything before any model.predict method can be invoked."""
    checked = validate_digits(raw, max_batch_size=max_batch_size)
    return np.asarray(model.predict(checked), dtype=np.int64)


def load_verified_model(
    path: Path = MODEL_PATH,
    manifest: Path = MODEL_MANIFEST,
) -> Any:
    """Load only a model produced by this project and verified before loading.

    WARNING: joblib uses pickle internally and must NEVER load untrusted model
    bytes. A checksum in the same writable location is not an authenticity proof.
    Preserve the trusted hash separately when moving a model to another host.
    """
    path = Path(path)
    manifest = Path(manifest)
    if not path.is_file() or not manifest.is_file():
        raise FileNotFoundError("Model and its SHA256 manifest must both exist")
    text = manifest.read_text(encoding="ascii").strip()
    match = re.fullmatch(r"([a-f0-9]{64})  (models/[a-zA-Z0-9_.-]+\.joblib)", text)
    if match is None or match.group(2) != f"models/{path.name}":
        raise ValueError("Model manifest has an unexpected format or filename")
    if sha256_file(path) != match.group(1):
        raise ValueError("Model SHA256 mismatch; refusing to deserialize")
    # This is a project-owned/trusted model, never user-supplied joblib content.
    return joblib.load(path)


def predict_request(model: Any, payload: Any) -> np.ndarray:
    """Minimal future JSON API contract: {'pixels': image_or_batch}."""
    if not isinstance(payload, dict):
        raise InputValidationError("Request must be an object with required field 'pixels'")
    if set(payload) != {"pixels"}:
        raise InputValidationError("Request requires exactly one field: 'pixels'")
    return predict_digits(model, payload["pixels"])
