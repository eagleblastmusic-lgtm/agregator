# Faro — collection-only smoke test

Collection smoke służy do sprawdzenia realnego pobierania ofert i jakości danych źródłowych **bez** uruchamiania Brave Search, crawlowania stron firm ani klasyfikacji kontaktów.

To jest etap pośredni pomiędzy unit/integration tests a pełnym benchmarkiem 1000 ofert.

## CLI

Preflight:

```bash
agregator-collect preflight \
  --sources jooble,adzuna \
  --strict
```

Mały run:

```bash
agregator-collect run \
  --db benchmark/collection.sqlite3 \
  --output-dir benchmark/collection \
  --sources jooble,adzuna \
  --target-jobs 100 \
  --max-rounds 10 \
  --strict
```

Collection-only preflight celowo ustawia `search_provider_required=false`, dlatego `BRAVE_SEARCH_API_KEY` nie jest potrzebny.

Collector kończy **całą rundę round-robin** zanim sprawdzi warunek `target_jobs`. Oznacza to, że końcowa liczba ofert może lekko przekroczyć target, ale jedno źródło o dużym wolumenie nie zakończy rundy zanim pozostałe skonfigurowane adaptery zostaną sprawdzone.

W trybie `--strict` samo osiągnięcie łącznego targetu nie wystarcza. Run jest uznawany za gotowy do pełnego benchmarku dopiero, gdy:

```text
collection_target_reached = true
source_health_ready = true
```

`source_health_ready=false`, jeżeli którekolwiek żądane źródło:

- nie wykonało ani jednego udanego runu,
- zostało wyłączone po błędach,
- wykonało run, ale nie zwróciło żadnej oferty.

Przejściowe błędy, po których źródło później działa, pozostają widoczne w `sources_with_errors`, ale nie blokują automatycznie readiness.

## GitHub Actions

Manualny workflow:

```text
.github/workflows/collection-smoke.yml
```

Domyślne parametry:

```text
sources=jooble,adzuna
target_jobs=100
max_rounds=10
allow_experimental_sources=false
```

Workflow jest wyłącznie `workflow_dispatch`; nie wykonuje realnych requestów do portali na każdy push lub PR.

Po uruchomieniu przebieg jest następujący:

```text
install
  -> collection preflight
  -> collection-only run
  -> benchmark/source diagnostics
  -> dataset v8
  -> artifact
  -> strict result enforcement
```

Jeżeli preflight nie przejdzie, właściwy run nie startuje, ale artifact nadal zawiera `preflight.json`, kod wyjścia oraz informację o pominięciu runu.

## Artifact

Artifact:

```text
faro-collection-smoke-<github.run_id>
```

Retencja: 7 dni.

Typowa zawartość:

```text
preflight.json
preflight_exit_code.txt
exit_code.txt
run_result.json
collection.sqlite3
run/collection.json
run/benchmark_report.json
run/collection_run_manifest.json
run/dataset/*
```

`collection_run_manifest.json` schema v2 zawiera m.in.:

```text
collection_target_reached
source_health_ready
unexercised_sources
disabled_sources
sources_without_jobs
sources_with_errors
ready_for_full_enrichment_benchmark
blockers
```

Run nie tworzy ground truth dla WWW/kontaktów, ponieważ collection smoke nie wykonuje enrichmentu.

## Source access policy

Źródła mają metadane `access_mode` i `experimental` w `SourceRegistry`.

Aktualny adapter OLX jest oznaczony jako `public_web_endpoint + experimental`, więc nie może wejść do smoke testu bez jawnego:

```text
--allow-experimental-sources
```

W workflow odpowiada temu boolean `allow_experimental_sources` domyślnie ustawiony na `false`.

Partner/API-first źródła pozostają preferowanym baseline'em. Brak konfiguracji partnera/API ma zakończyć się czytelnym błędem preflight, a nie fallbackiem omijającym autoryzację.

Dla ePraca workflow może korzystać z `EPRACA_PARTNER` jako secret oraz z repozytoryjnych variables `EPRACA_WOJEWODZTWO`, `EPRACA_JEDNOSTKA` lub `EPRACA_ALL` do jawnego określenia zakresu integracji.

## Po co ten etap

Smoke test odpowiada przede wszystkim na pytania:

- czy realne API działa z aktualną konfiguracją,
- czy każde wybrane źródło faktycznie zwraca oferty,
- czy paginacja/cursor działają,
- ile ofert realnie wraca,
- jaka jest jakość nazwy pracodawcy, miasta i opisu,
- czy źródło dostarcza NIP/REGON/WWW,
- jaki jest overlap i exclusivity względem pozostałych źródeł,
- jaki jest error rate i czas runów.

Dopiero po stabilnym collection smoke przechodzimy do pełnego benchmarku:

```text
1000 ofert
  -> enrichment
  -> website verification
  -> contact classification
  -> blind ground truth
  -> quality gate
```
