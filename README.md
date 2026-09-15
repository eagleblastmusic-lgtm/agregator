# Agregator — Faro Employer Discovery Engine

Silnik do budowania bazy firm aktywnie rekrutujących, rozwiązywania ich tożsamości, weryfikowania oficjalnych stron WWW oraz wykrywania publicznych kanałów współpracy B2B z pełnym provenance i audit trail.

## Główny łańcuch

`oferta pracy -> firma -> Company Resolution -> kandydat WWW -> first-party verification -> crawl -> kanał współpracy -> evidence + confidence`

Projekt **nie wysyła wiadomości**, nie omija logowania, CAPTCHA, paywalli ani kontroli dostępu i nie próbuje pozyskiwać niepublicznych danych kontaktowych. Źródła partnerskie/API działają tylko z prawidłową konfiguracją i autoryzacją.

## Aktualny zakres M0–M4

- wspólny `JobSource` + `SourceRegistry`,
- adaptery: `olx`, `jooble`, `adzuna`, `careerjet`, `epraca`,
- katalog 91 źródeł w `config/source_catalog.tsv`,
- resumowalne pobieranie i `source_runs`,
- kontrolowany `benchmark-collect` round-robin,
- Company Resolution v1 z konserwatywnym exact-match i fuzzy REVIEW-only,
- aliasy i lokalizacje firm,
- jawne identyfikatory przedsiębiorstw z provenance/confidence,
- NIP/REGON z oficjalnego feedu ePraca,
- konflikty identyfikatorów bez automatycznego merge,
- źródłowe kandydatury WWW, np. ePraca `adresWww`,
- first-party verification każdej domeny przed uznaniem jej za oficjalną,
- search fallback przez wymienny `SearchProvider`, domyślnie Brave Search,
- strukturalne provenance rozwiązania domeny: `source_candidate`, `search`, `known_url`,
- crawler first-party z `robots.txt`, limitem stron i rate limitingiem,
- `sitemap.xml` i priorytety stron kontaktowych/B2B,
- ekstrakcja e-maili, formularzy i typowych obfuskowanych adresów,
- klasyfikacja `GREEN / REVIEW / IGNORE`,
- append-only audit dla weryfikacji WWW i snapshotów evidence,
- ręcznie etykietowane quality gates dla Company Resolution, domen i kontaktów,
- Employer Discovery Score 0–100,
- eksport Faro schema v5.

## Instalacja

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
```

## Konfiguracja

Najważniejsze zmienne znajdują się w `.env.example`.

### Wyszukiwanie WWW

```text
BRAVE_SEARCH_API_KEY=
AGREGATOR_USER_AGENT=FaroEmployerDiscovery/0.1
AGREGATOR_MAX_PAGES=12
AGREGATOR_REQUEST_DELAY=0.8
```

### Jooble

```text
JOOBLE_API_KEY=
JOOBLE_KEYWORDS=praca
JOOBLE_LOCATION=Polska
JOOBLE_RESULTS_PER_PAGE=20
```

### Adzuna

```text
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
ADZUNA_COUNTRY=pl
ADZUNA_RESULTS_PER_PAGE=20
```

### Careerjet Publisher API

Careerjet wymaga kompletnego, rzeczywistego kontekstu partnera:

```text
CAREERJET_API_KEY=
CAREERJET_REFERER=
CAREERJET_USER_IP=
CAREERJET_USER_AGENT=
CAREERJET_LOCALE=pl_PL
```

Adapter nie podstawia fikcyjnego `user_ip`, `user_agent` ani `Referer`.

### ePraca WebService v2

Wymaga wartości `Partner` nadanej integratorowi oraz dokładnie jednego zakresu:

```text
EPRACA_PARTNER=
EPRACA_LANGUAGE=pl
EPRACA_WOJEWODZTWO=
EPRACA_JEDNOSTKA=
EPRACA_ALL=
```

Przykładowo należy ustawić tylko jedno z: `EPRACA_WOJEWODZTWO`, `EPRACA_JEDNOSTKA`, `EPRACA_ALL=true`.

## Podstawowe użycie

### Inicjalizacja bazy

```bash
agregator db-init --db agregator.sqlite3
```

### Lista adapterów

```bash
agregator sources
```

Aktualnie rejestrowane są: `adzuna`, `careerjet`, `epraca`, `jooble`, `olx`.

### Pobranie jednego źródła

```bash
agregator collect --source olx --pages 2
agregator collect --source jooble --pages 1
agregator collect --source adzuna --pages 1
```

Careerjet i ePraca można uruchomić analogicznie po poprawnej konfiguracji partnera/integratora.

### Kontrolowany benchmark 1000 ofert

```bash
agregator benchmark-collect \
  --db agregator.sqlite3 \
  --sources olx,jooble,adzuna \
  --target-jobs 1000 \
  --max-rounds 100
```

Collector działa round-robin: każde aktywne źródło dostaje najwyżej jedną stronę w rundzie. Źródła bez wymaganej konfiguracji są wyłączane, a powtarzające się błędy mają limit.

### Historia runów

```bash
agregator runs --db agregator.sqlite3 --limit 50
```

Każdy run zapisuje m.in. status, kursory, liczbę stron, oferty insert/update, nowe firmy, czas i skrócony błąd.

## Company Resolution

Resolver nie wykonuje automatycznego fuzzy-merge. Automatyczne łączenie jest konserwatywne i opiera się na znormalizowanej nazwie, lokalizacji, jednoznaczności kandydata i confidence źródła.

Każda oferta zapisuje m.in.:

- `company_resolution_method`,
- `company_resolution_confidence`,
- provenance i confidence nazwy pracodawcy.

Potencjalne duplikaty można skierować do ręcznego review:

```bash
agregator resolution-review \
  --db agregator.sqlite3 \
  --min-score 0.82 \
  --limit 100
```

Komenda **niczego nie scala**.

## Jawne identyfikatory firm

`JobPosting` może zawierać `CompanyIdentifier`. Obserwacje są normalizowane i przechowywane w `company_identifiers` wraz z provenance, confidence i `observation_count`.

Rozpoznawane są m.in. NIP, REGON i KRS. ePraca mapuje NIP i REGON z oficjalnego feedu. Ten sam identyfikator pod więcej niż jednym `company_id` jest traktowany jako konflikt do REVIEW, a nie sygnał do automatycznego merge.

## Weryfikacja oficjalnej strony WWW

Pipeline rozróżnia trzy finalne źródła rozwiązania domeny:

- `source_candidate` — URL pochodzi bezpośrednio ze źródła oferty i przeszedł first-party verification,
- `search` — domena została znaleziona przez SearchProvider i zweryfikowana,
- `known_url` — domena została jawnie podana do `scan-url`.

`website_resolution_source` zachowuje konkretne provenance, np. `official_feed.adresWww` albo `brave`. Każda `WebsiteVerificationAttempt` ma własne `origin` i `source`.

Źródłowy URL nie jest akceptowany w ciemno. Kolejność enrichmentu jest następująca:

`source website candidates -> first-party verification -> jeśli brak sukcesu: search -> first-party verification -> crawl kontaktów`

Dzięki temu poprawny URL z feedu może oszczędzić zapytanie do wyszukiwarki, ale błędny URL nie obniża jakości rozwiązania domeny.

### Enrichment bazy

```bash
agregator enrich-db --db agregator.sqlite3 --limit 20
```

Wymaga `BRAVE_SEARCH_API_KEY` wtedy, gdy trzeba wykonać search fallback.

### Pojedyncza firma

```bash
agregator scan-url \
  --company "Przykładowa Firma" \
  --url https://example.com

agregator discover \
  --company "Przykładowa Firma" \
  --city Gdynia
```

## Benchmark techniczny

```bash
agregator benchmark --db agregator.sqlite3
```

Raport obejmuje m.in.:

- liczbę ofert, firm i źródeł,
- Company Resolution methods,
- pokrycie jawnych identyfikatorów i konflikty,
- skuteczność enrichmentu,
- `website_candidates_total`,
- `companies_with_website_candidates`,
- `source_verified_websites`,
- `source_website_candidate_company_rate`,
- `source_verified_website_rate`,
- `source_verified_share_of_found`,
- `website_resolution_origin_counts`,
- `source_verified_website_counts`,
- GREEN/REVIEW/IGNORE,
- Employer Discovery Score,
- `source_run_metrics` z czasem i health per source.

## Ground truth i quality gate

### Company Resolution

```bash
agregator export-ground-truth \
  --db agregator.sqlite3 \
  --output company_ground_truth.csv \
  --limit 1000

agregator evaluate-resolution \
  --db agregator.sqlite3 \
  --path company_ground_truth.csv
```

### Oficjalna domena

```bash
agregator export-website-ground-truth \
  --db agregator.sqlite3 \
  --output website_ground_truth.csv \
  --limit 1000

agregator evaluate-website \
  --db agregator.sqlite3 \
  --path website_ground_truth.csv
```

`__none__` oznacza ręcznie potwierdzony brak oficjalnej strony.

### Kontakty

```bash
agregator export-contact-ground-truth \
  --db agregator.sqlite3 \
  --output contact_ground_truth.csv \
  --limit 1000

agregator evaluate-contacts \
  --db agregator.sqlite3 \
  --path contact_ground_truth.csv
```

### Wspólny pakiet etykiet

```bash
agregator export-quality-labels \
  --db agregator.sqlite3 \
  --output-dir benchmark/labels \
  --job-limit 1000 \
  --company-limit 1000 \
  --contact-limit 1000
```

### Quality gate

```bash
agregator quality-gate \
  --db agregator.sqlite3 \
  --resolution-truth benchmark/labels/company_resolution_truth.csv \
  --website-truth benchmark/labels/website_resolution_truth.csv \
  --contact-truth benchmark/labels/contact_classification_truth.csv \
  --fail-on-error
```

Domyślne progi:

- Company Resolution F1 >= 0.95,
- Website Resolution F1 >= 0.95,
- Contact decision macro F1 >= 0.90.

## Kontakty i evidence

Crawler przeszukuje first-party strony firmy, w tym priorytetowe ścieżki typu `/kontakt`, `/wspolpraca`, `/partnerzy`, `/b2b`, `/dla-firm`, `/dostawcy` i `/franczyza`.

Wyniki klasyfikowane są jako:

- `GREEN` — silny publiczny kanał zgodny z celem,
- `REVIEW` — wymaga ręcznej oceny,
- `IGNORE` — kanał nieodpowiedni do celu.

Formularz zawierający zgodę na informacje handlowe nie jest automatycznie traktowany jako GREEN.

```bash
agregator green --db agregator.sqlite3 --limit 100
agregator export-green --db agregator.sqlite3 --output green.csv
```

Każdy kontakt zachowuje `evidence_url`, `evidence_text`, signal i confidence. Audit przechowuje immutable snapshoty z SHA-256.

## Eksport dla Faro — schema v5

```bash
agregator export-dataset \
  --db agregator.sqlite3 \
  --output-dir export/faro
```

Powstają:

- `companies.csv`,
- `job_postings.csv`,
- `company_identifiers.csv`,
- `company_website_candidates.csv`,
- `contact_channels.csv`,
- `website_verification_runs.csv`,
- `contact_evidence_snapshots.csv`,
- `manifest.json`.

`website_verification_runs.csv` zawiera także `resolution_origin` i `resolution_source`. `website_attempts_json` zachowuje provenance każdej sprawdzonej kandydatury.

## Katalog źródeł

`config/source_catalog.tsv` zawiera 91 źródeł wraz z priorytetem, typem, stanem integracji i rekomendowaną drogą dostępu.

Kolejność integracji jest świadomie konserwatywna:

1. oficjalne API/feed/partnerstwo,
2. źródła oficjalne,
3. publiczny HTML po review technicznym i regulaminowym,
4. automatyzacja przeglądarki tylko tam, gdzie jest potrzebna i zgodna z zasadami dostępu,
5. brak zastępowania integracji partnerskich obchodzeniem uwierzytelniania lub zabezpieczeń.

## Ważne ograniczenie adaptera OLX

Nie każda oferta OLX zawiera jednoznaczną nazwę przedsiębiorstwa. Adapter zachowuje provenance i confidence. Imię konta lub osoby kontaktowej nie jest automatycznie traktowane jako pewna nazwa firmy i przy niskim confidence nie trafia domyślnie do automatycznego enrichmentu.

## Dokumentacja

- pełny plan: [`docs/PLAN.md`](docs/PLAN.md),
- status wdrożenia: [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md).

## Zasady projektu

1. Publiczne dane i publiczne strony.
2. Brak omijania logowania, CAPTCHA, paywalli i kontroli dostępu.
3. Każdy wynik kontaktowy ma provenance/evidence.
4. Sama obecność e-maila nie oznacza `GREEN`.
5. Adaptery portali pracy są oddzielone od silnika enrichmentu.
6. Fuzzy Company Resolution pozostaje REVIEW-only.
7. Identyczny NIP/REGON nie powoduje automatycznego merge bez zwalidowanej reguły.
8. Źródłowy URL firmy nie jest automatycznie uznawany za oficjalną domenę.
9. Quality gate opiera się na ręcznie oznaczonym ground truth.
10. Outreach i automatyczna wysyłka wiadomości są poza zakresem repo.
