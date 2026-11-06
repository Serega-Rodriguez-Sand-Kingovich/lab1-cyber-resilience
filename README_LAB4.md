# Лабораторная работа №4: защищённый API, веб-интерфейс и мониторинг

**Дисциплина:** «Киберустойчивость систем искусственного интеллекта», ИТМО.
**Основа:** та же модель `models/digits_baseline.joblib` и тот же `src.inference.predict_digits()` из ЛР №2.
**Предыдущие проверки:** тесты, Data Gate, Model Gate, Security Gate, Docker и GitHub Actions из ЛР №3 сохранены.

## Назначение

Создан локальный веб-сервис, принимающий 8×8 числовые изображения цифр и возвращающий результат классификации. Модель обучена ранее; **переобучения в ЛР №4 нет**. Успешная нагрузка и продакшен-безопасность не заявляются.

## Контракт API

**POST `/predict`** — JSON, обязательное единственное поле `pixels`:

```json
{"pixels": [[0,0,5,13,9,1,0,0],[0,0,13,15,10,15,5,0],[0,3,15,2,0,11,8,0],[0,4,12,0,0,8,8,0],[0,5,8,0,0,9,8,0],[0,4,11,0,1,12,7,0],[0,2,14,5,10,12,0,0],[0,0,6,13,10,0,0,0]]}
```

Нужен заголовок `Authorization: Bearer <APP_API_TOKEN>`. Значение `pixels`: одно изображение 8×8 или список 64 значений либо пакет до 32 таких изображений; разрешены только **конечные числа** в диапазоне [0,16]. Схема и предобработка целиком повторяют ЛР №2. JPEG и произвольные PNG не принимаются: сервис работает с уже подготовленной цифровой матрицей, а не с произвольными фотографиями. Никаких пользовательских файлов моделей `joblib/pkl` загрузить нельзя.

Пример успешного ответа:

```json
{
  "prediction": 0,
  "predictions": [0],
  "model_version": "lab2-655ada9ced68",
  "request_id": "<сгенерированный идентификатор>"
}
```

Для пакета `predictions` содержит список классов, а `prediction` равен `null`. Не возвращаются произвольные числовые оценки, названные вероятностями.

**GET `/health`** — HTTP 200 `{"status":"healthy","model_version":"lab2-655ada9ced68"}` только при успешной проверке хэша, загрузке и работе inference-worker. При отсутствии, несоответствии SHA256 или отказе процесса — HTTP 503 с нейтральным `unavailable`.

**GET `/` и `/static/*`** — интерфейс для ввода пикселей (сетка 8×8) и API-токена. Токен остаётся в поле формы, не сохраняется в localStorage, не помещается в URL или HTML/JS исходник. Серверные ответы выводятся через `textContent`. Фронтенд и API одного origin — CORS не требуется.

**GET `/metrics` и `/detection`** — закрытые endpoints. Доступ только с `X-Metrics-Token: <APP_METRICS_TOKEN>`. В запросах по интернету требуются TLS или защищённый SSH-туннель.

## Валидация, ограничения и безопасность

| Мера | Предел / поведение | Причина |
|---|---|---|
| Тело запроса | **24 KiB**, проверка в цикле чтения `request.stream()`; Content-Length только ранняя оптимизация | Блокировать неограниченный поток до полного накопления |
| Чтение тела | **3 с** на получение данных | Не держать медленного клиента бесконечно |
| Структура данных | 8×8, 64, N×8×8, N×64, от **1 до 32** изображений | Тот же контракт ЛР2; ограничение памяти |
| Значения | Только числа 0..16, NaN/Inf, bool, строки запрещены | Не пропускать мусор в модель |
| Параллельность вывода | **1** запрос в модель, ожидание слота до **0,5 с** | Ограничение CPU/очереди |
| Вычисление | **3 с** на запрос к отдельному worker-процессу | При зависании worker принудительно завершается и `/health` становится 503 до перезапуска сервиса; вычисление реально прекращается |
| HTTP-сервер | 1 worker Uvicorn, до 16 одновременных соединений, keep-alive 5 с | Совместимость с limiter/метриками в памяти |
| Rate limit | По умолчанию **5 попыток `/predict` за 60 с на `request.client.host`** | Защита от частых запросов; `X-Forwarded-For` не используется |
| Alert | **4 ответа 401/429 за 60 с** | Правило подозрительной активности |
| Аутентификация | Bearer для `/predict` и отдельный metrics token для служебных endpoints | Разделение прав |
| Docker | UID 10001, `--read-only`, без capabilities, loopback-публикация | Защита контейнера и сети |

Ошибки: `401` — нет/неверный токен; `413` — слишком большое тело; `415` — неподдерживаемый Content-Type (например, файл вместо JSON); `400` — синтаксическая ошибка JSON, запрещённое NaN; `422` — ошибка схемы или пикселей; `429` — частота превышена; `503` — модель недоступна/занята/превышен дедлайн; `408` — таймаут чтения. Traceback и пути файлов клиенту не выдаются.

**Ограничения:** limiter и detector находятся в памяти **одного** процесса: при нескольких worker-процессах или перезапуске счётчики не будут общими/устойчивыми. Хранится максимум 512 ключей в простом учебном limiter, при превышении таблица очищается — это не production-защита от распределённой атаки. Серверный дедлайн реализован отдельным `multiprocessing` child со `spawn`: прошедшая проверку модель сериализуется во внутренний worker **один раз при запуске**, после 3 с зависания worker завершается и сервис перестаёт объявлять себя готовым. Демонстрация рассчитана на Ubuntu/Docker Linux, не на Windows-native запуск сервера. Сервер не принимает загружаемые модели и обрабатывает лишь ограниченные числовые матрицы.
На демонстрации reverse proxy отсутствует. Ошибки, отклонённые самим Uvicorn до попадания в ASGI-приложение (например, при `--limit-concurrency`), не попадают в `lab4_requests_total`; их нужно изучать отдельно в журнале Uvicorn.

## Контроль SHA256 модели

Файл ЛР2: `models/digits_baseline.joblib`, ожидаемый SHA256 `655ada9ced68462b56dc298ad18bba5e2c2b4fe9783181aef8067ffd3467c9a9`.

Проверяется одновременно: встроенный отдельный эталон, `metrics/baseline.json`, `integrity/model.sha256` и фактический файл. Только после совпадения происходит `src.inference.load_verified_model()`. Совпадение хэша не доказывает безопасность произвольного pickle: доверенным считается только известный проектный артефакт.

## Запуск из Ubuntu

Из PowerShell сначала SSH:

```powershell
ssh -i "$env:USERPROFILE\.ssh\id_ed25519_lab1" -p 2222 mluser@127.0.0.1
```

В Ubuntu:

```bash
cd ~/ml-project
source .venv/bin/activate
python -m pip install -r requirements-runtime.txt -r requirements-ci.txt
python -m pytest tests/ -q
sha256sum -c integrity/model.sha256
```

Сгенерировать конфиденциальные токены **вне репозитория**:

```bash
umask 077
mkdir -p ~/.config/lab4
python - <<'PY'
from pathlib import Path
from secrets import token_urlsafe
p = Path.home() / '.config/lab4/app.env'
p.write_text(
    'APP_API_TOKEN=' + token_urlsafe(32) + '\n'
    'APP_METRICS_TOKEN=' + token_urlsafe(32) + '\n'
    'APP_RATE_LIMIT=5\nAPP_RATE_WINDOW=5\n'
    'APP_DETECT_THRESHOLD=3\nAPP_DETECT_WINDOW=5\n',
    encoding='ascii',
)
p.chmod(0o600)
print('Protected environment created:', p)
PY
```

Короткие окна 5 с применяются **только для учебного сценария**. Если переменные не заданы, действуют значения по умолчанию (60 с).

```bash
set -a
source ~/.config/lab4/app.env
set +a
mkdir -p reports/lab4
python -m uvicorn src.webapp:app --host 127.0.0.1 --port 8000 --workers 1 --limit-concurrency 16 --timeout-keep-alive 5 --no-access-log --no-proxy-headers 2>&1 | tee reports/lab4/service.log
```

Оставить этот SSH-сеанс открытым. Во **втором PowerShell** организовать туннель:

```powershell
ssh -N -o ExitOnForwardFailure=yes -i "$env:USERPROFILE\.ssh\id_ed25519_lab1" -p 2222 -L 127.0.0.1:8001:127.0.0.1:8000 mluser@127.0.0.1
```

Открыть в Windows браузере **http://127.0.0.1:8001/**. Токен для ввода формы (посмотреть только лично, не фотографировать):

```bash
grep '^APP_API_TOKEN=' ~/.config/lab4/app.env
```

Ввести **значение после знака `=`**, не префикс `APP_API_TOKEN=`.

## Положительные и негативные проверки

Отдельный третий SSH-сеанс:

```bash
cd ~/ml-project
source .venv/bin/activate
set -a
source ~/.config/lab4/app.env
set +a
python -m pytest tests/test_lab4_api.py -q
python scripts/lab4_demo.py
```

Демонстрация автоматически делает: снимок нормального состояния `/health` и `/metrics`; 1 успешное предсказание; 5 неверных токенов, дающих 401 и 429; снимок метрик и правила детектирования; выдержку короткого окна; повторный успешный запрос; подтверждение сброса alert. Это **7 контролируемых запросов**, а не нагрузочное тестирование.

Файлы доказательств (токены в них не сохраняются):

- `reports/lab4/health_before.json`, `health_after.json`;
- `metrics_before.prom`, `metrics_after.prom`;
- `detection_before.json`, `detection_after.json`, `detection_recovered.json`;
- `scenario_summary.json` и поток структурированных логов в `service.log`.

Сводка `scenario_summary.json` должна содержать `"result": "PASS"`. Для сравнения метрик откройте файлы `metrics_before.prom` и `metrics_after.prom`, включая `lab4_requests_total`, `lab4_request_duration_seconds_*`, `lab4_rejections_total`. Метрики и логи отражают **отказы запросов API**, а не факт злоумышленной атаки или падения точности модели.

## Docker (после остановки локального Uvicorn)

```bash
sudo docker build --pull -t ml-project:lab4 .
sudo docker run -d --rm --name lab4-api --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m --cap-drop ALL --security-opt no-new-privileges --pids-limit 64 --memory 700m -p 127.0.0.1:8000:8000 --env-file "$HOME/.config/lab4/app.env" ml-project:lab4
curl -i http://127.0.0.1:8000/health
sudo docker exec lab4-api id -u
sudo docker logs --tail 20 lab4-api
sudo docker stop lab4-api
```

Внутри контейнера API слушает `0.0.0.0:8000`, но Docker публикует порт только на `127.0.0.1:8000` Ubuntu. В UFW не нужно открывать порт 8000; Windows получает доступ через SSH-туннель. Ожидаемый UID — `10001`.

## CI и доказательства

Workflow `.github/workflows/ci.yml` запускает старые этапы: pytest, Ruff, Bandit, pip-audit, Data Gate, Model Gate, Trivy, Security Gate и offline smoke. Добавлены API-тесты, Docker `/health`, HTTP `/predict`, защита `/metrics`, проверка UID. `APP_*_TOKEN` в CI генерируются случайно и действуют только для временного контейнера; production-секреты из Git не нужны.

Результат CI зависит от реального Docker build, сети пакетов и базы Trivy на дату запуска; нельзя считать его успешным до зелёного GitHub Actions. При новой уязвимости обновляют зависимости/образ и повторяют аудит **без отключения Security Gate**.

## Что приложить к отчёту

1. Скриншот `/` с правильным ответом и скрытым полем API-токена.
2. Скриншот страницы с обработанной ошибкой 401 либо 429.
3. Скриншот `pytest` с тестами API и полного набора.
4. Скриншот `/health` при готовой модели и теста неготовности при неверном SHA256.
5. Метрики «до» и «после», обезличенный фрагмент логов с кодами 401/429, `/detection` с `alert=true`.
6. Подтверждение восстановления: `/detection` `alert=false`, успешное предсказание после истечения окна.
7. Docker UID 10001, контейнерный `/health` и зелёный GitHub Actions с сохранёнными artifacts.

См. пошаговую инструкцию `START_HERE_LAB4_RU.md` и каркас отчёта `LAB4_REPORT_TEMPLATE.md`. Для добавления ссылки на ЛР4 в основной README выполнить `python3 scripts/link_lab4_readme.py`.
