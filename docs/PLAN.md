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

## 2. Twarde zasady danych

1. Każdy rekord zwrócony przez każdy portal jest wartościową obserwacją źródłową.
2. Ta sama firma i ta sama oferta mogą występować wielokrotnie na różnych portalach.
3. Nie wykonujemy cross-source deduplikacji ofert.
4. `job_posting_observations` jest append-only i zachowuje historię kolejnych odczytów.
5. `job_postings` jest tylko bieżącym widokiem `(source, source_id)`.
6. `JobPosting.source_payload` zachowuje dane specyficzne dla źródła.
7. Company Resolution tworzy powiązanie do firmy, ale nie usuwa rekordów źródłowych.
8. Dane firmy z różnych portali mogą się uzupełniać i muszą zachować provenance.
9. Konsolidacja `1 firma = 1 wiersz` następuje dopiero w finalnym Excelu.
10. Kontakt rekrutacyjny z ogłoszenia nie jest automatycznie kanałem współpracy `GREEN`.
11. Finalny Excel wymaga kwalifikowanego kanału `GREEN` i zachowanego dowodu.

## 3. Zasady dostępu do źródeł

- priorytetem są publiczne strony HTML, jawne sitemap/feed oraz oficjalne źródła,
- API jest opcjonalną metodą pobierania, a nie warunkiem produktu,
- nie obchodzimy logowania, CAPTCHA, paywalli, anty-botów ani kontroli dostępu,
- publiczne scrapery sprawdzają `robots.txt`,
- niejasne lub niedozwolone ścieżki trafiają do `HOLD`,
- adapter ma czytelny failure state i nie próbuje ukrywać swojej tożsamości.

## 4. Stan etapów

```text
P0  raw-data invariant / no cross-source dedup      DONE
P1  master catalog 91                               DONE baseline
P2  wspólny silnik publicznych scraperów            DONE baseline
P3  rollout scraperów źródło po źródle              IN PROGRESS  ◀ TERAZ
P4  append-only raw database                        DONE baseline
P5  Company Resolution / linking                    V1 DONE
P6  official website resolution                     V1 DONE
P7  first-party website crawler                     DONE baseline
P8  contact intent classification                   DONE baseline
P9  finalny Excel 1 firma = 1 wiersz                DONE baseline
P10 quality control / benchmark                     infrastructure DONE
P11 pełny resumowalny run wszystkich źródeł         PLANNED after wider coverage
```

## 5. P1/P3 — katalog i rollout źródeł

Master catalog zawiera **91 źródeł**:

```text
A0  14
A1  36
B   24
C   17
```

Aktualnie mamy **19/91 adapterów**, więc **72 źródła pozostają**.

```text
pracuj
aplikuj
olx
justjoinit
nofluffjobs
theprotocol
bulldogjob
rocketjobs
epraca
kprm
jooble
careerjet
randstad
manpower
ngo
karierawfinansach
skillshot
ofertypracyedu
adzuna
```

Publiczne adaptery pozostają `experimental`, dopóki nie przejdą kontrolowanego realnego smoke oraz audytu pełnej paginacji i bieżących warunków źródła.

### A0

Po wdrożeniu dozwolonych/publicznych ścieżek trzy A0 pozostają świadomie na `HOLD`:

```text
Praca.pl       HOLD — potrzebne pozytywne rozstrzygnięcie warunków/uprawnienia
LinkedIn       HOLD — brak obchodzenia ograniczeń
Indeed         HOLD — brak obchodzenia anty-bot/login
```

### A1

Rollout A1 jest rozpoczęty. Najnowsze adaptery:

- `ngo` — publiczna kategoria NGO.pl z ofertami pracy/współpracy,
- `aplikuj` — publiczny listing i paginacja Aplikuj.pl,
- `theprotocol` — publiczny listing/detail theprotocol.it,
- `bulldogjob` — publiczny listing i strony ofert Bulldogjob; pełne pokrycie dalszego ładowania/paginacji wymaga jeszcze realnego smoke,
- `randstad` — publiczny listing Randstad Polska z jawną paginacją i stronami ofert; ukryty klient końcowy nie jest zgadywany, tylko oznaczany jako low-confidence agency fallback,
- `manpower` — publiczna wyszukiwarka Manpower Polska i strony `/pl/job/<id>/<slug>`; ukryty klient końcowy również nie jest zgadywany, a dane oferty i provenance zostają zachowane.

Następna kolejność: kolejne czytelne publiczne A1, źródła oficjalne/naukowe/BIP, serwisy agencji, a następnie B i C.

Szczegółowy stan: `docs/SCRAPER_ROLLOUT.md`.

## 6. P2 — wspólny silnik scraperów

`PublicHtmlJobSource` zapewnia:

- robots przed listingiem i detailem,
- request delay i bounded retry,
- listing -> detail links,
- ograniczenie hostów,
- regex detail paths,
- paginację/cursor tam, gdzie została potwierdzona,
- JSON-LD `JobPosting` jako preferowane źródło strukturalne,
- fallback CSS selectors,
- zachowanie source payload.

`SitemapHtmlJobSource` obsługuje jawne sitemap index/urlset, filtrowanie URL ofert, chunking i resumowalny cursor.

Scraper-first CLI:

```bash
agregator-scrape sources

agregator-scrape run \
  --sources all \
  --pages-per-source 5 \
  --db agregator.sqlite3
```

`all` oznacza publiczne adaptery scraper/feed. `partner_api` nie jest automatycznie wybierane.

## 7. P4 — pełna warstwa surowa

Ingest zachowuje kolejność:

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

Dodatkowy telefon, e-mail, NIP, REGON, URL lub inna wskazówka z jednego portalu nie ginie dlatego, że inny portal jej nie posiada.

## 8. P5 — Company Resolution bez utraty źródeł

Status: **V1 DONE; kalibracja trwa na realnych danych**.

Sygnały obejmują nazwę/formę prawną, lokalizację, NIP, REGON, KRS, source-provided WWW, aliasy i verified website. Fuzzy similarity pozostaje REVIEW-only, a konflikty identifierów nie powodują automatycznego merge.

## 9. P6 — oficjalna WWW firmy

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

Ranking wyszukiwarki nie jest dowodem. Oficjalna domena wymaga weryfikacji first-party.

## 10. P7/P8 — crawler firmy i klasyfikacja kontaktu

Crawler przegląda publiczne first-party strony, m.in. `/`, `/kontakt`, `/wspolpraca`, `/partnerzy`, `/b2b`, `/dla-firm`, `/dostawcy`, `/franczyza` oraz sitemapę.

Klasyfikacja:

- **GREEN** — wyraźny publiczny kontekst współpracy/partnerstwa/ofert handlowych,
- **REVIEW** — ogólny kontakt biznesowy/handlowy wymagający oceny,
- **IGNORE** — recruitment/HR, support, privacy, zakaz ofert lub brak właściwego kontekstu.

`GREEN` jest kwalifikacją relevance/context, nie automatyczną opinią prawną o zgodzie na dowolny marketing.

## 11. P9 — finalny Excel

```bash
agregator-export export \
  --db agregator.sqlite3 \
  --output export/faro_firmy_kontakt.xlsx
```

Finalny widok ma **1 firmę = 1 wiersz** i zawiera m.in. firmę, miasto, WWW, kwalifikowany kontakt, typ/cel/confidence, dowód i URL dowodu, NIP/REGON/KRS, liczbę ofert, portale źródłowe i datę weryfikacji.

Surowe rekordy z portali pozostają nietknięte.

## 12. P10 — kontrola jakości

Początkowe progi jakości:

```text
Company Resolution F1 >= 0.95
Website Resolution F1 >= 0.95
Contact decision macro F1 >= 0.90
```

Benchmark jest kontrolą jakości, a nie blokadą przed dodawaniem kolejnych publicznie/dozwolenie dostępnych scraperów.

## 13. P11 — pełne resumowalne uruchomienie

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

## 14. Co robimy teraz

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
 │   ├── theprotocol + Bulldogjob
 │   ├── Randstad + Manpower
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
