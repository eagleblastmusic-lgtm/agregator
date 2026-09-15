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

Status: rozpoczęty.

Zakres:

- modele danych,
- wymienny `SearchProvider`,
- resolver oficjalnej domeny,
- crawler stron firmowych,
- `robots.txt`, limity i opóźnienie między requestami,
- ekstrakcja e-maili i formularzy,
- klasyfikacja `GREEN / REVIEW / IGNORE`,
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

### Interfejs adaptera źródła

Każde źródło implementuje ten sam kontrakt:

```text
collect(since_cursor) -> JobPosting[] + next_cursor
```

Minimalne dane:

- source,
- source_id,
- URL oferty,
- tytuł,
- nazwa firmy,
- lokalizacja,
- opis,
- data publikacji / odświeżenia, jeśli dostępna.

### Kolejność wdrażania

1. źródła z oficjalnym API/feedem,
2. strony firmowe / careers,
3. publiczne portale bez logowania, po przeglądzie sposobu dostępu i regulaminu,
4. źródła dynamiczne przez Playwright tylko tam, gdzie jest to konieczne i zgodne z zasadami dostępu.

Każdy adapter jest izolowany w `src/agregator/sources/<source>.py` i może zostać wyłączony bez wpływu na pozostałe.

## M2 — Company Resolution

Cel: jedna firma = jeden rekord niezależnie od liczby ofert i źródeł.

Sygnały:

- nazwa i warianty prawne,
- miejscowość,
- adres,
- domena,
- telefon publiczny,
- NIP/KRS, jeśli jawnie występują,
- profile i identyfikatory źródłowe.

Wynik:

```text
company_id
canonical_name
aliases[]
locations[]
domains[]
job_count
sources[]
match_confidence
```

## M3 — wyszukiwanie i weryfikacja oficjalnej WWW

Nie uznajemy pierwszego wyniku wyszukiwarki automatycznie.

Scoring domeny bierze pod uwagę:

- zgodność tokenów nazwy,
- miasto / region,
- branżę,
- zgodność danych na stronie,
- wykluczenie social mediów, katalogów i portali pracy.

Plan: po znalezieniu kandydata odwiedzić stronę i zrobić drugi etap weryfikacji na podstawie treści i danych kontaktowych.

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

Pierwszy test produkcyjny:

- 1000 realnych ofert,
- liczba unikalnych firm,
- precision Company Resolution,
- % firm z poprawnie znalezioną domeną,
- % firm z kanałem GREEN/REVIEW,
- precision klasyfikacji na ręcznie oznaczonej próbce,
- średni koszt i czas na firmę.

Dopiero po benchmarku zwiększamy skalę i liczbę źródeł.
