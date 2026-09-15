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

Po instalacji projektu dostępna jest osobna komenda:

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

Domyślny `target_jobs=1000` oznacza całkowitą liczbę ofert w bazie benchmarkowej. Jeżeli baza zawiera już co najmniej target, etap collection kończy się jako `target_already_reached` i workflow przechodzi dalej.

`--fresh-collection` resetuje kursory wybranych źródeł, ale nie kasuje istniejących rekordów z bazy. Do całkowicie nowego benchmarku najlepiej użyć nowej ścieżki SQLite.

## Enrichment

Firmy są pobierane do enrichmentu partiami. Domyślnie kwalifikują się rekordy z `identity_confidence >= 0.7` i bez wcześniejszego `enriched_at`.

Workflow ma dwa zabezpieczenia przed zapętleniem:

- `--max-enrichment-companies` ogranicza liczbę wybranych prób enrichmentu,
- jeżeli cała wybrana partia kończy się błędem, run zatrzymuje enrichment z `batch_all_failed` zamiast powtarzać w nieskończoność te same firmy.

Nieudane firmy pozostają pending i mogą zostać ponowione w kolejnym uruchomieniu po naprawieniu konfiguracji lub problemu sieciowego.

## Struktura workspace

Przykładowy wynik:

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

`benchmark_run_manifest.json` zapisuje konfigurację runu, wynik collection, zagregowane statystyki enrichmentu, pełny raport benchmarku, wynik eksportu snapshotów oraz ścieżki eksportów.

## Offline evidence stron WWW

`website_page_snapshots.csv` jest tworzony z append-only audit trailu, bez ponownego pobierania stron. Dla automatycznego website resolution preferowane są snapshoty zapisane przy poszczególnych `WebsiteVerificationAttempt`, dzięki czemu plik obejmuje także kandydatów odrzuconych przed wyborem poprawnej domeny.

Każdy wiersz może zawierać m.in.:

- `verification_id` i `company_id`,
- finalne `resolution_origin` i `resolution_source`,
- URL sprawdzanego kandydata i informację, czy został zaakceptowany,
- provenance próby (`attempt_origin`, `attempt_source`),
- URL konkretnej strony,
- kod HTTP,
- SHA-256 treści,
- tekstowy excerpt zapisany w chwili weryfikacji,
- timestamp runu.

Jeżeli run nie posiada listy prób, np. dla jawnie podanego znanego URL, exporter używa run-level `page_snapshots_json`. Dzięki temu ręczny audyt domen nie musi zależeć od tego, czy strona nadal wygląda tak samo w późniejszym terminie.

## Następny krok: ręczny ground truth

Po wykonaniu benchmarku nie należy automatycznie podnosić progów ani rozszerzać auto-merge. Najpierw należy ręcznie oznaczyć pliki w `labels/`:

- `company_resolution_truth.csv`,
- `website_resolution_truth.csv`,
- `contact_classification_truth.csv`.

Przy oznaczaniu domen można wspierać się `website_page_snapshots.csv` i `website_verification_runs.csv`, aby zobaczyć nie tylko finalną domenę, ale również odrzucone kandydatury i evidence z momentu runu.

Następnie można uruchomić istniejący `quality-gate`:

```bash
agregator quality-gate \
  --db benchmark/benchmark.sqlite3 \
  --resolution-truth benchmark/run/labels/company_resolution_truth.csv \
  --website-truth benchmark/run/labels/website_resolution_truth.csv \
  --contact-truth benchmark/run/labels/contact_classification_truth.csv \
  --fail-on-error
```

Dopiero wyniki ground truth powinny decydować o zmianach w Company Resolution, website verification i klasyfikacji GREEN/REVIEW/IGNORE.
