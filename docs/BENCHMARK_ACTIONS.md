# Faro — Controlled Benchmark w GitHub Actions

Repo zawiera manualny workflow:

```text
.github/workflows/controlled-benchmark.yml
```

Workflow **nie uruchamia się automatycznie** na push/PR ani według harmonogramu. Jest dostępny wyłącznie przez `workflow_dispatch`, dzięki czemu pełny benchmark i potencjalnie płatne API nie są wywoływane przypadkowo.

## Kiedy użyć

Po merge workflow do gałęzi domyślnej i po skonfigurowaniu wymaganych GitHub Actions Secrets można uruchomić kontrolowany benchmark bez przygotowywania lokalnego środowiska Python.

Domyślne parametry:

```text
sources=olx,jooble,adzuna
target_jobs=1000
max_rounds=100
max_enrichment_companies=1000
label_sampling_seed=faro-ground-truth-v1
```

## Secrets

Workflow przekazuje do procesu tylko standardowe zmienne konfiguracyjne używane przez aplikację:

```text
BRAVE_SEARCH_API_KEY
JOOBLE_API_KEY
ADZUNA_APP_ID
ADZUNA_APP_KEY
CAREERJET_API_KEY
CAREERJET_REFERER
CAREERJET_USER_IP
CAREERJET_USER_AGENT
EPRACA_PARTNER
```

Należy skonfigurować wyłącznie sekrety potrzebne dla źródeł wybranych w `sources`. `BRAVE_SEARCH_API_KEY` jest wymagany przez pełny enrichment/search benchmark.

Workflow nie wypisuje wartości sekretów. Pierwszym krokiem merytorycznym jest `agregator-benchmark preflight --strict`; jeśli wybrane źródło nie ma wymaganej konfiguracji, właściwy benchmark nie startuje.

## Przebieg

```text
manual dispatch
   │
   ▼
install
   │
   ▼
initialize benchmark workspace
   │
   ▼
preflight --strict
   │
   ├── FAIL -> zapisz preflight.json + exit code -> artifact -> FAIL workflow
   │
   └── PASS
          │
          ▼
controlled benchmark --strict
          │
          ▼
source diagnostics
          │
          ▼
upload workspace artifact
          │
          ▼
enforce exit code
```

Workspace jest inicjalizowany **przed** preflightem. Dzięki temu nawet błąd konfiguracji pozostawia audytowalny artifact z `preflight.json`, `preflight_exit_code.txt` i informacją, że właściwy run został pominięty.

Sam run benchmarku zapisuje swój kod wyjścia do `benchmark/exit_code.txt`. Standardowy JSON zwracany przez CLI trafia do `benchmark/run_result.json`; właściwe dane benchmarku są nadal zapisywane w `benchmark/run/` przez samą aplikację.

## Source diagnostics

Po utworzeniu bazy workflow uruchamia:

```bash
agregator-benchmark source-diagnostics \
  --db benchmark/benchmark.sqlite3
```

Wynik trafia do:

```text
benchmark/source_diagnostics.json
```

Sekcja `identity` opisuje jakość rekordów ofertowych per źródło, m.in. confidence nazwy firmy, confidence Company Resolution, coverage miasta/opisu i rozkład metod resolution.

Sekcja `provenance` odpowiada na inne pytanie: **które źródło faktycznie dostarczyło jawne dane pracodawcy**, np. NIP/REGON lub kandydat oficjalnej strony WWW. W tym celu silnik utrzymuje osobne observation tables:

```text
company_identifier_observations
company_website_candidate_observations
```

Każda obserwacja zachowuje jednocześnie:

```text
job_source
+ evidence_source
+ company_id
+ wartość / URL
+ confidence
+ observation_count
```

Dzięki temu, jeśli dwie integracje dostarczą ten sam NIP lub tę samą stronę firmy, obie dostają własny credit w diagnostyce. Nie trzeba zgadywać źródła na podstawie ogólnego pola typu `official_feed.nip`.

Przykładowe metryki provenance per źródło:

```text
identifier_observations
identifiers
companies_with_identifiers
identifier_company_rate
identifier_kinds
identifier_evidence_sources
website_candidate_observations
website_candidates
companies_with_website_candidates
website_candidate_company_rate
website_evidence_sources
```

To nadal nie jest jeden arbitralny `Source Value Score`. Po realnym benchmarku wolumen, exclusivity/overlap, identity quality, jawne employer evidence, stabilność i koszt runtime powinny być analizowane osobno.

## Artifact

Artifact ma nazwę:

```text
faro-controlled-benchmark-<github.run_id>
```

oraz retencję 14 dni. Obejmuje katalog `benchmark/`, czyli zależnie od etapu m.in.:

```text
preflight.json
preflight_exit_code.txt
exit_code.txt
run_result.json
run_skipped.txt
source_diagnostics.json
benchmark.sqlite3
run/collection.json
run/enrichment.json
run/benchmark_report.json
run/benchmark_run_manifest.json
run/dataset/*
run/labels/*
```

`run_skipped.txt` występuje tylko wtedy, gdy preflight nie przeszedł. `run_result.json` i katalog `run/` powstają dopiero po wejściu we właściwy benchmark. `source_diagnostics.json` powstaje, jeśli baza benchmarkowa została utworzona.

Baza i eksport zawierają dane pozyskane podczas benchmarku, dlatego artefaktu nie należy traktować jako pliku do publicznego rozpowszechniania bez wcześniejszego przeglądu danych i warunków źródeł.

## Uruchomienie w UI GitHub

Po tym, jak workflow znajdzie się na gałęzi domyślnej:

```text
Actions
  -> Controlled Benchmark
  -> Run workflow
  -> wybór parametrów
  -> Run workflow
```

Przed pierwszym pełnym runem warto uruchomić lokalny `agregator-benchmark preflight` lub zweryfikować konfigurację Secrets, aby nie zużywać czasu runnera na oczywisty błąd konfiguracji.

## Bezpieczeństwo operacyjne

- workflow ma tylko `contents: read`,
- nie wykonuje outreachu,
- nie zapisuje wartości sekretów do generowanych plików,
- nie uruchamia się automatycznie,
- właściwy benchmark jest blokowany po nieudanym preflight,
- artifact powstaje również dla nieudanego preflightu lub niekompletnego strict runu,
- concurrency blokuje dwa równoległe pełne benchmarki,
- limit joba to 180 minut,
- brakujące autoryzacje nie są zastępowane scrapingiem obchodzącym kontrolę dostępu.
