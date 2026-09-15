# Faro Employer Discovery Engine — implementation status

Aktualny zakres PR obejmuje M0–M3: enrichment kontaktów, agregację ofert, Company Resolution oraz dwuetapową weryfikację oficjalnej strony WWW.

Szczegółowy plan i checkpointy: [`PLAN.md`](PLAN.md).

## Gotowe baseline'y

- M0: crawler + evidence + GREEN/REVIEW/IGNORE.
- M1: OLX, Jooble, Adzuna, source registry, resumowalne runy, katalog 91 źródeł, benchmark i pełny bundle eksportowy dla Faro.
- M2: konserwatywny Company Resolution v1, aliasy/lokalizacje, metody/confidence, ground truth, pairwise precision/recall/F1, fuzzy REVIEW bez automatycznego merge.
- M3: ranking wyników wyszukiwarki + first-party content verification z fallbackiem do kolejnych kandydatów.

## Kluczowe komendy jakościowe

```bash
agregator benchmark --db agregator.sqlite3
agregator resolution-review --db agregator.sqlite3 --min-score 0.82 --limit 100
agregator export-ground-truth --db agregator.sqlite3 --output company_ground_truth.csv --limit 1000
agregator evaluate-resolution --db agregator.sqlite3 --path company_ground_truth.csv
agregator export-dataset --db agregator.sqlite3 --output-dir export/faro
```

## Cel najbliższego benchmarku

Próbka 1000 ofert ma dostarczyć danych do kalibracji:

- precision/recall/F1 Company Resolution,
- jakości fuzzy REVIEW,
- poprawności wyboru oficjalnej domeny,
- udziału firm z poprawnym enrichmentem,
- precision klasyfikacji GREEN/REVIEW/IGNORE,
- kosztu/czasu per źródło i per firma.

## Granice automatyzacji

- fuzzy podobieństwo nazw nie scala firm automatycznie,
- domena WWW jest mocnym sygnałem REVIEW, ale auto-merge wymaga wcześniejszej walidacji na ground truth,
- źródła partnerskie/API nie są zastępowane obchodzeniem uwierzytelniania lub zabezpieczeń,
- outreach pozostaje poza zakresem repo.
