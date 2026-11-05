#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p reports/evidence

# Никаких токенов, ключей или секретов: только итоговые безопасные параметры.
{
  echo '=== Пользователь и рабочее окружение ==='
  id
  python --version
  echo '=== Права на данные, модель и каталог модели ==='
  stat -c '%a %U:%G %n' data/digits.csv data/digits_original.csv models models/digits_baseline.joblib
  echo '=== Результирующая серверная политика OpenSSH (без ключей) ==='
  sudo sshd -T | grep -E '^(permitrootlogin|pubkeyauthentication|passwordauthentication|kbdinteractiveauthentication) '
  echo '=== Настройки UFW ==='
  sudo ufw status verbose
  echo '=== Проверка прослушивания Jupyter (без доступа к токену) ==='
  sockets="$(ss -ltn | grep ':8888 ' || true)"
  if [ -z "$sockets" ]; then
    echo 'Jupyter сейчас не запущен. Запустите его на 127.0.0.1:8888 и повторите проверку.'
  else
    printf '%s\n' "$sockets"
    if printf '%s\n' "$sockets" | grep -Eq '0\.0\.0\.0:8888|\[::\]:8888|:::8888'; then
      echo 'ОШИБКА: Jupyter прослушивает внешний интерфейс' >&2
      exit 1
    fi
    if ! printf '%s\n' "$sockets" | grep -Eq '127\.0\.0\.1:8888'; then
      echo 'ПРЕДУПРЕЖДЕНИЕ: привязка к 127.0.0.1:8888 не подтверждена.'
    fi
  fi
  echo '=== Приватная модель не должна попадать в публичный Git ==='
  git check-ignore models/digits_baseline.joblib || true
} 2>&1 | tee reports/evidence/lab2_vm_security.txt
