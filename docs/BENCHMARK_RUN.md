# Faro — kontrolowany benchmark end-to-end

Ten workflow służy do uruchomienia jednego powtarzalnego przebiegu:

```text
zbieranie ofert
    -> Company Resolution
    -> enrichment firm
    -> weryfikacja oficjalnych WWW
    -> crawl kontaktów
    -> raport benchmarku
    -> eksport datasetu
    -> offline snapshoty stron
    -> pakiet do ręcznego ground truth
```

Nie wykonuje outreachu ani wysyłki wiadomości.

## Wymagania

Pełny benchmark wymaga skonfigurowanego wyszukiwania WWW:

```text
BRAVE_SEARCH_API_KEY=...
```

Źródła `jooble`, `adzuna`, `careerjet` i `epraca` wymagają dodatkowo własnych danych konfiguracyjnych opisanych w `.env.example` i README. Źródła bez wymaganej konfiguracji są przez kolektor oznaczane jako wyłączone; nie są zastępowane scrapingiem obchodzącym autoryzację.

## Uruchomienie

```bash
agregator-benchmark run \
  --db benchmark/benchmark.sqlite3 \
  --output-dir benchmark/run \
  --sources olx,jooble,adzuna \
  --target-jobs 1000 \
  --max-rounds 100 \
  --enrichment-batch-size 25 \
  --max-enrichment-companies 1000
```

`target_jobs=1000` oznacza całkowitą liczbę ofert w bazie benchmarkowej. Jeżeli baza ma już co najmniej target, collection kończy się jako `target_already_reached` i workflow idzie dalej.

`--fresh-collection` resetuje kursory wybranych źródeł, ale nie kasuje rekordów z bazy. Do całkowicie nowego benchmarku najlepiej użyć nowej ścieżki SQLite.

### Tryb strict

Do formalnego gate przed ręcznym labelingiem można dodać:

```bash
agregator-benchmark run ... --strict
```

Tryb `--strict` nadal zapisuje raporty i manifest, ale kończy proces kodem `2`, jeśli nie osiągnięto `target_jobs` albo enrichment nie zakończył się stanem `no_pending_companies`.

`benchmark_run_manifest.json` zawiera strukturę `readiness`: `collection_target_reached`, `enrichment_complete`, `dataset_exported`, `ground_truth_templates_generated`, `ready_for_manual_labeling`, `manual_ground_truth_required` oraz `blockers`.

`ready_for_manual_labeling=true` nie oznacza przejścia quality gate. Oznacza tylko, że techniczny run jest kompletny i można rozpocząć ręczne oznaczanie ground truth.

## Enrichment

Firmy są pobierane partiami. Domyślnie kwalifikują się rekordy z `identity_confidence >= 0.7` i bez wcześniejszego `enriched_at`.

Workflow ma dwa zabezpieczenia przed zapętleniem:

- `--max-enrichment-companies` ogranicza liczbę prób enrichmentu,
- jeżeli cała wybrana partia kończy się błędem, run zatrzymuje enrichment z `batch_all_failed`.

Nieudane firmy pozostają pending i mogą zostać ponowione po naprawieniu konfiguracji lub problemu sieciowego.

## Struktura workspace

```text
benchmark/run/
├── collection.json
├── enrichment.json
├── benchmark_report.json
├── benchmark_run_manifest.json
├── dataset/
│   ├── companies.csv
│   ├── job_postings.csv
│   ├── company_identifiers.csv
│   ├── company_website_candidates.csv
│   ├── contact_channels.csv
│   ├── website_verification_runs.csv
│   ├── contact_evidence_snapshots.csv
│   ├── website_page_snapshots.csv
│   └── manifest.json
└── labels/
    ├── company_resolution_truth.csv
    ├── website_resolution_truth.csv
    └── contact_classification_truth.csv
```

`dataset/manifest.json` ma schema version `6`. `website_page_snapshots.csv` jest formalną częścią datasetu.

## Offline evidence stron WWW

`website_page_snapshots.csv` powstaje z append-only audit trailu, bez ponownego pobierania stron. Dla automatycznego website resolution preferowane są snapshoty zapisane przy `WebsiteVerificationAttempt`, więc plik obejmuje również kandydatów odrzuconych przed wyborem poprawnej domeny.

Wiersz może zawierać `verification_id`, `company_id`, finalne `resolution_origin`/`resolution_source`, URL i wynik próby, `attempt_origin`/`attempt_source`, URL konkretnej strony, kod HTTP, SHA-256, tekstowy excerpt i timestamp.

Jeżeli run nie ma listy prób, np. dla jawnie podanego znanego URL, exporter używa run-level `page_snapshots_json`.

## Ground truth domen z provenance

`labels/website_resolution_truth.csv` zawiera poza `truth_domain` również `latest_verification_id`, `verification_outcome`, `predicted_resolution_origin`, `predicted_resolution_source`, `source_website_candidate_count` i `verification_signals_json`.

`latest_verification_id` pozwala powiązać wiersz labelingu z `website_page_snapshots.csv` i zobaczyć evidence zaakceptowanej domeny oraz wcześniejszych kandydatów odrzuconych przez verifier.

## Następny krok: ręczny ground truth

Po benchmarku nie należy automatycznie podnosić progów ani rozszerzać auto-merge. Najpierw należy ręcznie oznaczyć:

- `company_resolution_truth.csv`,
- `website_resolution_truth.csv`,
- `contact_classification_truth.csv`.

Następnie:

```bash
agregator quality-gate \
  --db benchmark/benchmark.sqlite3 \
  --resolution-truth benchmark/run/labels/company_resolution_truth.csv \
  --website-truth benchmark/run/labels/website_resolution_truth.csv \
  --contact-truth benchmark/run/labels/contact_classification_truth.csv \
  --fail-on-error
```

Dopiero ground truth powinien decydować o zmianach w Company Resolution, website verification i klasyfikacji GREEN/REVIEW/IGNORE.
