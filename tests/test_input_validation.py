"""Automated negative and positive tests for the single serving boundary."""
import numpy as np
import pytest

from src.inference import InputValidationError, predict_digits, predict_request, validate_digits


class SpyModel:
    def __init__(self):
        self.calls = 0

    def predict(self, matrix):
        self.calls += 1
        return np.zeros(len(matrix), dtype=np.int64)


def test_positive_8_by_8_image_predicts_once():
    spy = SpyModel()
    answer = predict_digits(spy, np.zeros((8, 8), dtype=np.float64))
    assert answer.tolist() == [0]
    assert spy.calls == 1


def test_positive_flat_64_features():
    spy = SpyModel()
    assert predict_request(spy, {"pixels": [0.0] * 64}).tolist() == [0]
    assert spy.calls == 1


def test_positive_batch_three_images():
    spy = SpyModel()
    assert predict_digits(spy, np.zeros((3, 8, 8))).shape == (3,)
    assert spy.calls == 1


@pytest.mark.parametrize("bad_input", [
    "wrong type",
    b"corrupted PNG payload",
    {"unexpected": "object"},
    None,
    [],
    np.array([]),
    np.zeros((7, 8)),
    np.zeros((8, 8, 1)),
    np.zeros((33, 8, 8)),
    np.full((8, 8), float("nan")),
    np.full((8, 8), float("inf")),
    np.full((8, 8), -0.1),
    np.full((8, 8), 16.1),
    np.full((8, 8), "1", dtype=object),
    np.full((8, 8), 1 + 1j),
    [[0, 1], [2]],
    [[[[]]]],
    np.zeros((8, 8), dtype=bool),
])
def test_negative_input_rejected_before_model_invocation(bad_input):
    spy = SpyModel()
    with pytest.raises(InputValidationError):
        predict_digits(spy, bad_input)
    assert spy.calls == 0


@pytest.mark.parametrize("payload", [
    {"wrong_field": [0.0] * 64},
    {"pixels": [0.0] * 64, "unexpected_field": "secret"},
    None,
    [0.0] * 64,
])
def test_negative_request_schema_rejected_before_model_invocation(payload):
    spy = SpyModel()
    with pytest.raises(InputValidationError):
        predict_request(spy, payload)
    assert spy.calls == 0


def test_negative_configurable_batch_cap_without_large_allocation():
    spy = SpyModel()
    small_tensor = np.zeros((4, 8, 8), dtype=np.float64)
    with pytest.raises(InputValidationError):
        predict_digits(spy, small_tensor, max_batch_size=3)
    assert spy.calls == 0


def test_input_is_copied_before_predict():
    original = np.ones((8, 8))
    validated = validate_digits(original)
    validated[0, 0] = 9.0
    assert original[0, 0] == 1.0
