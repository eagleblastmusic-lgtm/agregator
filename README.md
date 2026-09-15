# Agregator — Faro Employer Discovery Engine

Silnik do budowania bazy firm aktywnie rekrutujących oraz wykrywania ich oficjalnych stron WWW i publicznych kanałów współpracy B2B.

## Główny łańcuch

`oferta pracy -> firma -> oficjalna domena -> crawl strony -> kanał współpracy -> dowód + confidence`

Projekt **nie wysyła wiadomości**, nie omija logowania ani zabezpieczeń portali i nie próbuje pozyskiwać niepublicznych danych. Zapisuje publicznie dostępne informacje oraz źródło, z którego zostały znalezione.

## Aktualny zakres M0/M1/M2

- modele danych dla ofert, firm, kanałów kontaktu i dowodów,
- wspólny kontrakt `JobSource` i `SourceRegistry`,
- adapter `OlxPublicSource`,
- adapter `JoobleApiSource` oparty o oficjalne REST API,
- adapter `AdzunaApiSource` oparty o oficjalne REST API,
- katalog 91 źródeł z master-listy w `config/source_catalog.tsv`,
- resumowalne pobieranie przez cursor/offset/page,
- historia każdego uruchomienia źródła i metryki błędów,
- SQLite: `companies`, `company_aliases`, `company_locations`, `job_postings`,
  `contact_channels`, `source_state`, `source_runs`,
- Company Resolution v1 z konserwatywnym łączeniem między źródłami i lokalizacjami,
- jawny `company_resolution_method` i `company_resolution_confidence` na ofercie,
- nieinwazyjna kolejka `resolution-review` dla fuzzy-kandydatów — bez automatycznego merge,
- zweryfikowana domena WWW jako mocny sygnał do ręcznego review,
- provenance i confidence źródła nazwy firmy,
- importer CSV do benchmarków wieloźródłowych,
- eksport szablonu ground truth i evaluator precision/recall/F1 dla Company Resolution,
- wyszukiwanie oficjalnej strony przez wymienny `SearchProvider`,
- opcjonalny provider Brave Search API,
- resolver domeny z oceną dopasowania,
- crawler stron firmowych z limitem stron i obsługą `robots.txt`,
- ekstrakcja e-maili oraz formularzy,
- klasyfikacja kontekstu: `GREEN / REVIEW / IGNORE`,
- zachowywanie `evidence_url`, `evidence_text` i confidence,
- kolejka firm do enrichmentu z minimalnym confidence tożsamości,
- benchmark snapshot i eksport GREEN do JSON/CSV,
- pełny bundle eksportowy Faro: firmy, oferty, kontakty + manifest,
- testy jednostkowe i GitHub Actions CI.

## Instalacja

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e ".[dev]"
cp .env.example .env
```

## Użycie

### 1. Utworzenie bazy

```bash
agregator db-init --db agregator.sqlite3
```

### 2. Dostępne adaptery

```bash
agregator sources
```

Aktualnie: `olx`, `jooble`, `adzuna`.

### 3. OLX Praca

```bash
agregator collect-olx --db agregator.sqlite3 --pages 2
```

Kolejne uruchomienie wznawia pracę od zapisanego offsetu. `--fresh` rozpoczyna od początku.

Adapter zapisuje provenance nazwy firmy. Imię konta lub osoby kontaktowej ma niski confidence i domyślnie nie trafia do automatycznego enrichmentu.

### 4. Jooble REST API

Wymaga regionalnego klucza `JOOBLE_API_KEY`.

```bash
agregator collect-jooble \
  --keywords "sprzedawca" \
  --location "Polska" \
  --pages 2
```

### 5. Adzuna REST API

Wymaga `ADZUNA_APP_ID` i `ADZUNA_APP_KEY`.

```bash
agregator collect-adzuna \
  --country pl \
  --what "python" \
  --where "Polska" \
  --pages 2
```

### 6. Uniwersalny collector

```bash
agregator collect --source jooble --pages 1
agregator collect --source adzuna --pages 1
```

### 7. Historia runów

```bash
agregator runs --source olx --limit 20
```

Każdy run zapisuje status, kursory, liczbę stron, liczbę ofert, insert/update, nowe firmy i skrócony błąd.

### 8. Import benchmarku CSV

Minimalne kolumny: `url,title,company_name`.

```bash
agregator import-csv --path jobs.csv --db agregator.sqlite3
```

### 9. Podgląd wykrytych firm

```bash
agregator companies --db agregator.sqlite3 --limit 50
```

Wynik zawiera także aliasy i wszystkie zaobserwowane lokalizacje firmy.

### 10. Company Resolution v1

Resolver nie wykonuje automatycznego fuzzy-merge. Automatyczne łączenie między różnymi miastami jest dopuszczane tylko wtedy, gdy:

- znormalizowana nazwa jest identyczna,
- nazwa jest wystarczająco charakterystyczna,
- po obu stronach istnieje mocny `identity_confidence`,
- istnieje tylko jeden jednoznaczny kandydat.

Krótkie lub ogólne nazwy, niskie confidence oraz niejednoznaczne klastry pozostają rozdzielone zamiast być ryzykownie scalane.

Każda oferta zapisuje metodę resolution, np. `new_company`, `exact_name_city`, `exact_name_cross_city`, `exact_name_partial_location` albo informację o niewystarczających przesłankach.

### 11. Kolejka fuzzy do ręcznej weryfikacji

```bash
agregator resolution-review \
  --db agregator.sqlite3 \
  --min-score 0.82 \
  --limit 100
```

Ta komenda **niczego nie scala**. Zwraca potencjalne duplikaty wraz z punktacją i sygnałami, np. podobieństwem nazw, wspólną lokalizacją albo zgodnością wysoko zweryfikowanego hosta WWW. Jest to warstwa REVIEW przed ewentualnym rozszerzeniem automatycznych reguł.

### 12. Benchmark techniczny

```bash
agregator benchmark --db agregator.sqlite3
```

Raport zawiera m.in. liczbę ofert, firm, źródeł, skuteczność enrichmentu, GREEN/REVIEW/IGNORE oraz rozkład `company_resolution_method`.

### 13. Ground truth dla Company Resolution

Najpierw można wygenerować arkusz roboczy z realnych rekordów bazy:

```bash
agregator export-ground-truth \
  --db agregator.sqlite3 \
  --output company_ground_truth.csv \
  --limit 1000
```

Eksport zawiera aktualny `predicted_company_id`, metodę i confidence. Kolumnę `truth_company_id` należy uzupełnić ręcznie tak, aby oferty tej samej rzeczywistej firmy dostały ten sam identyfikator.

Minimalny format wejścia do ewaluatora:

```csv
source,source_id,truth_company_id
olx,123,company-001
jooble,ABC-7,company-001
adzuna,987,company-002
```

Ocena jest wykonywana pairwise i zwraca precision, recall oraz F1:

```bash
agregator evaluate-resolution \
  --path company_ground_truth.csv \
  --db agregator.sqlite3
```

Dzięki temu benchmark 1000 ofert może mierzyć jakość deduplikacji, a nie tylko liczbę utworzonych rekordów.

### 14. Znalezienie oficjalnych stron i kanałów B2B

Wymaga `BRAVE_SEARCH_API_KEY`:

```bash
agregator enrich-db --db agregator.sqlite3 --limit 20
```

Domyślnie przetwarzane są firmy z `identity_confidence >= 0.7`.

### 15. Wyniki GREEN i eksport

```bash
agregator green --db agregator.sqlite3 --limit 100
agregator export-green --db agregator.sqlite3 --output green.csv
```

Każdy wynik zawiera źródło dowodu i tekst kontekstu, w którym kontakt został znaleziony.

### 16. Pełny eksport dla Faro

```bash
agregator export-dataset \
  --db agregator.sqlite3 \
  --output-dir export/faro
```

Powstają:

- `companies.csv` — kanoniczne firmy, aliasy, lokalizacje, WWW, confidence i źródła ofert,
- `job_postings.csv` — oferty wraz z `company_id`, provenance i danymi Company Resolution,
- `contact_channels.csv` — GREEN/REVIEW/IGNORE razem z evidence,
- `manifest.json` — wersja schematu, nazwy plików i liczności.

To jest stabilny punkt integracyjny przed przejściem z SQLite do docelowego API/PostgreSQL.

### Pojedyncza znana firma

```bash
agregator scan-url --company "Przykładowa Firma" --url https://example.com
agregator discover --company "Przykładowa Firma" --city Gdynia
```

## Katalog źródeł

`config/source_catalog.tsv` zawiera 91 źródeł z przygotowanej master-listy wraz z priorytetem, typem, stanem publicznego API i rekomendowanym sposobem integracji.

Kolejność wdrażania jest świadomie różna od prostego „scrapuj wszystko”:

1. API/feed/partnerstwo,
2. źródła oficjalne,
3. publiczny HTML po audycie ToS/robots,
4. Playwright tylko gdy jest potrzebny i zgodny z zasadami dostępu,
5. źródła partnerskie lub ograniczone nie są zastępowane obchodzeniem zabezpieczeń.

## Ważne ograniczenie adaptera OLX

Nie każda oferta OLX zawiera jednoznaczną nazwę przedsiębiorstwa. Adapter zapisuje provenance nazwy i confidence:

- `company.name` — bardzo wysoki confidence,
- `user.company_name` — wysoki confidence,
- `partner.name` — wysoki/średni confidence,
- `user.name` — niski confidence,
- `contact.name` — bardzo niski confidence.

Dzięki temu imię rekrutera typu „Kazimierz” nie jest automatycznie traktowane jako pewna nazwa firmy i nie jest domyślnie wysyłane do wyszukiwarki domen.

## Dokumentacja

Pełny plan: [`docs/PLAN.md`](docs/PLAN.md).

## Zasady projektu

1. Publiczne dane i publiczne strony.
2. Brak omijania logowania, CAPTCHA, paywalli i ograniczeń dostępu.
3. Każdy wynik kontaktowy musi mieć provenance/evidence.
4. Sama obecność e-maila nie oznacza `GREEN`.
5. Adaptery portali pracy są oddzielone od silnika enrichmentu.
6. Każde źródło przed wdrożeniem produkcyjnym przechodzi przegląd regulaminu i sposobu dostępu.
7. Outreach i automatyczna wysyłka wiadomości są poza zakresem tego repo.
