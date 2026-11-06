#!/usr/bin/env python3
"""Add a non-destructive Lab 1 / Lab 2 project index to the existing root README."""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / 'README.md'
START = '<!-- LABS_OVERVIEW_BEGIN -->'
END = '<!-- LABS_OVERVIEW_END -->'

BLOCK = '''<!-- LABS_OVERVIEW_BEGIN -->
# Киберустойчивость систем искусственного интеллекта

**Единый учебный проект по компьютерному зрению: от защищённого окружения до оценки качества и устойчивости ML-модели.**

## Лабораторные работы

| Этап | Тема | Основные материалы |
|:--|:--|:--|
| **№ 1** | Подготовка защищённого окружения и исследование набора рукописных цифр | Описание **ниже на этой странице**, [ноутбук № 1](notebooks/01_digits_analysis.ipynb), [графики](reports/figures/) |
| **№ 2** | Построение базовой модели, оценка качества и проверка устойчивости входов | **[Описание, результаты и 7 рисунков](README_LAB2.md)**, [ноутбук № 2](notebooks/02_baseline_and_robustness.ipynb), [метрики](metrics/baseline.json), [тесты](tests/) |

## Основные результаты второго этапа

| Accuracy на тесте | Macro-F1 | Тестовая выборка | Автоматические тесты |
|:--:|:--:|:--:|:--:|
| **97,41 %** | **0,9740** | **348 изображений** | **33/33 пройдены** |

![Матрица ошибок базового классификатора на отложенной выборке](reports/figures/lab2_02_confusion_matrix.png)

*Матрица ошибок классификатора из ЛР № 2. Полный разбор результатов, значения Precision/Recall/F1 по классам и эксперимент с искажениями приведены в [описании второй лабораторной](README_LAB2.md).*

---

**Ниже сохранено исходное описание лабораторной работы № 1 с её иллюстрациями.**
<!-- LABS_OVERVIEW_END -->
'''


def main() -> None:
    if not README.is_file():
        raise SystemExit(f'Нет корневого README: {README}')

    required = [
        ROOT / 'README_LAB2.md',
        ROOT / 'notebooks/01_digits_analysis.ipynb',
        ROOT / 'notebooks/02_baseline_and_robustness.ipynb',
        ROOT / 'reports/figures/lab2_02_confusion_matrix.png',
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing:
        raise SystemExit('Сначала проверь наличие файлов: ' + ', '.join(missing))

    old = README.read_text(encoding='utf-8')
    backup = Path.home() / 'README_LAB1_BEFORE_NAVIGATION.md'
    if not backup.exists():
        shutil.copy2(README, backup)
        print(f'Сохранена резервная копия: {backup}')

    if START in old and END in old:
        a = old.index(START)
        b = old.index(END, a) + len(END)
        new = old[:a] + BLOCK.rstrip() + old[b:]
        print('Обновлён блок навигации; остальное содержимое не изменено.')
    elif START not in old and END not in old:
        new = BLOCK.rstrip() + '\n\n' + old
        print('В начало README добавлена навигация по лабораторным.')
    else:
        raise SystemExit('Найден один из маркеров навигации; README не изменён.')

    README.write_text(new, encoding='utf-8')
    print('README первой лабораторной и его изображения сохранены.')
    print(f'Результат: {README}')


if __name__ == '__main__':
    main()
