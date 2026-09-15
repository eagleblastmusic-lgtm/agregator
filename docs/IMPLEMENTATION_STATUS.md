# Faro Employer Discovery Engine — implementation status

Aktualny zakres PR obejmuje M0–M3 oraz warstwę pomiarową potrzebną do kontrolowanego benchmarku: enrichment kontaktów, agregację ofert, Company Resolution, dwuetapową weryfikację oficjalnej strony WWW i ręcznie etykietowane quality gates.

Szczegółowy plan i checkpointy: [`PLAN.md`](PLAN.md).

## Gotowe baseline'y

- M0: crawler + evidence + GREEN/REVIEW/IGNORE.
- M1: OLX, Jooble, Adzuna, source registry, resumowalne runy, katalog 91 źródeł, benchmark i pełny bundle eksportowy dla Faro.
- M2: konserwatywny Company Resolution v1, aliasy/lokalizacje, metody/confidence, ground truth, pairwise precision/recall/F1, fuzzy REVIEW bez automatycznego merge.
- M3: ranking wyników wyszukiwarki + first-party content verification z fallbackiem do kolejnych kandydatów.
- Quality benchmark: osobne ground truth i ewaluatory dla Company Resolution, wyboru oficjalnej domeny oraz klasyfikacji kontaktów.

## Kluczowe komendy jakościowe

```bash
agregator benchmark --db agregator.sqlite3
agregator resolution-review --db agregator.sqlite3 --min-score 0.82 --limit 100

agregator export-quality-labels \
  --db agregator.sqlite3 \
  --output-dir benchmark/labels \
  --job-limit 1000 \
  --company-limit 1000 \
  --contact-limit 1000

agregator evaluate-resolution \
  --db agregator.sqlite3 \
  --path benchmark/labels/company_resolution_truth.csv

agregator evaluate-website \
  --db agregator.sqlite3 \
  --path benchmark/labels/website_resolution_truth.csv

agregator evaluate-contacts \
  --db agregator.sqlite3 \
  --path benchmark/labels/contact_classification_truth.csv

agregator quality-gate \
  --db agregator.sqlite3 \
  --resolution-truth benchmark/labels/company_resolution_truth.csv \
  --website-truth benchmark/labels/website_resolution_truth.csv \
  --contact-truth benchmark/labels/contact_classification_truth.csv \
  --fail-on-error

agregator export-dataset --db agregator.sqlite3 --output-dir export/faro
```

## Co mierzy quality gate

- Company Resolution: pairwise TP/FP/FN/TN oraz precision/recall/F1.
- Oficjalna WWW: poprawny host, błędny host, false positive, false negative, precision/recall/F1 i accuracy. `__none__` oznacza ręcznie potwierdzony brak oficjalnej strony.
- Kontakty: macierz pomyłek GREEN/REVIEW/IGNORE, accuracy, per-class precision/recall/F1, macro F1 oraz opcjonalną zgodność `purpose`.

Domyślne progi `quality-gate` to:

- Company Resolution F1 >= 0.95,
- Website Resolution F1 >= 0.95,
- Contact decision macro F1 >= 0.90.

Progi są parametrami CLI i przed zamrożeniem produkcyjnym powinny zostać potwierdzone na realnym, ręcznie oznaczonym benchmarku.

## Cel najbliższego benchmarku

Próbka 1000 ofert ma dostarczyć danych do kalibracji:

- precision/recall/F1 Company Resolution,
- jakości fuzzy REVIEW,
- precision/recall wyboru oficjalnej domeny,
- udziału firm z poprawnym enrichmentem,
- jakości GREEN/REVIEW/IGNORE,
- kosztu/czasu per źródło i per firma.

## Granice automatyzacji

- fuzzy podobieństwo nazw nie scala firm automatycznie,
- domena WWW jest mocnym sygnałem REVIEW, ale auto-merge wymaga wcześniejszej walidacji na ground truth,
- quality gate nie zastępuje ręcznego labelingu — mierzy jakość względem etykiet,
- źródła partnerskie/API nie są zastępowane obchodzeniem uwierzytelniania lub zabezpieczeń,
- outreach pozostaje poza zakresem repo.
