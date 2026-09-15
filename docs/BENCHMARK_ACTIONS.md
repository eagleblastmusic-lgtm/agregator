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
upload workspace artifact
          │
          ▼
enforce exit code
```

Workspace jest inicjalizowany **przed** preflightem. Dzięki temu nawet błąd konfiguracji pozostawia audytowalny artifact z `preflight.json`, `preflight_exit_code.txt` i informacją, że właściwy run został pominięty.

Sam run benchmarku zapisuje swój kod wyjścia do `benchmark/exit_code.txt`. Standardowy JSON zwracany przez CLI trafia do `benchmark/run_result.json`; właściwe dane benchmarku są nadal zapisywane w `benchmark/run/` przez samą aplikację.

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
benchmark.sqlite3
run/collection.json
run/enrichment.json
run/benchmark_report.json
run/benchmark_run_manifest.json
run/dataset/*
run/labels/*
```

`run_skipped.txt` występuje tylko wtedy, gdy preflight nie przeszedł. `run_result.json` i katalog `run/` powstają dopiero po wejściu we właściwy benchmark.

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
