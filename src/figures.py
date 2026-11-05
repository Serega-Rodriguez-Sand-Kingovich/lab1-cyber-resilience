"""Create publication-ready PNG figures from actual model outputs."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import ConfusionMatrixDisplay, confusion_matrix

from .config import CLASSES, FIGURES_DIR

plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["savefig.dpi"] = 180


def _save(name: str, destination: Path = FIGURES_DIR) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / name
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", dpi=190)
    plt.close()
    return path


def plot_class_split(y_train: np.ndarray, y_test: np.ndarray) -> Path:
    positions = np.arange(10)
    train_counts = np.bincount(y_train, minlength=10)
    test_counts = np.bincount(y_test, minlength=10)
    _fig, ax = plt.subplots(figsize=(9, 4.4))
    ax.bar(positions - 0.18, train_counts, 0.36, label="Обучение")
    ax.bar(positions + 0.18, test_counts, 0.36, label="Тест")
    ax.set_xticks(positions)
    ax.set_xlabel("Класс цифры")
    ax.set_ylabel("Число изображений")
    ax.set_title("Стратифицированное разделение выборки")
    ax.legend()
    ax.grid(axis="y", alpha=0.22)
    return _save("lab2_01_class_split.png")


def plot_confusion(y_true: np.ndarray, y_pred: np.ndarray) -> Path:
    cm = confusion_matrix(y_true, y_pred, labels=CLASSES)
    _fig, ax = plt.subplots(figsize=(7.4, 6.9))
    ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=CLASSES).plot(
        ax=ax, cmap="Blues", colorbar=True, values_format="d"
    )
    ax.set_title("Матрица ошибок на отложенной выборке")
    ax.set_xlabel("Предсказанный класс")
    ax.set_ylabel("Истинный класс")
    return _save("lab2_02_confusion_matrix.png")


def plot_class_f1(report: dict) -> Path:
    f1 = [report[str(i)]["f1-score"] for i in CLASSES]
    _fig, ax = plt.subplots(figsize=(8.5, 4.1))
    bars = ax.bar(range(10), f1, color="steelblue")
    ax.bar_label(bars, labels=[f"{v:.2f}" for v in f1], padding=3, fontsize=9)
    ax.set_xticks(range(10))
    ax.set_ylim(0, 1.08)
    ax.set_xlabel("Класс цифры")
    ax.set_ylabel("F1")
    ax.set_title("F1 по классам на тестовой выборке")
    ax.grid(axis="y", alpha=0.2)
    return _save("lab2_03_f1_by_class.png")


def plot_wrong_predictions(X: np.ndarray, y: np.ndarray, pred: np.ndarray) -> Path | None:
    wrong = np.flatnonzero(y != pred)[:8]
    if wrong.size == 0:
        return None
    fig, axes = plt.subplots(2, 4, figsize=(9.6, 5.0))
    for ax in axes.flat:
        ax.axis("off")
    for ax, idx in zip(axes.flat, wrong):
        ax.imshow(X[idx].reshape(8, 8), cmap="gray_r", vmin=0, vmax=16)
        ax.set_title(f"Истина={y[idx]}, прогноз={pred[idx]}", fontsize=10)
        ax.axis("off")
    fig.suptitle("Примеры ошибочных предсказаний", fontsize=13)
    return _save("lab2_04_wrong_predictions.png")


def plot_perturbations(
    clean: np.ndarray,
    noise: np.ndarray,
    labels: np.ndarray,
    clean_predictions: np.ndarray,
    noise_predictions: np.ndarray,
) -> Path:
    fig, axes = plt.subplots(2, 5, figsize=(11.5, 5.2))
    for j in range(5):
        axes[0, j].imshow(clean[j].reshape(8, 8), cmap="gray_r", vmin=0, vmax=16)
        axes[0, j].set_title(f"Прогноз {clean_predictions[j]}, метка {labels[j]}", fontsize=9)
        axes[1, j].imshow(noise[j].reshape(8, 8), cmap="gray_r", vmin=0, vmax=16)
        axes[1, j].set_title(f"После шума: {noise_predictions[j]}", fontsize=10)
        axes[0, j].axis("off")
        axes[1, j].axis("off")
    fig.suptitle("Влияние слабого шума на изображения цифр 8×8", fontsize=13)
    return _save("lab2_05_noise_examples.png")


def plot_robustness(robustness: dict) -> Path:
    variants = ["Исходные", "Шум", "Яркость"]
    accuracy = [robustness["variants"][v]["accuracy"] for v in ("clean", "noise", "brightness")]
    changes = [robustness["variants"][v]["changed_fraction"] for v in ("clean", "noise", "brightness")]
    idx = np.arange(len(variants))
    _fig, ax = plt.subplots(figsize=(8.2, 4.8))
    ax.bar(idx - 0.18, accuracy, 0.36, label="Точность на тех же 20 примерах")
    ax.bar(idx + 0.18, changes, 0.36, label="Доля изменившихся ответов")
    ax.set_xticks(idx, variants)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Доля")
    ax.set_title("Чувствительность к слабым искажениям изображений")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2, fontsize=9)
    ax.grid(axis="y", alpha=0.2)
    return _save("lab2_06_robustness.png")


def plot_atypical(atypical: np.ndarray, typical: np.ndarray, predicted_class: int) -> Path:
    _fig, axes = plt.subplots(1, 2, figsize=(6.8, 3.6))
    axes[0].imshow(typical.reshape(8, 8), cmap="gray_r", vmin=0, vmax=16)
    axes[0].set_title("Типичная тестовая цифра")
    axes[1].imshow(atypical.reshape(8, 8), cmap="gray_r", vmin=0, vmax=16)
    axes[1].set_title(f"Нетипичный светлый вход: прогноз={predicted_class}")
    for ax in axes:
        ax.axis("off")
    return _save("lab2_07_atypical_input.png")
