# Лабораторная работа № 3 — безопасный CI/CD для ML-проекта

Дисциплина: «Киберустойчивость систем искусственного интеллекта». Проект продолжает ЛР № 1 и № 2. Среда разработки — Ubuntu 24.04.5 LTS в VirtualBox. Базовая модель — классификатор рукописных цифр 8×8 из ЛР № 2.

## Зафиксированные результаты ЛР № 2

- Рабочий датасет `data/digits.csv`: 1740 строк, 10 классов, 64 признака + `target`; SHA256: `4b55658bf1299c5e4bdce02ae154081e2694f74e22eca2c5bc8b7a5c8d67419e`.
- Обучение/тест: стратифицированное разделение 80% / 20%, `random_state=42`, 348 тестовых примеров.
- Исходная Accuracy: `0.9741379310344828` (97,41%).
- Проверенный артефакт модели: `models/digits_baseline.joblib`, SHA256: `655ada9ced68462b56dc298ad18bba5e2c2b4fe9783181aef8067ffd3467c9a9`.
- Model Gate: разрешённое относительное снижение Accuracy 5%, порог: `0.9741379310344828 × 0.95 ≈ 0.925431`.

## Как работает CI

Файл `.github/workflows/ci.yml` запускается на `push` в `main`, `lab3-ci`, демонстрационные ветки `demo/**`, а также при `pull_request` и ручном `workflow_dispatch`.

Единый обязательный pipeline выполняет шаги **по порядку**, поэтому ошибка любого этапа блокирует следующие обычные шаги:

1. Получение исходников, SHA256 датасета/модели, запись SHA коммита.
2. Установка фиксированных runtime- и CI-зависимостей для Python 3.12.
3. Ruff и Bandit.
4. Pytest, результаты JUnit XML.
5. `pip-audit` рабочих зависимостей.
6. Data Quality Gate.
7. Model Quality Gate на фиксированном тестовом разделении.
8. Сборка Docker-образа без запуска приложения от root.
9. Trivy (реальный JSON-скан образа) и Security Gate.
10. Отдельная безопасная проверка синтетического отчёта Security Gate.
11. Trivy Config — проверка Dockerfile.
12. Smoke-проверка Docker: UID 10001, сеть отключена, файловая система только для чтения, привилегии ограничены.
13. Сохранение отчётов через GitHub Actions Artifacts, **даже при сбое**. Сохранение отчётов не превращает ошибочный pipeline в успешный.

Инструменты: Python 3.12, pytest 9.2.0, Ruff 0.17.3, Bandit 1.9.4, pip-audit 2.10.1, Trivy 0.76.1. В GitHub Actions используются зафиксированные **полные SHA** официальных actions: checkout v7.0.1, setup-python v7.0.0, upload-artifact v7.0.1 (комментарии содержат номера версий). Trivy v0.76.1 дополнительно проверяется по SHA256 официального файла контрольных сумм.

## Защитные политики

- **Data Gate**: схема данных 64 `pixel_r_c` плюс `target`, 1740 объектов, ровно 174 на каждый класс, значения пикселей 0–16, отсутствие пропусков, NaN и Inf, неизменный SHA256. Правила: `config/data_quality_policy.json`.
- **Model Gate**: метрика Accuracy, на том же наборе и с тем же разделением, что в ЛР № 2; результат кандидата должен быть не ниже 95% от зафиксированного baseline. Baseline не перезаписывается. Правила: `config/model_quality_policy.json`.
- **Аудит зависимостей**: сборка отклоняется при любой известной уязвимости, найденной `pip-audit` в `requirements-runtime.txt` (политика строже минимальной блокировки только CRITICAL).
- **Security Gate Trivy**: обработка реального JSON, отклонение CRITICAL и UNKNOWN, а также отсутствующих/нечитаемых результатов сканирования. Скрипт: `scripts/security_gate.py`. Это отдельная проверка от `trivy config`, которая отклоняет любые конфигурационные нарушения.
- **Секреты**: дополнительных токенов не требуется, стандартный `GITHUB_TOKEN` имеет только `contents: read`; `checkout` не сохраняет учётные данные; не используются `pull_request_target`, `privileged`, Docker socket внутри контейнера или публикация в registry.
- **Модель**: перед `joblib.load` проверяется закреплённый SHA256. Формат joblib основан на pickle, поэтому нельзя загружать модель из недоверенного источника без проверки происхождения и целостности.
- **CI-образ**: официальный `python:3.12.16-slim-trixie`, непривилегированный UID 10001, без API и внешних портов. В Docker включён HEALTHCHECK для будущего длительно работающего сервиса; для текущего одноразового запуска проверяем реальный `docker run`.

## Локальное воспроизведение

Команды вводятся в Ubuntu из каталога `~/ml-project` с активированным `.venv`:

```bash
python -m pytest tests/ -q
ruff check src/ tests/ scripts/data_gate.py scripts/model_gate.py scripts/docker_smoke.py scripts/export_runtime_requirements.py scripts/security_gate.py
python -m bandit -r src/ -q
pip-audit -r requirements-runtime.txt
sha256sum -c integrity/datasets.sha256
python scripts/data_gate.py
python scripts/model_gate.py
python scripts/security_gate.py --report tests/fixtures/security_gate_input.json
sudo docker build -t ml-project:lab3 .
sudo docker run --rm --entrypoint id ml-project:lab3 -u
sudo docker run --rm --read-only --network none --cap-drop ALL --security-opt no-new-privileges --pids-limit 64 ml-project:lab3
sudo trivy image --scanners vuln --severity CRITICAL --exit-code 1 ml-project:lab3
trivy config --exit-code 1 Dockerfile
```

## Демонстрации отказов (только в отдельных ветках)

Сначала получить **зелёный** запуск `lab3-ci`. Далее подготовить три отдельные ветки `demo/data-failure`, `demo/model-failure`, `demo/security-failure` из работоспособного состояния.

- **Data Gate**: в демонстрационной ветке создать испорченную **копию** CSV без `pixel_0_0` (в `/tmp` на runner) и передать её скрипту Data Gate через `--data`. Исходный CSV и эталон SHA256 не менять. Сбой должен произойти до Model Gate и Docker.
- **Model Gate**: в отдельной ветке для CI указать `--demo-weak-candidate`. Реально вычисляется Accuracy константного предиктора на фиксированной выборке; порог нарушается, Docker не собирается. Не подменять значение метрики искусственным числом.
- **Security Gate**: в отдельной ветке изменить **только** `tests/fixtures/security_gate_input.json`, добавив синтетический элемент с `Severity: CRITICAL` (образец `tests/fixtures/security_gate_critical_example.json`). Реальная Trivy-проверка образа выполняется независимо от этой имитации. Следующий шаг Dockerfile/smoke должен быть пропущен.

Для каждого неуспешного GitHub Actions Run сохранить URL и/или скриншот со статусом failed, SHA коммита, описание нарушенного условия и список пропущенных последующих этапов. После экспериментов оставить исходную рабочую ветку `lab3-ci` зелёной и интегрировать её в `main` обычным pull request; демонстрационные ветки в `main` не сливать.

## Отчёты и доказательства

Локальные протоколы находятся в `reports/lab3/`. Файлы с текущего запуска GitHub Actions сохраняются отдельно в `reports/ci/` и загружаются как Actions Artifact `lab3-ci-evidence-<run_id>` со сроком хранения 30 дней.

Где смотреть: репозиторий → **Actions** → запуск workflow → **Jobs** / **Artifacts**. Зеленый статус подтверждает только конкретный проверенный коммит и версию уязвимостей на дату запуска.

## Границы проверки

Повторная CI-оценка не заменяет новую независимую финальную оценку модели. Отсутствие критических находок Trivy не означает отсутствие всех уязвимостей; базы обновляются. Joblib надо загружать только после контроля доверенного эталона. Нельзя утверждать, что demo-файлы отражают реальные находки сканера.
