"""Write an evidence table with actual outcomes for each negative test case."""
from __future__ import annotations

import numpy as np

from .config import METRICS_DIR
from .data import save_json
from .inference import InputValidationError, load_verified_model, predict_request


class SpyModel:
    """Count calls to assert malformed requests do not reach the model."""

    def __init__(self) -> None:
        self.calls = 0

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        self.calls += 1
        return np.zeros(len(matrix), dtype=np.int64)


def run_validation_cases() -> dict:
    # Every negative input is tiny and safe to allocate on a 4 GiB VM.
    cases = [
        ("missing_required_field", "Отсутствует обязательное поле pixels", {"wrong": [[0.0] * 8 for _ in range(8)]}),
        ("wrong_numeric_type", "Строка abc вместо значения пикселя", {"pixels": [["abc"] * 8 for _ in range(8)]}),
        ("wrong_image_size", "Неверная форма изображения 7x8", {"pixels": [[0.0] * 8 for _ in range(7)]}),
        ("empty_input", "Пустой список пикселей", {"pixels": []}),
        ("nan", "Изображение с NaN", {"pixels": np.full((8, 8), np.nan)}),
        ("inf", "Изображение с Inf", {"pixels": np.full((8, 8), np.inf)}),
        ("batch_limit_33", "Пакет из 33 изображений при максимуме 32", {"pixels": np.zeros((33, 8, 8))}),
        ("pixel_outside_0_to_16", "Пиксели со значениями 16.1 вне диапазона", {"pixels": np.full((8, 8), 16.1)}),
        ("unsupported_binary_file", "Бинарные байты вместо декодированного массива", {"pixels": b"not a valid digit"}),
    ]
    results = []
    for name, description, payload in cases:
        spy = SpyModel()
        rejected = False
        actual = "UNEXPECTED ACCEPTANCE"
        try:
            predict_request(spy, payload)
        except InputValidationError as exc:
            rejected = True
            actual = f"InputValidationError: {exc}"
        passed = rejected and spy.calls == 0
        results.append({
            "case": name,
            "input_description": description,
            "expected": "Контролируемый InputValidationError, 0 вызовов модели",
            "actual": actual,
            "model_calls": spy.calls,
            "passed": passed,
            "conclusion": "Проверка успешна: вход отклонён до модели" if passed else "Ошибка проверки",
        })
    real_model = load_verified_model()
    positive = predict_request(real_model, {"pixels": np.zeros((8, 8))})
    results.append({
        "case": "positive_valid_8_by_8",
        "input_description": "Корректный числовой массив 8x8 из нулей",
        "expected": "Один прогноз класса 0–9",
        "actual": f"Предсказан класс {int(positive[0])}",
        "model_calls": 1,
        "passed": len(positive) == 1 and int(positive[0]) in range(10),
        "conclusion": "Положительный тест успешен" if len(positive) == 1 and int(positive[0]) in range(10) else "Ошибка проверки",
    })
    report = {
        "count": len(results),
        "passed": sum(int(row["passed"]) for row in results),
        "failed": sum(int(not row["passed"]) for row in results),
        "cases": results,
    }
    save_json(METRICS_DIR / "validation_cases.json", report)
    for row in results:
        print(f"{'PASS' if row['passed'] else 'FAIL'} {row['case']}: {row['actual']}")
    if report["failed"]:
        raise RuntimeError("At least one validation case failed")
    return report


if __name__ == "__main__":
    run_validation_cases()
