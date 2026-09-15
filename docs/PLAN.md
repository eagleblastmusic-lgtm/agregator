# Plan rozwoju — Faro Employer Discovery Engine

## 1. Cel produktu

Faro jest wewnętrznym silnikiem, który ma odczytać możliwie szeroki zbiór publicznych ofert pracy z poznanych źródeł, zachować każdy rekord źródłowy, ustalić firmy stojące za ofertami, znaleźć ich oficjalne strony internetowe i wykryć publiczne kanały współpracy B2B.

Końcowym artefaktem biznesowym jest **Excel: jedna firma = jeden wiersz**, ale dopiero po pełnym zachowaniu danych wejściowych.

```text
WSZYSTKIE POZNANE ŹRÓDŁA PRACY
              │
              ▼
       SCRAPER / PUBLIC FEED
              │
              ▼
 KAŻDY REKORD ŹRÓDŁOWY ZACHOWANY
      BEZ CROSS-SOURCE DEDUP
              │
              ▼
        LINKOWANIE DO FIRMY
      BEZ KASOWANIA ŹRÓDEŁ
              │
              ▼
 NAZWA / NIP / REGON / KRS / WWW / ADRES
              │
              ▼
     OFICJALNA STRONA FIRMY
              │
              ▼
      FIRST-PARTY WEBSITE CRAWL
              │
              ▼
 WSPÓŁPRACA / PARTNERZY / B2B / HANDLOWE
              │
              ▼
 GREEN / REVIEW / IGNORE + EVIDENCE
              │
              ▼
            EXCEL
       1 FIRMA = 1 WIERSZ
```

Repo nie wysyła wiadomości. Outreach pozostaje poza zakresem kolektora.

---

## 2. Niezmienne zasady danych

1. Każdy rekord zwrócony przez każdy portal jest wartościową obserwacją źródłową.
2. Ta sama firma i ta sama oferta mogą występować wielokrotnie na różnych portalach.
3. Nie wykonujemy cross-source deduplikacji ofert.
4. Ponowne odczytanie rekordu może zostać zachowane jako kolejna obserwacja historyczna.
5. `job_posting_observations` jest append-only.
6. `job_postings` jest tylko bieżącym widokiem `(source, source_id)`; nie jest warstwą utraty danych.
7. Company Resolution tworzy relację/powiązanie do firmy; nie usuwa rekordów źródłowych.
8. Dane o firmie z różnych portali mogą się uzupełniać i muszą zachować provenance.
9. Finalna konsolidacja do jednej firmy następuje dopiero w widoku biznesowym/Excelu.
10. Kontakt rekrutacyjny z ogłoszenia nie jest automatycznie kanałem współpracy `GREEN`.
11. Do finalnego Excela trafiają firmy z kwalifikowanym kanałem `GREEN` i zachowanym dowodem.

---

## 3. Zasady dostępu do źródeł

- Używamy publicznie dostępnych stron, jawnych sitemap/feedów oraz autoryzowanych źródeł partnerskich, gdy są przydatne.
- API jest opcjonalną metodą pobierania danych, a nie warunkiem produktu.
- Nie obchodzimy logowania, CAPTCHA, paywalli, anty-botów ani kontroli dostępu.
- Każdy scraper publicznych stron sprawdza `robots.txt`.
- Jeżeli jawne warunki źródła zabraniają planowanego wykorzystania albo status prawny jest niejasny, źródło trafia do `HOLD`.
- Adapter ma czytelny failure state; nie próbuje ukrywać swojej tożsamości ani omijać ograniczeń.

---

## 4. Stan funkcjonalny

```text
P0  zasady raw-data / no cross-source dedup        DONE
P1  katalog źródeł 91                              DONE baseline
P2  wspólny silnik scraperów                       DONE baseline
P3  rollout scraperów źródło po źródle             IN PROGRESS  ◀ TERAZ
P4  append-only raw database                       DONE baseline
P5  Company Resolution / linking                   V1 DONE
P6  official website resolution                    V1 DONE
P7  first-party website crawler                    DONE baseline
P8  contact intent classification                  DONE baseline
P9  finalny Excel 1 firma = 1 wiersz               DONE baseline
P10 quality control / benchmark                     infrastructure DONE
P11 pełny resumowalny run wszystkich źródeł         PLANNED after wider coverage
```

Największym bieżącym zadaniem jest **pokrycie źródeł scraperami**, a nie rozszerzanie benchmarków czy uzależnianie kolektora od partner API.

---

## 5. P0/P4 — pełna warstwa surowa

Status: **DONE baseline**.

Przed normalizowanym upsertem ingest wykonuje:

```text
source.collect()
      │
      ▼
record_job_observations()   ← append-only, bez deduplikacji
      │
      ▼
upsert_jobs()               ← bieżący widok source/source_id
      │
      ▼
company identifiers / website candidates
```

`JobPosting.source_payload` zachowuje source-specific dane, które nie mieszczą się jeszcze w wspólnym modelu. Dzięki temu dodatkowy telefon, e-mail, identyfikator, WWW lub fragment danych z jednego portalu nie ginie tylko dlatego, że inny portal go nie posiada.

---

## 6. P1 — mapa źródeł

Status: **DONE baseline; audyt trwa razem z rolloutem**.

`config/source_catalog.tsv` zawiera **91 źródeł**:

```text
A0  14
A1  36
B   24
C   17
```

Dla każdego źródła docelowo ustalamy public start URL, listing, paginację/cursor, detail pattern, sposób renderowania, robots, warunki dostępu, jakość danych pracodawcy oraz status adaptera.

Bieżący rollout: `docs/SCRAPER_ROLLOUT.md`.

---

## 7. P2 — wspólny silnik scraperów

Status: **DONE baseline**.

### Public HTML

`PublicHtmlJobSource` zapewnia:

- robots przed listingiem i detailem,
- request delay i bounded retry,
- listing -> detail links,
- ograniczenie hostów,
- regex detail paths,
- paginację/cursor,
- JSON-LD `JobPosting` jako preferowane źródło strukturalne,
- fallback CSS selectors,
- zachowanie source payload.

### Sitemap

`SitemapHtmlJobSource` obsługuje jawne sitemap index/urlset, filtrowanie URL ofert, chunking i resumowalny cursor.

### Scraper-first CLI

```bash
agregator-scrape sources

agregator-scrape run \
  --sources all \
  --pages-per-source 5 \
  --db agregator.sqlite3
```

`all` oznacza publiczne adaptery scraper/feed. `partner_api` nie jest automatycznie wybierane.

---

## 8. P3 — rollout źródeł

Status: **IN PROGRESS**.

Aktualnie katalog rozpoznaje **15/91 zaimplementowanych adapterów**; **76 pozostaje**.

Zaimplementowane są m.in.:

```text
pracuj
aplikuj
olx
justjoinit
nofluffjobs
rocketjobs
epraca
kprm
jooble
careerjet
ngo
karierawfinansach
skillshot
ofertypracyedu
adzuna
```

Publiczne adaptery pozostają `experimental`, dopóki nie przejdą kontrolowanego realnego smoke oraz audytu paginacji i bieżących warunków źródła.

### A0

Po wdrożeniu KPRM i OfertyPracy.edu.pl **3 A0 pozostają na HOLD**:

```text
Praca.pl       HOLD — potrzebne pozytywne rozstrzygnięcie warunków/uprawnienia
LinkedIn       HOLD — brak obchodzenia ograniczeń
Indeed         HOLD — brak obchodzenia anty-bot/login
```

Nie próbujemy sztucznie domknąć `14/14` przez obchodzenie ograniczeń. Przechodzimy do A1.

### A1 — rozpoczęty

Zaimplementowane nowe A1:

- `ngo` — publiczna kategoria NGO.pl `Organizacja oferuje pracę, współpracę`,
- `aplikuj` — publiczny listing/paginacja Aplikuj.pl, publiczne szczegóły, JSON-LD/fallback HTML i source evidence pracodawcy.

Następna kolejność audytu:

1. kolejne publiczne portale A1 z czytelnym listingiem/detailami,
2. EURAXESS / publiczne oferty naukowe,
3. Akademicka Baza Ogłoszeń MNiSW — po rozstrzygnięciu zakresu licencji dla planowanego wykorzystania,
4. BIP-y i inne oficjalne źródła,
5. publiczne serwisy agencji zatrudnienia,
6. następnie B i C.

---

## 9. P5 — Company Resolution bez utraty źródeł

Status: **V1 DONE; dalsza kalibracja na realnych danych**.

Company Resolution ustala, które rekordy źródłowe dotyczą tej samej firmy. Wynik nie usuwa ani nie scala `job_posting_observations`.

Sygnały obejmują nazwę/formę prawną, lokalizację, NIP, REGON, KRS, source-provided WWW, aliasy i verified website. Fuzzy similarity pozostaje REVIEW-only, a konflikty identifierów nie powodują automatycznego merge.

---

## 10. P6 — oficjalna WWW

Status: **V1 DONE**.

```text
website candidates ze wszystkich ofert firmy
       │
       ▼
first-party identity verification
       │
       ├── ACCEPT -> official website
       └── brak sukcesu
               │
               ▼
         SearchProvider fallback
               │
               ▼
       first-party verification
```

Search ranking nie jest dowodem. Oficjalna domena wymaga weryfikacji treści first-party.

---

## 11. P7/P8 — crawler firmy i klasyfikacja kontaktu

Status: **DONE baseline; calibration ongoing**.

Crawler przegląda publiczne first-party strony, m.in. `/`, `/kontakt`, `/wspolpraca`, `/partnerzy`, `/b2b`, `/dla-firm`, `/dostawcy`, `/franczyza` oraz sitemapę.

Klasyfikacja:

- **GREEN** — wyraźny publiczny kontekst współpracy/partnerstwa/ofert handlowych,
- **REVIEW** — ogólny kontakt biznesowy/handlowy wymagający oceny,
- **IGNORE** — recruitment/HR, support, privacy, zakaz ofert, brak właściwego kontekstu.

Kontakt rekrutacyjny znaleziony w ogłoszeniu pracy służy jako source evidence, ale sam w sobie nie jest `GREEN`.

---

## 12. P9 — finalny Excel

Status: **DONE baseline**.

```bash
agregator-export export \
  --db agregator.sqlite3 \
  --output export/faro_firmy_kontakt.xlsx
```

Finalny widok ma **1 firmę = 1 wiersz** i zawiera m.in. firmę, miasto, WWW, kwalifikowany kontakt, typ/cel/confidence, dowód i URL dowodu, NIP/REGON/KRS, liczbę ofert, portale źródłowe i datę weryfikacji.

Surowe rekordy z portali pozostają nietknięte.

---

## 13. P10 — kontrola jakości

Status: **INFRASTRUCTURE DONE; real validation rośnie razem z coverage**.

Początkowe progi jakości:

```text
Company Resolution F1 >= 0.95
Website Resolution F1 >= 0.95
Contact decision macro F1 >= 0.90
```

Benchmark jest kontrolą jakości, a nie blokadą przed dodawaniem kolejnych publicznie/dozwolenie dostępnych scraperów.

---

## 14. P11 — pełne resumowalne uruchomienie

Status: **PLANNED after wider source coverage**.

Docelowo jeden run wykonuje:

```text
1. wszystkie aktywne scrapery
2. append-only zapis każdej obserwacji
3. aktualizacja current source state
4. Company Resolution/linking
5. zebranie wszystkich employer clues
6. official website verification
7. first-party contact crawl
8. GREEN / REVIEW / IGNORE
9. Excel one-company-per-row
10. raport source health i błędów
```

Awaria jednego portalu nie może niszczyć danych z pozostałych źródeł.

---

## 15. Co robimy teraz

```text
P0 raw-data invariant                         DONE
 │
 ▼
P1 master catalog 91                         DONE baseline
 │
 ▼
P2 generic public scraper engine             DONE baseline
 │
 ▼
P3 scraper rollout                           ◀ TERAZ
 │   ├── A0 public/dozwolone ścieżki
 │   ├── KPRM + OfertyPracy.edu.pl
 │   ├── NGO.pl + Aplikuj.pl
 │   └── dalsze A1 -> B -> C
 ▼
P4–P9 utrzymywać i wzmacniać istniejący pipeline
 │
 ▼
P10 real quality checks na rosnącym zbiorze
 │
 ▼
P11 pełny scheduler/resumable end-to-end run
```

Najważniejszy KPI bieżącego etapu: **pokrycie źródeł i zachowanie pełnej informacji wejściowej**, nie liczba użytych API ani minimalna liczba rekordów po deduplikacji.
