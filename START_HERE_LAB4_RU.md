# ЛР №4. Инструкция с нуля для Windows PowerShell + Ubuntu VirtualBox

Выполняй **по порядку**. Где указано PowerShell — это Windows. Где указано Ubuntu — команды вводятся **после SSH-подключения**. Символ `$` или `mluser@...` в начале строки терминала копировать не нужно.

## 0. Состав работы

Мы не переустанавливаем Ubuntu и не обучаем новую модель. Продолжаем `/home/mluser/ml-project`: ЛР1 — безопасная среда и цифры, ЛР2 — модель, ЛР3 — тесты и CI, ЛР4 — сервер, веб-форма, защита запросов, мониторинг и Docker.

## 1. Включить Ubuntu

Windows → Oracle VirtualBox → **CyberAI-Ubuntu** → Start. Дождаться загрузки. Если Ubuntu уже работает, повторно создавать VM не надо.

## 2. Подключиться через PowerShell (окно №1)

Windows: `Win + R` → `powershell` → Enter. Вставь **одну** команду:

```powershell
ssh -i "$env:USERPROFILE\.ssh\id_ed25519_lab1" -p 2222 mluser@127.0.0.1
```

Если запросит `Enter passphrase for key`, вводишь парольную фразу ключа, не пароль GitHub. Теперь все команды в этом окне выполняются в Ubuntu.

## 3. Проверить старую работу (Ubuntu, окно №1)

```bash
whoami
cd ~/ml-project
pwd
git status -sb
git branch --show-current
sha256sum -c integrity/model.sha256
sha256sum -c integrity/datasets.sha256
```

Ожидается `mluser`, `/home/mluser/ml-project`, а для контрольных сумм — `OK`. Если хэш `FAILED`, **остановись**: не меняй модель и не обновляй checksum, сначала выясни причину.

## 4. Создать новую ветку (Ubuntu, окно №1)

Сначала убедись, что `git status -sb` не показывает несохранённых изменений. Если состояние чистое:

```bash
cd ~/ml-project
git switch main
git pull --ff-only
git switch -c lab4-api
```

Если увидишь, что `lab4-api` уже существует, не создавай повторно: `git switch lab4-api`. Новая ветка нужна, чтобы прежние ЛР не пострадали.

## 5. Передать архив проекта из Windows

Скачай `lab4_patch.zip` из ответа ChatGPT в **Загрузки/Downloads**. Архив лежит на Windows, не в Ubuntu.

Открой **НОВОЕ окно Windows PowerShell №2** (не закрывай SSH №1). Выполни:

```powershell
scp -i "$env:USERPROFILE\.ssh\id_ed25519_lab1" -P 2222 "$env:USERPROFILE\Downloads\lab4_patch.zip" mluser@127.0.0.1:~/lab4_patch.zip
```

Если Windows сохранила его с суффиксом `(1)`, укажи фактическое имя. Содержимое архива никак не связано с SSH-ключом; ключ остаётся в Windows.

Снова **Ubuntu, окно №1**:

```bash
ls -lh ~/lab4_patch.zip
sudo apt install -y unzip
unzip -l ~/lab4_patch.zip | head -n 30
unzip -o ~/lab4_patch.zip -d ~/ml-project
cd ~/ml-project
python3 scripts/link_lab4_readme.py
git status -sb
```

`unzip -o` заменяет только перечисленные файлы новой ветки. Существующая модель и CSV не входят в архив и не должны измениться.

## 6. Подготовить Python (Ubuntu, окно №1)

```bash
cd ~/ml-project
source .venv/bin/activate
python --version
python -m pip install -r requirements-runtime.txt -r requirements-ci.txt
python -m pip check
python -m pytest tests/test_lab4_api.py -q
python -m pytest tests/ -q
sha256sum -c integrity/model.sha256
```

Проверки должны завершиться **без ошибок**. Количество тестов может быть больше 75 из ЛР3: добавлен набор ЛР4. При ошибке пришли точный вывод команды — не отключай тест, чтобы получить зелёный статус.

## 7. Создать секреты отдельно от Git (Ubuntu, окно №1)

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
print('Created:', p)
PY
```

Эти 5-секундные лимиты специально для безопасной демонстрации. Файл **не в проекте**, в Git его не добавляем. Никому не отправляй его содержимое, не фотографируй открытый токен.

## 8. Запустить веб-сервер (Ubuntu, окно №1)

```bash
set -a
source ~/.config/lab4/app.env
set +a
mkdir -p reports/lab4
python -m uvicorn src.webapp:app --host 127.0.0.1 --port 8000 --workers 1 --limit-concurrency 16 --timeout-keep-alive 5 --no-access-log --no-proxy-headers 2>&1 | tee reports/lab4/service.log
```

Окно №1 **оставь работающим**. Когда появится `Uvicorn running on http://127.0.0.1:8000`, сервер запущен. Чтобы остановить позже, нажми `Ctrl + C` именно в этом окне.

## 9. Открыть сайт из Windows (PowerShell, окно №2)

После передачи архива команда `scp` завершится. В этом же окне Windows PowerShell запусти туннель:

```powershell
ssh -N -o ExitOnForwardFailure=yes -i "$env:USERPROFILE\.ssh\id_ed25519_lab1" -p 2222 -L 127.0.0.1:8001:127.0.0.1:8000 mluser@127.0.0.1
```

**Окно №2 оставь открытым**. Запущенная команда может не выводить ничего — это нормально, туннель работает.

В браузере Windows открой: **http://127.0.0.1:8001/**.

Сайт должен показать статус «Сервис готов». Нажми «Пример цифры 0». В поле «API-токен» нужно вставить только значение после `=` из файла Ubuntu. Чтобы его увидеть, открой **новое PowerShell №3**, снова SSH (команда из шага 2), затем в Ubuntu:

```bash
grep '^APP_API_TOKEN=' ~/.config/lab4/app.env
```

Не публикуй токен и не снимай скриншот этой команды. Вставь токен в поле на сайте и нажми «Распознать цифру» — должна появиться цифра и request_id.

## 10. Автоматическая проверка и обнаружение (Ubuntu, окно №3)

```bash
cd ~/ml-project
source .venv/bin/activate
set -a
source ~/.config/lab4/app.env
set +a
sleep 6  # дождаться сброса лимита после ручной проверки через сайт
python scripts/lab4_demo.py
cat reports/lab4/scenario_summary.json
```

Демонстрация делает 1 корректный запрос, серию из 5 неверных токенов (401, затем 429), показывает `alert=true`, ждёт 6 с, повторяет корректный запрос и показывает `alert=false`. Итог должен содержать `"result": "PASS"`. На свой сервис идёт **малое количество запросов**, не нагрузочная атака.

Сохрани доказательства в `reports/lab4/` и сфотографируй/зафиксируй выход скрипта. В терминале сервера (окно №1) появляются обезличенные JSON-логи. Примеры:

```bash
grep '"status":401' reports/lab4/service.log | head -n 3
grep '"status":429' reports/lab4/service.log | head -n 3
```

## 11. Собрать Docker (Ubuntu, окно №3)

Теперь **останови Uvicorn в окне №1 сочетанием `Ctrl + C`**, иначе будет занят порт 8000. В окне №3:

```bash
cd ~/ml-project
sudo docker build --pull -t ml-project:lab4 .
sudo docker run -d --rm --name lab4-api --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m --cap-drop ALL --security-opt no-new-privileges --pids-limit 64 --memory 700m -p 127.0.0.1:8000:8000 --env-file "$HOME/.config/lab4/app.env" ml-project:lab4
curl -i http://127.0.0.1:8000/health
sudo docker exec lab4-api id -u
sudo docker logs --tail 20 lab4-api
```

HTTP `/health` должен вернуть 200, UID — 10001. Сайт в браузере (туннель PowerShell №2) теперь обслуживает контейнер. После скриншотов останови:

```bash
sudo docker stop lab4-api
```

## 12. Сохранить в Git и запустить GitHub Actions (Ubuntu, окно №3)

```bash
cd ~/ml-project
git status -sb
git diff --check
git add README.md .gitignore .dockerignore Dockerfile requirements-runtime.txt requirements-ci.txt .github/workflows/ci.yml src/webapp.py static/ scripts/docker_api_smoke.py scripts/lab4_demo.py scripts/link_lab4_readme.py tests/test_lab4_api.py README_LAB4.md START_HERE_LAB4_RU.md LAB4_REPORT_TEMPLATE.md
git diff --cached --check
git diff --cached --stat
git commit -m "feat: add secure digits API, UI and monitoring for lab4"
git push -u origin lab4-api
```

Перейди в GitHub → твой репозиторий → Actions → выбери последний workflow. Он должен пройти тесты, quality gates, Docker, Trivy и HTTP smoke. Если какой-то этап красный, **не утверждай успешный CI**, а посмотри лог и исправь причину. После зелёного запуска можно создать Pull Request `lab4-api → main` и слить по стандартному процессу.

## 13. Что обязательно сдать

Репозиторий + README, скрин сайта с результатом и с обработанной ошибкой, полные тесты и минимум 5 негативных проверок, hash/health при неготовности, метрики до/после, обезличенные логи, detection alert+recovery, доказательство Docker UID 10001 и зелёного GitHub Actions. Отчёт по структуре `LAB4_REPORT_TEMPLATE.md`.

## Если что-то не работает

| Симптом | Причина и действие |
|---|---|
| `ssh: connect ... Connection refused` | Включи CyberAI-Ubuntu и проверь VirtualBox NAT forwarding Windows 127.0.0.1:2222 → Ubuntu :22 |
| `Permission denied (publickey)` | Проверь путь к `id_ed25519_lab1`, используй именно пользователя `mluser`, парольный SSH специально отключён |
| `source: ... No such file` | Сначала `cd ~/ml-project`; если `.venv` отсутствует — проверь, что это исходная VM и проект не удалён |
| `Address already in use: 8000` | Старый Uvicorn или Docker ещё работает; останови предыдущий процесс, не открывай лишние порты UFW |
| `/health` даёт 503 | Сравни `sha256sum -c integrity/model.sha256`, проверь `metrics/baseline.json`, файл модели и установленное окружение |
| Сайт открывается, но `401` | Токен не введён или неверен; копируй только значение после `APP_API_TOKEN=` |
| `429` | Достигнут ограничитель запросов; для демонстрации подожди 6 с и попробуй ещё раз |
| В GitHub падает pip-audit/Trivy | Не отключай gate; найди конкретный CVE и проверь совместимую версию исправления |
| В GitHub ошибка при публикации workflow | В ЛР3 использовался GitHub CLI с правом `workflow`; повтори авторизацию, если её срок истёк |
