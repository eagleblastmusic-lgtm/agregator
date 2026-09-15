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
9. Finalna deduplikacja do jednej firmy następuje dopiero w widoku biznesowym/Excelu.
10. Do finalnego Excela trafiają firmy z kwalifikowanym kanałem `GREEN` i zachowanym dowodem.

---

## 3. Zasady dostępu do źródeł

- Używamy publicznie dostępnych stron, jawnych sitemap/feedów oraz autoryzowanych źródeł partnerskich, gdy są przydatne.
- API jest opcjonalną metodą pobierania danych, a nie warunkiem produktu.
- Nie obchodzimy logowania, CAPTCHA, paywalli, anty-botów ani kontroli dostępu.
- Każdy scraper publicznych stron sprawdza `robots.txt`.
- Jeżeli jawne warunki źródła zabraniają planowanego wykorzystania, źródło trafia do `HOLD`, a nie do mechanizmu obchodzenia blokady.
- Adapter ma failure state; nie próbuje ukrywać swojej tożsamości ani omijać ograniczeń.

---

## 4. Stan funkcjonalny

```text
P0  zasady raw-data / no cross-source dedup        DONE
P1  katalog źródeł 91                              DONE baseline
P2  wspólny silnik scraperów                       IN PROGRESS / baseline ready
P3  rollout scraperów źródło po źródle             IN PROGRESS
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

## 5. P0 — zamrożenie zasad raw-data

Status: **DONE**.

Warstwa append-only `job_posting_observations` zachowuje każdą obserwację kolektora i pełny serializowany `JobPosting`. Model `JobPosting` posiada dodatkowo `source_payload`, dzięki czemu scraper może zachować source-specific struktury, np. JSON-LD.

Przed jakimkolwiek normalizowanym upsertem kolejność ingestu jest:

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

---

## 6. P1 — mapa wszystkich źródeł

Status: **DONE baseline; audyt każdego źródła trwa razem z rolloutem**.

`config/source_catalog.tsv` zawiera 91 źródeł i priorytety:

```text
A0  14
A1  36
B   24
C   17
```

Dla każdego źródła docelowo ustalamy:

```text
public start URL
listing strategy
pagination/cursor
job detail pattern
server-rendered / JS
robots
terms/access decision
company data coverage
adapter status
```

Szczegóły bieżącego rollout: `docs/SCRAPER_ROLLOUT.md`.

---

## 7. P2 — wspólny silnik scraperów

Status: **BASELINE IMPLEMENTED**.

### `PublicHtmlJobSource`

Wspólna warstwa dla publicznych serwisów HTML:

- robots.txt przed listingiem i detailem,
- request delay,
- bounded retry,
- list page -> detail links,
- ograniczenie hostów,
- regex detail paths,
- paginacja/cursor,
- JSON-LD `JobPosting` jako preferowane źródło strukturalne,
- fallback CSS selectors,
- source payload zachowany w rekordzie,
- brak ukrytych/private API,
- brak CAPTCHA/login bypass.

### `SitemapHtmlJobSource`

Dla portali udostępniających jawne sitemap:

- sitemap index / urlset,
- filtrowanie wyłącznie URL ofert,
- chunking,
- resumowalny cursor `sitemap_index:offset`,
- robots check,
- wspólny parser detailu.

### `agregator-scrape`

Dedykowany scraper-first CLI:

```bash
agregator-scrape sources

agregator-scrape run \
  --sources all \
  --pages-per-source 5 \
  --db agregator.sqlite3
```

`all` oznacza publiczne adaptery scraper/feed. Partner API nie jest automatycznie wybierane przez ten CLI.

---

## 8. P3 — rollout źródeł

Status: **IN PROGRESS**.

Aktualnie katalog rozpoznaje **11/91 zaimplementowanych adapterów**. W tej liczbie są zarówno publiczne scrapery, jak i wcześniejsze opcjonalne integracje API/feed.

Pierwszy scraper batch obejmuje:

```text
pracuj
skillshot
nofluffjobs
justjoinit
rocketjobs
karierawfinansach
```

Dodatkowo wcześniej istnieją:

```text
olx
epraca
jooble
careerjet
adzuna
```

Publiczne adaptery pierwszego batchu pozostają `experimental`, dopóki nie przejdą realnego smoke i pełnego audytu paginacji/warunków.

### Następne źródła A0

Priorytet:

1. Nabory KPRM — jawny XML/publiczny format.
2. OfertyPracy.edu.pl — publiczny serwis MEN/SIO po audycie robots/paginacji.
3. Praca.pl — HOLD do pozytywnego rozstrzygnięcia warunków wykorzystania.
4. LinkedIn — HOLD; brak obchodzenia ograniczeń.
5. Indeed — HOLD; brak obchodzenia anty-botów/logowania.

Potem A1 -> B -> C.

---

## 9. P4 — surowa baza wszystkich rekordów

Status: **DONE baseline**.

SQLite przechowuje:

- append-only source observations,
- current source records,
- source runs/cursors,
- company links,
- source-provided identifiers,
- source-provided website candidates,
- immutable website/contact evidence.

Ważne rozróżnienie:

```text
raw observations != normalized current state != final company view
```

Nie wolno upraszczać tych trzech warstw do jednej tabeli.

---

## 10. P5 — Company Resolution bez utraty rekordów

Status: **V1 DONE; dalsza kalibracja na realnych danych**.

Company Resolution ma ustalić, które źródłowe rekordy dotyczą tej samej firmy. Wynik nie usuwa ani nie scala source observations.

Sygnały:

- nazwa i forma prawna,
- lokalizacja,
- NIP,
- REGON,
- KRS,
- źródłowa WWW,
- aliasy,
- verified website.

Fuzzy similarity pozostaje REVIEW-only. Konflikty jawnych identifierów nie powodują automatycznego merge.

---

## 11. P6 — oficjalna WWW firmy

Status: **V1 DONE**.

Kolejność:

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

Search ranking nie jest dowodem. Oficjalna domena wymaga weryfikacji treści pierwszej strony firmy.

---

## 12. P7 — crawler strony firmy

Status: **DONE baseline**.

Crawler przegląda publiczne first-party strony, m.in.:

```text
/
/kontakt
/wspolpraca
/partnerzy
/b2b
/dla-firm
/dostawcy
/franczyza
```

oraz sitemapę, w ramach limitów, robots i rate limiting.

---

## 13. P8 — klasyfikacja kontaktów

Status: **DONE baseline; calibration ongoing**.

### GREEN

Wyraźny kontekst istotny dla współpracy, np.:

- propozycje współpracy,
- kontakt dla partnerów biznesowych,
- oferty handlowe prosimy przesyłać na,
- zostań partnerem,
- kanał B2B/dostawców/franczyzy.

### REVIEW

- ogólny dział handlowy,
- ogólny kontakt z pewnym kontekstem biznesowym,
- formularz wymagający oceny.

### IGNORE

- recruitment/HR,
- support,
- privacy,
- wyraźny zakaz ofert handlowych,
- sygnał nieistotny dla celu.

`GREEN` jest kwalifikacją relevance/context i nie stanowi automatycznej opinii prawnej o zgodzie na dowolny marketing.

---

## 14. P9 — finalny Excel

Status: **BASELINE IMPLEMENTED**.

Komenda:

```bash
agregator-export export \
  --db agregator.sqlite3 \
  --output export/faro_firmy_kontakt.xlsx
```

Finalny widok:

```text
1 firma = 1 wiersz
```

Do arkusza trafiają firmy z co najmniej jednym `GREEN` wraz z:

```text
Firma
Miasto
WWW
Status
Kontakt główny
Typ kontaktu
Cel kontaktu
Pewność
Wszystkie kontakty GREEN
Dowód / kontekst
Sygnał
URL dowodu
NIP
REGON
KRS
Liczba ofert
Portale źródłowe
Data weryfikacji
```

Surowe rekordy z portali nie są przez eksport kasowane ani deduplikowane.

---

## 15. P10 — kontrola jakości

Status: **INFRASTRUCTURE DONE; real validation ongoing after source expansion**.

Benchmark służy do sprawdzania, czy:

- source records są kompletne,
- Company Resolution nie łączy różnych firm,
- official website jest prawidłowe,
- GREEN/REVIEW/IGNORE jest sensowne,
- evidence pozwala odtworzyć decyzję.

Początkowe progi jakości pozostają:

```text
Company Resolution F1 >= 0.95
Website Resolution F1 >= 0.95
Contact decision macro F1 >= 0.90
```

Benchmark **nie blokuje dodawania kolejnych publicznie/dozwolenie dostępnych scraperów**.

---

## 16. P11 — pełne resumowalne uruchomienie

Status: **PLANNED after wider source coverage**.

Docelowo jedno uruchomienie wykonuje:

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

Run musi być resumowalny. Awaria jednego portalu nie może niszczyć danych z pozostałych źródeł.

---

## 17. Co robimy teraz

Aktualna kolejność pracy:

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
 │   ├── batch S1: first public portals
 │   ├── KPRM XML
 │   ├── OfertyPracy.edu.pl
 │   └── A1 -> B -> C
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
