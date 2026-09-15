# Plan rozwoju — Faro Employer Discovery Engine

## Cel produktu

Zbudować program, który:

1. pobiera publiczne oferty pracy z wielu źródeł,
2. wyciąga i normalizuje pracodawców,
3. deduplikuje firmy między portalami,
4. znajduje oficjalną stronę WWW firmy,
5. przeszukuje jej publiczne podstrony,
6. wykrywa kanały typu współpraca / partnerzy / B2B / oferty handlowe / dostawcy / franczyza,
7. zapisuje e-mail lub formularz **razem z kontekstem, źródłem i confidence**,
8. nie wysyła wiadomości — moduł outreach jest poza zakresem tego repo na M0/M1.

## Architektura docelowa

```text
Job Sources
   │
   ▼
Collectors / Adapters
   │
   ▼
Job Normalizer
   │
   ▼
Company Resolver + Deduplication
   │
   ▼
Website Search Provider
   │
   ▼
Official Website Resolver
   │
   ▼
Company Website Crawler
   │
   ▼
Contact / Intent Extractor
   │
   ▼
Evidence + Confidence Engine
   │
   ▼
Database / Export / API
```

## M0 — rdzeń enrichmentu

Status: **funkcjonalny baseline gotowy**.

Zaimplementowano:

- modele danych,
- wymienny `SearchProvider`,
- resolver oficjalnej domeny,
- crawler stron firmowych,
- `robots.txt`, limity i opóźnienie między requestami,
- ekstrakcję e-maili i formularzy,
- klasyfikację `GREEN / REVIEW / IGNORE`,
- provenance/evidence,
- CLI,
- testy i CI.

### Kryteria akceptacji M0

- `scan-url` potrafi przeskanować znaną stronę firmy i zwrócić JSON,
- wynik zawiera URL źródłowy i kontekst każdej znalezionej pozycji,
- fraza typu „Propozycje współpracy: wspolpraca@firma.pl” daje GREEN,
- „Nie przyjmujemy ofert handlowych” daje IGNORE,
- adres RODO / IOD daje IGNORE,
- zwykły `kontakt@` bez kontekstu nie daje GREEN,
- crawler nie wychodzi poza domenę i respektuje `robots.txt`.

## M1 — agregacja ofert pracy

Status: **zaawansowany fundament w realizacji**.

Zaimplementowano:

- wspólny kontrakt `JobSource`,
- `SourceRegistry` pod kolejne portale,
- adapter publicznego źródła OLX,
- adapter Jooble oparty o REST API,
- adapter Adzuna oparty o REST API,
- cursor/offset/page i resumowalne pobieranie,
- SQLite z tabelami `companies`, `job_postings`, `contact_channels`, `source_state`, `source_runs`,
- podstawową normalizację i konserwatywną deduplikację firm,
- provenance nazwy pracodawcy oraz `identity_confidence`,
- historię runów: success/failure, kursory, strony, insert/update i skrócony błąd,
- kolejkę firm do enrichmentu,
- trwały zapis oficjalnej strony, kanałów i evidence,
- importer CSV do benchmarków wieloźródłowych,
- katalog 91 źródeł z master-listy i raport pokrycia adapterami,
- benchmark snapshot: oferty, firmy, źródła, enrichment, GREEN/REVIEW/IGNORE, rate domen,
- eksport wyników GREEN do JSON/CSV,
- CLI do całego przepływu.

### Interfejs adaptera źródła

Każde źródło implementuje ten sam kontrakt:

```text
collect(cursor) -> JobPosting[] + next_cursor
```

Minimalne dane:

- source,
- source_id,
- URL oferty,
- tytuł,
- nazwa firmy,
- provenance i confidence nazwy,
- lokalizacja,
- opis,
- data publikacji / odświeżenia, jeśli dostępna.

### Strategia integracji źródeł

1. źródła z oficjalnym API/feedem,
2. źródła publiczne/oficjalne,
3. publiczne portale bez logowania po przeglądzie sposobu dostępu i regulaminu,
4. strony dynamiczne przez Playwright tylko tam, gdzie jest to konieczne i zgodne z zasadami dostępu,
5. źródła partnerskie/ograniczone nie są zastępowane obchodzeniem zabezpieczeń.

Każdy adapter jest izolowany w `src/agregator/sources/<source>.py` i może zostać wyłączony bez wpływu na pozostałe.

### Stan katalogu źródeł

- 91 pozycji w `config/source_catalog.tsv`,
- 14 źródeł A0,
- 36 źródeł A1,
- 24 źródła B,
- 17 źródeł C,
- obecnie zaimplementowane: OLX, Jooble, Adzuna.

### Następne checkpointy M1

- M1-06: dodać kolejne źródło API-first lub oficjalne A0/A1,
- M1-07: przygotować fixture z realnego publicznego payloadu OLX i test kontraktowy,
- M1-08: uruchomić kontrolowany benchmark 1000 ofert,
- M1-09: mierzyć błędy per source oraz koszt/czas na firmę,
- M1-10: eksport pełnego datasetu firm i ofert do późniejszej integracji z Faro.

## M2 — Company Resolution

Status: **V1 zaimplementowany; fuzzy/entity-resolution v2 pozostaje do wykonania**.

Cel: jedna firma = jeden rekord niezależnie od liczby ofert, źródeł i lokalizacji, bez agresywnego łączenia podmiotów tylko dlatego, że ich nazwy są podobne.

### Zaimplementowany baseline V1

- normalizacja nazw i wariantów prawnych,
- `company_aliases` zachowujące wszystkie zaobserwowane nazwy,
- `company_locations` zachowujące wszystkie zaobserwowane miejscowości,
- exact-match nazwy + lokalizacji jako najmocniejszy sygnał,
- cross-city exact-match tylko dla charakterystycznej nazwy i wysokiego `identity_confidence`,
- blokada automatycznego cross-city merge dla nazw krótkich lub ogólnych,
- brak fuzzy-matchingu w V1,
- stabilny fallback identity dla ofert bez lokalizacji,
- `company_resolution_method` i `company_resolution_confidence` zapisane przy każdej ofercie,
- metryki metod resolution w `benchmark`,
- pairwise ground-truth evaluator precision/recall/F1 przez `evaluate-resolution`.

Przykładowe metody resolution:

```text
new_company
exact_name_city
exact_name_cross_city
exact_name_partial_location
insufficient_cross_city_evidence
ambiguous_exact_name
stable_source_key
```

### Ground truth

Ręcznie oznaczony plik ma postać:

```csv
source,source_id,truth_company_id
olx,123,company-001
jooble,ABC-7,company-001
adzuna,987,company-002
```

Dla wszystkich dopasowanych rekordów evaluator porównuje pary ofert i liczy TP/FP/FN/TN oraz precision, recall i F1. Brakujące w bazie rekordy są raportowane osobno.

### Sygnały planowane dla V2

- nazwa i warianty prawne,
- miejscowość i wiele lokalizacji,
- adres,
- domena,
- telefon publiczny,
- NIP/KRS, jeśli jawnie występują,
- profile i identyfikatory źródłowe,
- zgodność danych między portalami,
- fuzzy similarity jako sygnał pomocniczy, nigdy samodzielny dowód,
- kolejka przypadków niejednoznacznych do ręcznego review.

Wynik docelowy:

```text
company_id
canonical_name
aliases[]
locations[]
domains[]
job_count
sources[]
match_confidence
resolution_method
```

### Następne checkpointy M2

- M2-02: dodać jawne identyfikatory pracodawcy ze źródeł, jeśli są dostępne,
- M2-03: wykorzystać zweryfikowaną domenę jako mocny sygnał merge,
- M2-04: dodać kandydatów fuzzy do REVIEW bez automatycznego merge,
- M2-05: zbudować ręczny ground truth na próbce benchmarkowej,
- M2-06: ustalić progi precision/recall przed rozszerzeniem reguł automatycznych.

## M3 — wyszukiwanie i weryfikacja oficjalnej WWW

Nie uznajemy pierwszego wyniku wyszukiwarki automatycznie.

Scoring domeny bierze pod uwagę:

- zgodność tokenów nazwy,
- miasto / region,
- branżę,
- zgodność danych na stronie,
- wykluczenie social mediów, katalogów i portali pracy.

Następny etap: po znalezieniu kandydata odwiedzić stronę i wykonać drugi etap weryfikacji na podstawie treści i danych kontaktowych.

## M4 — crawler i classifier v2

Rozszerzenia:

- sitemap.xml,
- podstrony z menu i stopki,
- priorytety: `/kontakt`, `/wspolpraca`, `/partnerzy`, `/b2b`, `/dla-firm`, `/dostawcy`, `/franczyza`,
- obsługa obfuskowanych maili,
- lepsza detekcja formularzy,
- klasyfikacja semantyczna całego kontekstu,
- snapshot dowodu (tekst + timestamp + hash treści).

## M5 — baza i API

Docelowo PostgreSQL.

Główne encje:

- `job_postings`,
- `companies`,
- `company_aliases`,
- `company_locations`,
- `company_websites`,
- `contact_channels`,
- `evidence`,
- `crawl_runs`,
- `source_runs`.

API:

- nowe firmy,
- firmy aktywnie rekrutujące,
- firmy z GREEN channel,
- ręczna weryfikacja REVIEW,
- eksport CSV/JSON.

## Employer Discovery Score

Przykładowe sygnały biznesowe:

```text
+25 >= 3 aktywne oferty
+15 >= 2 źródła ofert
+15 jednoznaczna oficjalna domena
+20 jawna strona współpraca/B2B
+20 jawny kanał współpracy
 +5 bardzo wysoka zgodność danych firmy
```

Score biznesowy jest osobny od `contact_confidence`.

## Zasady bezpieczeństwa i jakości

- tylko publicznie dostępne dane,
- brak obchodzenia logowania, CAPTCHA, paywalli i blokad technicznych,
- respektowanie `robots.txt` dla crawlera stron firmowych,
- rate limiting per host,
- brak automatycznej wysyłki wiadomości,
- każde źródło portalu przechodzi osobny review techniczny i regulaminowy,
- każdy kontakt ma `evidence_url`, `evidence_text`, `verified_at` i confidence,
- wynik GREEN oznacza „mocny sygnał kontekstowy”, a nie automatyczną opinię prawną.

## Benchmark przed skalowaniem

Pierwszy test produkcyjny: 1000 realnych ofert.

Mierzymy:

- liczbę unikalnych firm,
- company/job ratio,
- precision/recall/F1 Company Resolution na ręcznie oznaczonej próbce,
- % firm z poprawnie znalezioną domeną,
- % wzbogaconych firm z kanałem GREEN/REVIEW,
- precision klasyfikacji kanałów,
- rozkład wyników per źródło,
- liczbę błędów i retry per źródło,
- średni koszt i czas na firmę.

CLI `benchmark` zapewnia automatyczny snapshot metryk technicznych. CLI `evaluate-resolution` mierzy jakość deduplikacji na ręcznie oznaczonym ground truth przed rozszerzeniem automatycznych reguł resolution.
