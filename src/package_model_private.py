"""Упаковка текущей модели ЛР № 2 для приватной сдачи преподавателю.

Полученный архив намеренно НЕ предназначен для открытого репозитория.
Содержимое проверяется по контрольной сумме перед упаковкой.
"""
from __future__ import annotations

import json
from zipfile import ZIP_DEFLATED, ZipFile

from .config import METRICS_DIR, MODEL_MANIFEST, MODEL_PATH, ROOT
from .data import sha256_file


def main() -> None:
    if not MODEL_MANIFEST.is_file() or not MODEL_PATH.is_file():
        raise FileNotFoundError("Сначала выполните обучение и сохранение модели")
    expected = MODEL_MANIFEST.read_text(encoding="ascii").split()[0]
    actual = sha256_file(MODEL_PATH)
    if expected != actual:
        raise ValueError("Контрольная сумма модели не совпадает; архив не создан")
    files = [
        MODEL_PATH,
        MODEL_MANIFEST,
        METRICS_DIR / "baseline.json",
        METRICS_DIR / "training_config.json",
    ]
    for file in files:
        if not file.is_file():
            raise FileNotFoundError(f"Отсутствует необходимый файл: {file}")
    baseline = json.loads(files[2].read_text(encoding="utf-8"))
    if baseline["model_sha256"] != actual:
        raise ValueError("Метрики относятся к другой версии модели")
    output = ROOT / "lab2_model_private.zip"
    with ZipFile(output, mode="w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for file in files:
            archive.write(file, arcname=file.relative_to(ROOT).as_posix())
        archive.writestr(
            "README_PRIVATE.txt",
            "Приватный артефакт ЛР № 2. Не публиковать на открытом GitHub.\n"
            "Проверить models/digits_baseline.joblib по integrity/model.sha256\n"
            "до загрузки. Формат joblib потенциально исполняет код;\n"
            "загружать только доверенную модель.\n",
        )
    print(f"Личный архив модели создан: {output}")
    print(f"SHA256 архива: {sha256_file(output)}")
    print("Сдавать через личный кабинет курса или иной канал с ограниченным доступом.")


if __name__ == "__main__":
    main()
