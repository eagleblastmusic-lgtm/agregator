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

Workflow nie wypisuje wartości sekretów. Pierwszym krokiem jest `agregator-benchmark preflight --strict`; jeśli wybrane źródło nie ma wymaganej konfiguracji, benchmark kończy się przed kolekcją.

## Przebieg

```text
manual dispatch
   │
   ▼
install
   │
   ▼
preflight --strict
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

Sam run benchmarku zapisuje exit code do `benchmark/exit_code.txt`, a upload artefaktu jest wykonywany również po nieudanym/niekompletnym runie. Dzięki temu diagnostyczny workspace nie znika tylko dlatego, że strict gate zwrócił kod różny od zera.

## Artifact

Artifact ma nazwę:

```text
faro-controlled-benchmark-<github.run_id>
```

oraz retencję 14 dni. Obejmuje katalog `benchmark/`, czyli m.in.:

```text
benchmark.sqlite3
run/collection.json
run/enrichment.json
run/benchmark_report.json
run/benchmark_run_manifest.json
run/dataset/*
run/labels/*
```

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
- nie zapisuje sekretów do artefaktu,
- nie uruchamia się automatycznie,
- concurrency blokuje dwa równoległe pełne benchmarki,
- limit joba to 180 minut,
- brakujące autoryzacje nie są zastępowane scrapingiem obchodzącym kontrolę dostępu.
