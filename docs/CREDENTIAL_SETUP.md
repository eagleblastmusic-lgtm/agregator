# Faro — konfiguracja źródeł przed realnym smoke testem

Ten etap odpowiada punktowi P2 roadmapy. Jego celem jest przygotowanie autoryzowanych źródeł do pierwszego realnego collection smoke bez ujawniania wartości sekretów w logach, artefaktach ani outputach CLI.

## Pierwszy zestaw źródeł

Na pierwszy smoke używamy:

```text
jooble
adzuna
```

Oba źródła są zarejestrowane jako `partner_api`. Aktualny adapter OLX pozostaje `public_web_endpoint + experimental` i nie jest częścią domyślnego smoke testu.

## Wymagane wartości

Jooble:

```text
JOOBLE_API_KEY
```

Adzuna:

```text
ADZUNA_APP_ID
ADZUNA_APP_KEY
```

Brave Search **nie jest potrzebny** do collection smoke. `BRAVE_SEARCH_API_KEY` będzie potrzebny dopiero przy pełnym benchmarku z website discovery i enrichmentem.

## Bezpieczne sprawdzenie konfiguracji

Po instalacji repo można sprawdzić wymagania bez wyświetlania wartości sekretów:

```bash
agregator-collect sources
```

Następnie:

```bash
agregator-collect credentials \
  --sources jooble,adzuna \
  --strict
```

Komenda raportuje wyłącznie:

```text
nazwa zmiennej
configured = true / false
missing_required_env
ready
```

Nie wypisuje wartości żadnej zmiennej środowiskowej. Pole `values_exposed` powinno mieć wartość `false`.

Po przejściu credential check uruchamiamy właściwy preflight adapterów:

```bash
agregator-collect preflight \
  --sources jooble,adzuna \
  --strict
```

Credential check odpowiada na pytanie „czy wymagane dane konfiguracyjne są obecne?”, natomiast preflight dodatkowo próbuje zbudować adapter i wykrywa błędy konfiguracji specyficzne dla danego źródła.

## Lokalnie

Sekretów nie należy commitować do repo. Można ustawić je jako zmienne środowiskowe procesu/shella lub skorzystać z lokalnego pliku `.env` ładowanego przez własne środowisko uruchomieniowe. Repo zawiera wyłącznie `.env.example` z pustymi wartościami.

Przykładowy zestaw konfiguracyjny dla pierwszego smoke:

```text
JOOBLE_API_KEY=<secret>
JOOBLE_KEYWORDS=praca
JOOBLE_LOCATION=Polska
JOOBLE_RESULTS_PER_PAGE=20

ADZUNA_APP_ID=<secret>
ADZUNA_APP_KEY=<secret>
ADZUNA_COUNTRY=pl
ADZUNA_RESULTS_PER_PAGE=20
```

## GitHub Actions

Manualny workflow `.github/workflows/collection-smoke.yml` korzysta z GitHub Actions Secrets:

```text
JOOBLE_API_KEY
ADZUNA_APP_ID
ADZUNA_APP_KEY
```

Workflow nie wypisuje ich wartości. Po dodaniu sekretów można uruchomić w GitHub UI:

```text
Actions
  -> Collection Smoke
  -> Run workflow
```

Domyślnie:

```text
sources=jooble,adzuna
target_jobs=100
max_rounds=10
allow_experimental_sources=false
```

## Dalsze źródła

Careerjet wymaga:

```text
CAREERJET_API_KEY
CAREERJET_REFERER
CAREERJET_USER_IP
CAREERJET_USER_AGENT
```

oraz opcjonalnej konfiguracji locale/keywords/location/page size/sort.

Oficjalny ePraca WebService wymaga:

```text
EPRACA_PARTNER
```

oraz dokładnie jednego kryterium zakresu:

```text
EPRACA_WOJEWODZTWO
EPRACA_JEDNOSTKA
EPRACA_ALL=true
```

Nie podstawiamy fikcyjnych wartości partnera ani nie obchodzimy autoryzacji.

## Gate P2 -> P3

P2 uznajemy za zakończone, gdy dla `jooble,adzuna` oba polecenia kończą się sukcesem:

```bash
agregator-collect credentials --sources jooble,adzuna --strict
agregator-collect preflight --sources jooble,adzuna --strict
```

Następnie przechodzimy do P3:

```bash
agregator-collect run \
  --db benchmark/collection.sqlite3 \
  --output-dir benchmark/collection \
  --sources jooble,adzuna \
  --target-jobs 100 \
  --max-rounds 10 \
  --strict
```
