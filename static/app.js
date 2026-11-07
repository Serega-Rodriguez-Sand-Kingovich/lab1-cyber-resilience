"use strict";
// Only DOM textContent is used for server-supplied values. Never use innerHTML.
const digitsZero = [
  [0,0,5,13,9,1,0,0], [0,0,13,15,10,15,5,0],
  [0,3,15,2,0,11,8,0], [0,4,12,0,0,8,8,0],
  [0,5,8,0,0,9,8,0], [0,4,11,0,1,12,7,0],
  [0,2,14,5,10,12,0,0], [0,0,6,13,10,0,0,0]
];
let pixels = Array.from({length: 8}, () => Array(8).fill(0));
const grid = document.getElementById("pixels");
const status = document.getElementById("status");
const digit = document.getElementById("digit");
const version = document.getElementById("version");
const requestId = document.getElementById("request-id");
const send = document.getElementById("send");

function update() {
  grid.replaceChildren();
  for (let r = 0; r < 8; r += 1) {
    for (let c = 0; c < 8; c += 1) {
      const cell = document.createElement("button");
      cell.type = "button";
      cell.className = "pixel";
      const value = pixels[r][c];
      cell.classList.add(`intensity-${value}`);
      cell.title = `Строка ${r + 1}, столбец ${c + 1}: ${value}`;
      cell.setAttribute("aria-label", cell.title);
      cell.addEventListener("click", () => {
        pixels[r][c] = (pixels[r][c] + 4) % 20;
        if (pixels[r][c] > 16) pixels[r][c] = 0;
        update();
      });
      cell.addEventListener("contextmenu", event => {
        event.preventDefault();
        pixels[r][c] = 0;
        update();
      });
      grid.append(cell);
    }
  }
  document.getElementById("json-preview").textContent = JSON.stringify({pixels}, null, 1);
}

function setStatus(message, isError = false) {
  status.textContent = message;
  status.className = isError ? "error" : "";
}

async function checkHealth() {
  const badge = document.getElementById("health");
  try {
    const response = await fetch("/health", {cache: "no-store"});
    const data = await response.json();
    badge.textContent = response.ok && data.status === "healthy" ? "Сервис готов" : "Сервис не готов (HTTP 503)";
    badge.className = response.ok ? "pill good" : "pill bad";
  } catch (_) {
    badge.textContent = "Нет соединения";
    badge.className = "pill bad";
  }
}

document.getElementById("sample").addEventListener("change", async (event) => {
  const number = event.target.value;
  if (number === "") return;

  try {
    const response = await fetch("/static/digit_examples.json");
    if (!response.ok) throw new Error("Load failed");

    const examples = await response.json();
    const selected = examples[number];

    if (!Array.isArray(selected) || selected.length !== 8 ||
        !selected.every(row => Array.isArray(row) &&
          row.length === 8 && row.every(v =>
            Number.isInteger(v) && v >= 0 && v <= 16))) {
      throw new Error("Invalid example");
    }

    pixels = selected.map(row => row.slice());
    update();
    digit.textContent = "—";
    version.textContent = "—";
    requestId.textContent = "—";
    setStatus("");
  } catch (_) {
    setStatus("Не удалось загрузить пример.", true);
  }
});

document.getElementById("clear").addEventListener("click", () => {
  pixels = Array.from({length: 8}, () => Array(8).fill(0));
  update();
  setStatus("");
});

send.addEventListener("click", async () => {
  const tokenField = document.getElementById("token");
  const token = tokenField.value;
  digit.textContent = "—";
  version.textContent = "—";
  requestId.textContent = "—";
  if (!token) {
    setStatus("Введите токен.", true);
    return;
  }
  send.disabled = true;
  setStatus("Проверка входа и предсказание…");
  try {
    const response = await fetch("/predict", {
      method: "POST",
      headers: {"Authorization": `Bearer ${token}`, "Content-Type": "application/json"},
      body: JSON.stringify({pixels}),
      cache: "no-store"
    });
    const data = await response.json();
    requestId.textContent = data.request_id || "—";
    if (!response.ok) {
      const descriptions = {
        401: "Нет доступа: проверьте API-токен.",
        413: "Слишком большой запрос.",
        415: "Неподдерживаемый формат.",
        422: "Неверные значения: требуются 8 × 8 чисел от 0 до 16.",
        429: "Слишком много запросов. Повторите после окончания окна лимита.",
        503: "Сервис занят или модель не готова."
      };
      setStatus(descriptions[response.status] || `Ошибка HTTP ${response.status}.`, true);
      return;
    }
    digit.textContent = String(data.prediction);
    version.textContent = String(data.model_version);
    setStatus("");
  } catch (_) {
    setStatus("Сетевая ошибка: не удалось получить ответ от сервиса.", true);
  } finally {
    send.disabled = false;
  }
});

update();
checkHealth();
document.getElementById("sample").dispatchEvent(new Event("change"));
