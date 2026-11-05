#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."

# Дополняем первую лабораторную, не заменяя её данные и исходные документы.
if [ ! -f README.md ] || [ ! -f .gitignore ] || [ ! -f requirements.txt ]; then
  echo 'Ошибка: нет README.md, .gitignore или requirements.txt из ЛР №1.' >&2
  exit 1
fi
if [ ! -f data/digits.csv ] || [ ! -f integrity/datasets.sha256 ]; then
  echo 'Ошибка: выполнять скрипт нужно внутри существующего проекта ЛР №1.' >&2
  exit 1
fi

# Нельзя молча перезаписывать эталонные SHA256 из первой лабораторной.
sha256sum -c integrity/datasets.sha256
# Меняем только права доступа, не содержимое датасета и не его SHA256.
chmod 700 data models
chmod 600 data/digits.csv data/digits_original.csv
if [ -f models/digits_baseline.joblib ]; then
  chmod 600 models/digits_baseline.joblib
fi

# Модель и приватный архив не должны случайно попадать в открытый Git.
if ! grep -Fxq 'lab2_model_private.zip' .gitignore; then
  printf '\n# Приватная сдача артефакта модели из ЛР №2\nlab2_model_private.zip\n' >> .gitignore
fi
if ! grep -Fq 'README_LAB2.md' README.md; then
  printf '\n## Лабораторная работа №2\n\nИнструкции: [README_LAB2.md](README_LAB2.md).\n' >> README.md
fi
python -m pip install -r requirements-lab2.txt
python -m pip freeze > requirements.txt
printf 'ЛР №1 сохранена; зависимости для ЛР №2 установлены и зафиксированы.\n'
