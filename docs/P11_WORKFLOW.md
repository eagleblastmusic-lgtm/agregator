# P11 — resumowalny end-to-end run

## Status

P11 ma działający baseline dla aktualnie zaimplementowanych adapterów.

Jeden przebieg łączy istniejące etapy:

```text
źródła ofert
    -> append-only job observations
    -> current job/company state
    -> employer website candidates
    -> official website verification
    -> first-party crawl
    -> GREEN / REVIEW / IGNORE
    -> Excel: jedna firma = jeden wiersz
```

## Uruchomienie

```bash
agregator-run run \
  --sources all \
  --pages-per-source 1 \
  --enrichment-limit 100 \
  --db agregator.sqlite3 \
  --output export/faro_firmy_kontakt.xlsx
```

`--sources all` oznacza wszystkie adaptery z aktualnego registry.

- publiczne źródła są uruchamiane bez dodatkowych poświadczeń,
- partner/API jest uruchamiany tylko wtedy, gdy wszystkie jego `required_env` są ustawione,
- brak konfiguracji opcjonalnego partnera daje `skipped`, nie `failed`,
- `BRAVE_SEARCH_API_KEY` jest opcjonalny dla workflow: source-provided employer websites są weryfikowane bez niego; Brave jest fallbackiem dla firm bez zweryfikowanej strony.

## Resume

Domyślny run jest resumowalny:

- każdy source korzysta z zapisanego cursora,
- `job_posting_observations` pozostaje append-only,
- firmy z ustawionym `enriched_at` nie są ponownie crawlowane,
- source runy i evidence history pozostają w bazie,
- Excel jest odtwarzany z aktualnego zbioru firm posiadających kanał `GREEN`.

Ponowne uruchomienie tej samej komendy kontynuuje pracę z istniejącej bazy.

## Kontrolowane odświeżenie

```bash
agregator-run run --fresh-sources
agregator-run run --refresh-enrichment
```

`--fresh-sources` resetuje tylko punkt startowy wybranych adapterów na czas danego przebiegu. Nie kasuje append-only historii.

`--refresh-enrichment` ponownie weryfikuje także wcześniej wzbogacone firmy.

## Awaria źródła

Awaria jednego portalu nie zatrzymuje pozostałych źródeł. Wynik workflow otrzymuje status `partial`, a szczegóły błędu są zapisane w `source_results` i w tabeli `source_runs`.

`--fail-fast` zatrzymuje dalsze zbieranie po pierwszym błędzie źródła, ale nadal wykonuje enrichment i eksport na danych już zapisanych.

`--strict` zwraca kod procesu `2`, jeżeli którekolwiek faktycznie uruchomione źródło zakończyło się błędem. Źródło pominięte z powodu brakujących opcjonalnych poświadczeń nie jest błędem workflow.

## Wynik JSON

Runner raportuje m.in.:

- `requested_sources`,
- `selected_sources`,
- `skipped_sources` wraz z `missing_env`,
- `successful_sources`,
- `failed_sources`,
- statystyki każdego source runu,
- statystyki enrichmentu (`websites_found`, `green_channels`, `search_skipped`, itd.),
- ścieżkę oraz liczbę firm w finalnym eksporcie Excel.

## Bezpieczeństwo danych

P11 nie wysyła wiadomości i nie automatyzuje outreach. System tylko zbiera publiczne dane, zachowuje evidence i klasyfikuje kanały. `GREEN` oznacza istotny sygnał współpracy w kontekście produktu, a nie automatyczne stwierdzenie podstawy prawnej do dowolnej komunikacji marketingowej.
