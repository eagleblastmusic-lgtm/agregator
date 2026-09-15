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
    -> offline snapshoty stron i timeline evidence
    -> deterministycznie próbkowany pakiet do ręcznego ground truth
```

Nie wykonuje outreachu ani wysyłki wiadomości.

## Wymagania

Pełny benchmark wymaga skonfigurowanego wyszukiwania WWW:

```text
BRAVE_SEARCH_API_KEY=...
```

Źródła `jooble`, `adzuna`, `careerjet` i `epraca` wymagają dodatkowo własnych danych konfiguracyjnych opisanych w `.env.example` i README. Źródła bez wymaganej konfiguracji są przez kolektor oznaczane jako wyłączone; nie są zastępowane scrapingiem obchodzącym autoryzację.

Przed realnym runem można wykonać preflight bez ujawniania wartości sekretów:

```bash
agregator-benchmark preflight \
  --sources olx,jooble,adzuna \
  --strict
```

## Uruchomienie

```bash
agregator-benchmark run \
  --db benchmark/benchmark.sqlite3 \
  --output-dir benchmark/run \
  --sources olx,jooble,adzuna \
  --target-jobs 1000 \
  --max-rounds 100 \
  --enrichment-batch-size 25 \
  --max-enrichment-companies 1000 \
  --label-sampling-seed faro-ground-truth-v1
```

`target_jobs=1000` oznacza całkowitą liczbę ofert w bazie benchmarkowej. Jeżeli baza ma już co najmniej target, collection kończy się jako `target_already_reached` i workflow idzie dalej.

`--fresh-collection` resetuje kursory wybranych źródeł, ale nie kasuje rekordów z bazy. Do całkowicie nowego benchmarku najlepiej użyć nowej ścieżki SQLite.

`--label-sampling-seed` steruje deterministycznym doborem rekordów do ręcznego ground truth. Ten sam dataset, te same limity i ten sam seed dają tę samą próbkę. Seed jest zapisywany w `benchmark_run_manifest.json` oraz `labels/sampling_manifest.json`.

### Tryb strict

```bash
agregator-benchmark run ... --strict
```

Tryb `--strict` nadal zapisuje raporty i manifest, ale kończy proces kodem `2`, jeśli nie osiągnięto `target_jobs` albo enrichment nie zakończył się stanem `no_pending_companies`.

`benchmark_run_manifest.json` zawiera `readiness`: `collection_target_reached`, `enrichment_complete`, `dataset_exported`, `ground_truth_templates_generated`, `ready_for_manual_labeling`, `manual_ground_truth_required` oraz `blockers`.

`ready_for_manual_labeling=true` nie oznacza przejścia quality gate. Oznacza tylko, że techniczny run jest kompletny i można rozpocząć ręczne oznaczanie ground truth.

## Enrichment

Firmy są pobierane partiami. Domyślnie kwalifikują się rekordy z `identity_confidence >= 0.7` i bez wcześniejszego `enriched_at`.

Workflow ma dwa zabezpieczenia przed zapętleniem:

- `--max-enrichment-companies` ogranicza liczbę prób enrichmentu,
- jeżeli cała wybrana partia kończy się błędem, run zatrzymuje enrichment z `batch_all_failed`.

Nieudane firmy pozostają pending i mogą zostać ponowione po naprawieniu konfiguracji lub problemu sieciowego.

Enrichment raportuje także `evidence_snapshots`, `evidence_observations` i `evidence_changes`. Snapshot jest immutable treścią evidence, obserwacja reprezentuje konkretny run, a `evidence_changes` zlicza przejścia do nowej wersji treści dla istniejącego kanału.

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
│   ├── contact_evidence_observations.csv
│   ├── website_page_snapshots.csv
│   └── manifest.json
└── labels/
    ├── company_resolution_truth.csv
    ├── website_resolution_truth.csv
    ├── contact_classification_truth.csv
    └── sampling_manifest.json
```

`dataset/manifest.json` ma schema version `7`. `benchmark_run_manifest.json` ma schema version `4` i zapisuje m.in. seed oraz ścieżkę do manifestu samplingu.

## Deterministyczny sampling ground truth

Eksport labeli nie bierze już po prostu pierwszych N rekordów z SQLite. Najpierw budowana jest pełna pula kandydatów, a następnie — jeśli populacja przekracza limit — dobierana jest próbka warstwowa.

Warstwy są definiowane osobno dla trzech zadań:

- Company Resolution: `source + resolution method + confidence band`,
- Website Resolution: `resolution origin + verification outcome + confidence band + obecność source website candidate`,
- Contact Classification: `kind + predicted decision + confidence band`.

Gdy budżet próbki na to pozwala, każda obserwowana warstwa dostaje co najmniej jeden rekord, a pozostały budżet jest dzielony proporcjonalnie do liczebności warstw. Remisy są rozstrzygane deterministycznym hashem zależnym od seeda.

Dla Company Resolution część próbki jest rezerwowana na **pairwise anchors**: po dwa rekordy z wybranych przewidywanych `company_id`, które mają co najmniej dwie oferty. Dzięki temu ewaluacja pairwise nie kończy się sztucznie na zbiorze złożonym wyłącznie z singletonów.

`labels/sampling_manifest.json` zapisuje:

- seed i nazwę strategii,
- rozmiar pełnej populacji i próbki dla każdego zadania,
- liczebność każdej warstwy przed i po samplingu,
- liczbę firm i wierszy wykorzystanych jako pairwise anchors dla Company Resolution.

Manifest samplingu jest elementem provenance benchmarku. Zmiana seeda jest dozwolona np. dla niezależnej próbki kontrolnej, ale przy porównywaniu dwóch wersji algorytmu należy zachować ten sam dataset, limity i seed.

## Offline evidence stron WWW

`website_page_snapshots.csv` powstaje z append-only audit trailu, bez ponownego pobierania stron. Dla automatycznego website resolution preferowane są snapshoty zapisane przy `WebsiteVerificationAttempt`, więc plik obejmuje również kandydatów odrzuconych przed wyborem poprawnej domeny.

Wiersz może zawierać `verification_id`, `company_id`, finalne `resolution_origin`/`resolution_source`, URL i wynik próby, `attempt_origin`/`attempt_source`, URL konkretnej strony, kod HTTP, SHA-256, tekstowy excerpt i timestamp.

Jeżeli run nie ma listy prób, np. dla jawnie podanego znanego URL, exporter używa run-level `page_snapshots_json`.

## Timeline evidence kontaktów

`contact_evidence_snapshots.csv` przechowuje deduplikowane immutable wersje tekstu evidence. `contact_evidence_observations.csv` zapisuje każdą obserwację kanału w konkretnym `website_verification_run_id` wraz z:

- `snapshot_id` i `content_sha256`,
- `decision`, `purpose` i `confidence` z danego runu,
- `evidence_url` i `evidence_signal`,
- `snapshot_changed`, które wskazuje zmianę treści względem poprzedniej obserwacji tego kanału,
- timestampem.

Dzięki temu można rozdzielić „kanał widziany ponownie bez zmian” od „evidence rzeczywiście się zmieniło” i audytować historyczne zmiany klasyfikacji bez nadpisywania poprzedniego stanu.

## Ground truth domen z provenance

`labels/website_resolution_truth.csv` zawiera poza `truth_domain` również `latest_verification_id`, `verification_outcome`, `predicted_resolution_origin`, `predicted_resolution_source`, `source_website_candidate_count` i `verification_signals_json`.

`latest_verification_id` pozwala powiązać wiersz labelingu z `website_page_snapshots.csv` i zobaczyć evidence zaakceptowanej domeny oraz wcześniejszych kandydatów odrzuconych przez verifier.

## Ground truth kontaktów z immutable evidence

`labels/contact_classification_truth.csv` przechowuje także:

- `latest_evidence_snapshot_id`,
- `evidence_content_sha256`,
- `evidence_captured_at`.

Ewaluator raportuje metryki globalne oraz `decision_by_kind`: osobne accuracy, macro F1, confusion matrix i per-class metrics dla `email` oraz `form`, o ile dany typ występuje w oznaczonej próbce.

## Postęp labelingu

Po wygenerowaniu pakietu można sprawdzać postęp bez uruchamiania quality gate:

```bash
agregator-benchmark status \
  --label-dir benchmark/run/labels
```

Do skryptów/CI można użyć:

```bash
agregator-benchmark status \
  --label-dir benchmark/run/labels \
  --strict
```

`--strict` zwraca kod `2`, dopóki wszystkie trzy pliki ground truth nie istnieją, mają prawidłową kolumnę etykiety, nie są puste i nie są w pełni oznaczone. `sampling_manifest.json` nie jest czwartym plikiem do ręcznego oznaczania — służy wyłącznie jako audit/provenance próbki.

## Następny krok: ręczny ground truth

Po benchmarku nie należy automatycznie podnosić progów ani rozszerzać auto-merge. Najpierw należy ręcznie oznaczyć:

- `company_resolution_truth.csv`,
- `website_resolution_truth.csv`,
- `contact_classification_truth.csv`.

Przed labelingiem warto sprawdzić `sampling_manifest.json`, czy istotne warstwy mają wystarczający support. Sam sampling nie gwarantuje statystycznej reprezentatywności dla każdej rzadkiej kategorii — jego zadaniem jest uniknięcie oczywistego biasu „pierwszych N rekordów” i zachowanie audytowalnego, powtarzalnego wyboru.

Gdy `agregator-benchmark status --strict` przejdzie, można wykonać zintegrowaną ewaluację:

```bash
agregator-benchmark evaluate \
  --db benchmark/benchmark.sqlite3 \
  --label-dir benchmark/run/labels \
  --fail-on-error
```

Alternatywnie pozostaje dostępne niskopoziomowe:

```bash
agregator quality-gate \
  --db benchmark/benchmark.sqlite3 \
  --resolution-truth benchmark/run/labels/company_resolution_truth.csv \
  --website-truth benchmark/run/labels/website_resolution_truth.csv \
  --contact-truth benchmark/run/labels/contact_classification_truth.csv \
  --fail-on-error
```

Dopiero ground truth powinien decydować o zmianach w Company Resolution, website verification i klasyfikacji GREEN/REVIEW/IGNORE.
