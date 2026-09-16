# Faro — Controlled Benchmark w GitHub Actions

Repo zawiera manualny workflow:

```text
.github/workflows/controlled-benchmark.yml
```

Workflow **nie uruchamia się automatycznie** na push/PR ani według harmonogramu. Jest dostępny wyłącznie przez `workflow_dispatch`, dzięki czemu pełny benchmark i potencjalnie płatne API nie są wywoływane przypadkowo.

Przed nim zalecany jest tańszy collection-only smoke opisany w [`COLLECTION_SMOKE.md`](COLLECTION_SMOKE.md).

## Kiedy użyć

Po merge workflow do gałęzi domyślnej i po skonfigurowaniu wymaganych GitHub Actions Secrets można uruchomić kontrolowany benchmark bez przygotowywania lokalnego środowiska Python.

Domyślne parametry:

```text
sources=jooble,adzuna
allow_experimental_sources=false
target_jobs=1000
max_rounds=100
max_enrichment_companies=1000
label_sampling_seed=faro-ground-truth-v1
```

## Klasy dostępu źródeł

`SourceRegistry` zapisuje `access_mode`, `experimental` i opcjonalną notatkę operacyjną:

```text
jooble     -> partner_api
adzuna     -> partner_api
careerjet  -> partner_api
epraca     -> official_partner_feed
olx        -> public_web_endpoint + experimental
```

Aktualny adapter OLX nie jest traktowany jako stabilny kontrakt partnerskiego API, dlatego kontrolowany benchmark nie użyje go bez jawnego opt-in `--allow-experimental-sources`. W GitHub Actions odpowiada za to boolean `allow_experimental_sources`, domyślnie `false`.

## Secrets i variables

Secrets:

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

Dla ePraca zakres można skonfigurować jako GitHub repository variables:

```text
EPRACA_WOJEWODZTWO
EPRACA_JEDNOSTKA
EPRACA_ALL
```

Należy ustawić prawidłowy, jawny scope zgodny z adapterem. `BRAVE_SEARCH_API_KEY` jest wymagany przez pełny enrichment/search benchmark, ale nie przez osobny collection smoke.

Workflow nie wypisuje wartości sekretów. `agregator-benchmark preflight --strict` blokuje run przy brakującej konfiguracji lub niezaakceptowanym źródle eksperymentalnym.

## Przebieg

```text
manual dispatch
   │
   ▼
install
   │
   ▼
initialize workspace
   │
   ▼
preflight --strict
   │
   ├── FAIL -> preflight.json + artifact + FAIL
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
GitHub Step Summary
          │
          ▼
upload workspace artifact
          │
          ▼
enforce exit code
```

Workspace jest inicjalizowany przed preflightem. Dzięki temu nawet błąd konfiguracji pozostawia audytowalny artifact z `preflight.json`, kodem wyjścia i informacją o pominięciu właściwego runu.

`benchmark/run_result.json` zawiera standardowy JSON zwracany przez CLI, a `benchmark/run/` zawiera właściwy workspace benchmarku.

## GitHub Step Summary

Workflow generuje czytelne podsumowanie bez wypisywania sekretów. Pokazuje m.in.:

```text
preflight ready
search provider ready
collection target reached
jobs collected
companies
companies enriched
websites found
GREEN channels
ready_for_manual_labeling
readiness blockers
```

Jeżeli powstały source diagnostics, summary dodaje tabelę per źródło z liczbą ofert/firm, średnim confidence nazwy i Company Resolution oraz city coverage.

To jest szybki widok operacyjny; pełnym źródłem audytowym pozostają JSON-y, SQLite i eksporty w artifact.

## Source diagnostics

Po utworzeniu bazy workflow uruchamia:

```bash
agregator-benchmark source-diagnostics \
  --db benchmark/benchmark.sqlite3
```

Wynik trafia do `benchmark/source_diagnostics.json`.

Sekcja `identity` opisuje jakość rekordów ofertowych per źródło, m.in. confidence nazwy firmy, Company Resolution i coverage miasta/opisu.

Sekcja `provenance` pokazuje, które źródło faktycznie dostarczyło jawne dane pracodawcy, np. NIP/REGON lub kandydaturę oficjalnej WWW. Wykorzystuje:

```text
company_identifier_observations
company_website_candidate_observations
```

Każda obserwacja zachowuje `job_source + evidence_source + company_id + wartość/URL + confidence + observation_count`. Jeśli dwie integracje dostarczą ten sam NIP/WWW, obie zachowują własny provenance.

## Artifact

Artifact:

```text
faro-controlled-benchmark-<github.run_id>
```

Retencja: 14 dni.

Typowa zawartość:

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

`run_skipped.txt` występuje tylko po nieudanym preflight. Baza i eksport zawierają dane pozyskane podczas benchmarku, dlatego artifactu nie należy publicznie rozpowszechniać bez przeglądu danych i warunków źródeł.

## Uruchomienie w UI GitHub

Po tym, jak workflow znajdzie się na gałęzi domyślnej:

```text
Actions
  -> Controlled Benchmark
  -> Run workflow
  -> wybór parametrów
  -> Run workflow
```

Zalecana kolejność przed pierwszym pełnym runem:

```text
Collection Smoke
  -> PASS
  -> Controlled Benchmark
```

## Bezpieczeństwo operacyjne

- `contents: read`,
- brak outreachu,
- brak wartości sekretów w generowanych raportach/summary,
- brak automatycznego uruchamiania,
- benchmark blokowany po failed preflight,
- źródła eksperymentalne wymagają jawnego opt-in,
- artifact powstaje również dla failed preflight/strict runu,
- concurrency blokuje dwa równoległe pełne benchmarki,
- limit joba 180 minut,
- brakujące autoryzacje nie są zastępowane obchodzeniem kontroli dostępu.
