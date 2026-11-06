"""Add Lab 4 navigation to the original README without replacing Lab 1-3 text."""

from pathlib import Path


def main() -> int:
    readme = Path("README.md")
    text = readme.read_text(encoding="utf-8")
    if "README_LAB4.md" in text:
        print("README already links Lab 4")
        return 0
    rows = text.splitlines(keepends=True)
    for index, line in enumerate(rows):
        if line.startswith(("| № 3 |", "| **№ 3** |")):
            rows.insert(index + 1,
                "| **№ 4** | Защищённый API, веб-интерфейс и мониторинг | "
                "[Описание и инструкция](README_LAB4.md), "
                "[API](src/webapp.py), [тесты](tests/test_lab4_api.py) |\n")
            readme.write_text("".join(rows), encoding="utf-8")
            print("Added Lab 4 navigation link to README.md")
            return 0
    print("No known Lab 3 row found; README.md left unchanged")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
