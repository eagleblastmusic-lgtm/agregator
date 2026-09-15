# Faro — scraper rollout

## Cel

Głównym zadaniem kolektora Faro jest odczytanie możliwie szerokiego zestawu **publicznie dostępnych ofert pracy** z katalogu źródeł i zachowanie informacji z każdego portalu osobno.

API nie jest wymaganiem produktu. Jeżeli dane źródło ma użyteczny oficjalny feed/API, może być dodatkowym adapterem, ale brak klucza API nie może zatrzymywać rozwoju scraperów publicznych stron innych serwisów.

Nie obchodzimy logowania, CAPTCHA, paywalli ani innych kontroli dostępu.

## Niezmiennik danych

```text
portal A: oferta X ─┐
portal B: oferta X ─┼──► wszystkie rekordy zachowane osobno
portal C: oferta X ─┘
                         │
                         ▼
                  linkowanie do firmy
                  bez kasowania źródeł
                         │
                         ▼
                 finalny Excel firm
                 jedna firma = jeden wiersz
```

`job_posting_observations` jest append-only i nie ma constraintu deduplikującego rekordy między portalami. `job_postings` jest tylko bieżącym widokiem jednego rekordu danego źródła `(source, source_id)`.

## Stan katalogu

Master catalog: **91 źródeł**.

Aktualnie:

```text
adaptery zaimplementowane: 12
pozostałe:                79
```

Zaimplementowane adaptery:

| Źródło | Adapter | Tryb | Stan rollout |
|---|---|---|---|
| Pracuj.pl | `pracuj` | public sitemap + HTML | experimental |
| OLX Praca | `olx` | public web endpoint | experimental |
| Just Join IT | `justjoinit` | public HTML | experimental |
| No Fluff Jobs | `nofluffjobs` | public HTML | experimental |
| RocketJobs | `rocketjobs` | public HTML | experimental |
| ePraca / CBOP | `epraca` | official partner feed | implemented |
| Nabory KPRM | `kprm` | official public HTML | experimental |
| Jooble Polska | `jooble` | partner API | implemented, optional source method |
| Careerjet Polska | `careerjet` | publisher API | implemented, optional source method |
| Kariera w Finansach | `karierawfinansach` | public HTML | experimental |
| Skillshot.pl | `skillshot` | public HTML | experimental |
| Adzuna Polska | `adzuna` | partner API | implemented, optional source method |

`experimental` oznacza, że parser istnieje, ale przed uznaniem integracji za produkcyjnie stabilną trzeba potwierdzić aktualne reguły dostępu, warunki źródła, paginację i jakość parsera na realnych danych.

## A0 — aktualny priorytet

W katalogu jest 14 źródeł A0. Po wdrożeniu KPRM **4 A0 pozostają bez aktywnego adaptera**:

| Źródło | Decyzja bieżąca |
|---|---|
| Praca.pl | HOLD — przed scraperem wymagana pozytywna weryfikacja uprawnienia/warunków; publiczna stopka obecnie zawiera zakaz powielania/kopiowania/rozpowszechniania materiałów |
| LinkedIn Jobs | HOLD — nie opieramy Faro na obchodzeniu ograniczeń LinkedIn; wymaga dozwolonej ścieżki/partnerstwa/publicznego dostępu zgodnego z zasadami |
| Indeed Polska | HOLD — nie obchodzimy anty-bot/login; preferowana dozwolona ścieżka partnerska/feed albo publiczna ścieżka po audycie |
| OfertyPracy.edu.pl | NEXT — publiczny serwis MEN/SIO dla osób szukających pracy; potrzebna walidacja robots, listingu i paginacji |

## Kolejność rollout

### Batch S1 — DONE baseline

- wspólny `PublicHtmlJobSource`,
- robots check,
- listing -> detail,
- JSON-LD `JobPosting`,
- fallback CSS selectors,
- retry i request delay,
- raw `source_payload`,
- sitemap walker z resumowalnym cursorem,
- Pracuj / Skillshot / NFJ / JustJoinIT / RocketJobs / Kariera w Finansach.

### Batch S2 — IN PROGRESS

- Nabory KPRM: adapter publicznego HTML wdrożony; zachowuje pełny widoczny tekst ogłoszenia, numer ogłoszenia, datę, urząd i source-specific payload. Publiczny serwis sam pokazuje w stopce eksport `XML`; XML pozostaje kandydatem do późniejszego porównania/uzupełnienia danych.
- OfertyPracy.edu.pl: następny A0 po technicznym audycie listingu/robots/paginacji.
- Praca.pl pozostaje HOLD, dopóki warunki/uprawnienie nie pozwolą na taki sposób wykorzystania.
- Potem A1 zaczynając od stron server-rendered i źródeł oficjalnych/agencji z czytelną strukturą.

### Batch S3+

Kolejne źródła wybieramy z A1 -> B -> C według:

- publicznej dostępności,
- możliwości pełnej paginacji,
- jakości danych pracodawcy,
- stabilności HTML/feedu,
- ograniczeń robots/warunków,
- kosztu i niezawodności kolektora.

## CLI scraper-first

Lista źródeł publicznych:

```bash
agregator-scrape sources
```

Pobranie jednego źródła:

```bash
agregator-scrape run \
  --sources kprm \
  --pages-per-source 5 \
  --db agregator.sqlite3 \
  --strict
```

Pobranie wszystkich aktualnie zarejestrowanych publicznych adapterów scraper/feed:

```bash
agregator-scrape run \
  --sources all \
  --pages-per-source 5 \
  --db agregator.sqlite3
```

`agregator-scrape` celowo nie wybiera `partner_api`. Dzięki temu publiczny scraping nie jest uzależniony od JOOBLE/ADZUNA/CAREERJET credentials.

Manualny GitHub Actions workflow `.github/workflows/public-scraper-smoke.yml` pozwala wykonać kontrolowany realny smoke publicznych adapterów bez sekretów. Domyślnie wskazuje oficjalny serwis KPRM i zapisuje bazę oraz wynik jako artifact.

## Definition of Done dla pojedynczego źródła

Źródło nie jest uznane za stabilne tylko dlatego, że parser kompiluje się. Produkcyjny adapter powinien mieć:

1. potwierdzony publiczny punkt startowy,
2. sprawdzone robots i warunki dostępu,
3. pełną lub jasno opisaną strategię paginacji,
4. parser listingu/detailu lub jawnego feedu,
5. fixture tests bez requestów do internetu,
6. zachowanie pełnego source payload/provenance,
7. test braku cross-source deduplikacji,
8. kontrolowany realny smoke,
9. czytelny failure state bez prób obchodzenia blokady,
10. wpisany status w katalogu/rollout.

## Co następuje po pokryciu źródeł

Dane wejściowe pozostają pełne i wielokrotne. Następnie:

```text
raw source observations
  -> company linking/resolution
  -> zebranie wszystkich wskazówek firmy
  -> official website verification
  -> first-party website crawl
  -> GREEN / REVIEW / IGNORE + evidence
  -> finalny Excel
     1 firma = 1 wiersz
     tylko kwalifikowane kontakty GREEN
```

Benchmark jakości pozostaje ważny, ale pełni rolę kontroli jakości systemu; nie jest już blokadą przed rozszerzaniem legalnie/publicznie dostępnych scraperów.
