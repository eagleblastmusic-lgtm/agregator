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
- pełny bundle `export-dataset`: firmy, oferty, kontakty/evidence + manifest wersji schematu,
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
- M1-10: **DONE** — pełny dataset eksportowy dla Faro (`companies.csv`, `job_postings.csv`, `contact_channels.csv`, `manifest.json`).

## M2 — Company Resolution

Status: **V1 + bezpieczna warstwa REVIEW zaimplementowane; automatyczny fuzzy-merge pozostaje wyłączony**.

Cel: jedna firma = jeden rekord niezależnie od liczby ofert, źródeł i lokalizacji, bez agresywnego łączenia podmiotów tylko dlatego, że ich nazwy są podobne.

### Zaimplementowany baseline V1

- normalizacja nazw i wariantów prawnych,
- rozszerzona normalizacja polskich i wybranych międzynarodowych form prawnych,
- `company_aliases` zachowujące wszystkie zaobserwowane nazwy,
- `company_locations` zachowujące wszystkie zaobserwowane miejscowości,
- exact-match nazwy + lokalizacji jako najmocniejszy sygnał,
- cross-city exact-match tylko dla charakterystycznej nazwy i wysokiego `identity_confidence`,
- blokada automatycznego cross-city merge dla nazw krótkich lub ogólnych,
- brak automatycznego fuzzy-matchingu,
- stabilny fallback identity dla ofert bez lokalizacji,
- `company_resolution_method` i `company_resolution_confidence` zapisane przy każdej ofercie,
- metryki metod resolution w `benchmark`,
- generator szablonu ground truth przez `export-ground-truth`,
- pairwise ground-truth evaluator precision/recall/F1 przez `evaluate-resolution`,
- `resolution-review` generujący fuzzy-kandydatów bez modyfikacji bazy,
- blocking kandydatów po tokenach/prefiksach oraz wysoko zweryfikowanym hoście WWW,
- score REVIEW uwzględniający podobieństwo nazw, token overlap, wspólną lokalizację, confidence tożsamości i zgodność domeny.

Przykładowe metody automatycznego resolution:

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

Szablon można wygenerować bezpośrednio z bazy:

```bash
agregator export-ground-truth \
  --db agregator.sqlite3 \
  --output company_ground_truth.csv \
  --limit 1000
```

Kolumna `truth_company_id` pozostaje pusta do ręcznego oznaczenia. Pozostałe kolumny zawierają kontekst, aktualny `predicted_company_id`, metodę i confidence.

Minimalny format ewaluatora:

```csv
source,source_id,truth_company_id
olx,123,company-001
jooble,ABC-7,company-001
adzuna,987,company-002
```

Dla wszystkich dopasowanych rekordów evaluator porównuje pary ofert i liczy TP/FP/FN/TN oraz precision, recall i F1. Brakujące w bazie rekordy są raportowane osobno.

### REVIEW fuzzy bez auto-merge

```bash
agregator resolution-review \
  --db agregator.sqlite3 \
  --min-score 0.82 \
  --limit 100
```

Ta warstwa służy do obserwacji jakości kandydatów i budowy ground truth. Nie zmienia `company_id` i nie może automatycznie połączyć dwóch firm.

### Sygnały planowane dla V2

- jawne identyfikatory pracodawcy ze źródeł,
- adres,
- telefon publiczny,
- NIP/KRS, jeśli jawnie występują,
- profile i identyfikatory źródłowe,
- zgodność danych między portalami,
- zweryfikowana domena jako potencjalny sygnał automatycznego merge dopiero po benchmarku,
- fuzzy similarity jako sygnał pomocniczy, nigdy samodzielny dowód,
- ręczne decyzje REVIEW jako dane treningowe/regułowe do kalibracji progów.

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
- M2-03: **PARTIAL** — zweryfikowana domena jest już mocnym sygnałem REVIEW; automatyczny merge pozostaje zablokowany do czasu ground truth,
- M2-04: **DONE** — fuzzy kandydaci trafiają do REVIEW bez automatycznego merge,
- M2-05: tooling **DONE**; zbudować rzeczywisty ręcznie oznaczony ground truth na próbce benchmarkowej,
- M2-06: ustalić progi precision/recall przed rozszerzeniem reguł automatycznych.

## M3 — wyszukiwanie i weryfikacja oficjalnej WWW

Status: **drugi etap weryfikacji treścią strony zaimplementowany jako baseline**.

Nie uznajemy pierwszego wyniku wyszukiwarki automatycznie.

### Etap 1 — ranking wyników wyszukiwarki

Scoring kandydata bierze pod uwagę:

- zgodność tokenów nazwy,
- miasto / region,
- zgodność nazwy z hostem,
- wykluczenie social mediów, katalogów i portali pracy,
- sygnały typu oficjalna/kontakt.

### Etap 2 — first-party verification

Dla najlepiej ocenionych kandydatów pipeline:

1. odwiedza stronę zgodnie z zasadami crawlera,
2. odczytuje treść first-party,
3. mierzy pokrycie tokenów nazwy firmy,
4. szuka pełnej znormalizowanej nazwy,
5. uwzględnia zgodność hosta i miejscowości,
6. łączy search score z content score,
7. akceptuje domenę tylko przy wystarczającym wyniku **i** mocnym sygnale tożsamości,
8. jeżeli pierwszy wynik jest fałszywy, może przejść do kolejnego kandydata zamiast automatycznie przyjąć pierwszy wynik.

Wynik `CompanyIdentity` zawiera `website_verification_signals`, a `website_confidence` dla automatycznie znalezionej strony jest wynikiem po drugiej fazie, nie samym search score.

### Następne checkpointy M3

- M3-02: utrwalić website verification provenance w bazie jako osobny evidence/audit trail,
- M3-03: dodać sygnały JSON-LD `Organization`, NIP/KRS/adres, jeśli jawnie dostępne,
- M3-04: przygotować ground truth poprawnych/niepoprawnych domen i policzyć precision/recall,
- M3-05: kalibracja wag i progów osobno dla krótkich i długich nazw firm.

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

Aktualny interoperacyjny bundle przed API/PostgreSQL:

```text
companies.csv
job_postings.csv
contact_channels.csv
manifest.json
```

API docelowe:

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

Score biznesowy jest osobny od `contact_confidence` i od technicznego confidence Company Resolution / Website Verification.

## Zasady bezpieczeństwa i jakości

- tylko publicznie dostępne dane,
- brak obchodzenia logowania, CAPTCHA, paywalli i blokad technicznych,
- respektowanie `robots.txt` dla crawlera stron firmowych,
- rate limiting per host,
- brak automatycznej wysyłki wiadomości,
- każde źródło portalu przechodzi osobny review techniczny i regulaminowy,
- każdy kontakt ma `evidence_url`, `evidence_text`, `verified_at` i confidence,
- fuzzy Company Resolution działa w trybie REVIEW, a nie automatycznego merge,
- wynik GREEN oznacza „mocny sygnał kontekstowy”, a nie automatyczną opinię prawną.

## Benchmark przed skalowaniem

Pierwszy test produkcyjny: 1000 realnych ofert.

Mierzymy:

- liczbę unikalnych firm,
- company/job ratio,
- precision/recall/F1 Company Resolution na ręcznie oznaczonej próbce,
- precision/recall poprawnego wyboru oficjalnej domeny,
- % firm z poprawnie znalezioną domeną,
- % wzbogaconych firm z kanałem GREEN/REVIEW,
- precision klasyfikacji kanałów,
- rozkład wyników per źródło,
- liczbę błędów i retry per źródło,
- średni koszt i czas na firmę.

CLI `benchmark` zapewnia automatyczny snapshot metryk technicznych. CLI `export-ground-truth` przygotowuje próbkę do ręcznego oznaczenia, `evaluate-resolution` mierzy jakość deduplikacji, a `resolution-review` pokazuje fuzzy-kandydatów bez ingerencji w tożsamość firm.
