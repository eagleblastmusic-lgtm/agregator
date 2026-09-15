# Faro — scraper rollout

## Cel

Głównym zadaniem kolektora Faro jest odczytanie możliwie szerokiego zestawu **publicznie dostępnych ofert pracy** z katalogu źródeł i zachowanie informacji z każdego portalu osobno.

API nie jest wymaganiem produktu. Jeżeli dane źródło ma użyteczny oficjalny feed/API, może być dodatkowym adapterem, ale brak klucza API nie może zatrzymywać rozwoju scraperów publicznych stron innych serwisów.

Nie obchodzimy logowania, CAPTCHA, paywalli, anty-botów ani innych kontroli dostępu.

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
adaptery zaimplementowane: 17
pozostałe:                74
```

Zaimplementowane adaptery:

| Źródło | Adapter | Tryb | Stan rollout |
|---|---|---|---|
| Pracuj.pl | `pracuj` | public sitemap + HTML | experimental |
| Aplikuj.pl | `aplikuj` | public HTML | experimental |
| OLX Praca | `olx` | public web endpoint | experimental |
| Just Join IT | `justjoinit` | public HTML | experimental |
| No Fluff Jobs | `nofluffjobs` | public HTML | experimental |
| theprotocol.it | `theprotocol` | public HTML | experimental |
| Bulldogjob | `bulldogjob` | public HTML | experimental |
| RocketJobs | `rocketjobs` | public HTML | experimental |
| ePraca / CBOP | `epraca` | official partner feed | implemented |
| Nabory KPRM | `kprm` | official public HTML | experimental |
| Jooble Polska | `jooble` | partner API | optional source method |
| Careerjet Polska | `careerjet` | publisher API | optional source method |
| NGO.pl — praca i współpraca | `ngo` | public HTML | experimental |
| Kariera w Finansach | `karierawfinansach` | public HTML | experimental |
| Skillshot.pl | `skillshot` | public HTML | experimental |
| OfertyPracy.edu.pl | `ofertypracyedu` | official public HTML | experimental |
| Adzuna Polska | `adzuna` | partner API | optional source method |

`experimental` oznacza, że parser istnieje, ale przed uznaniem integracji za produkcyjnie stabilną trzeba potwierdzić aktualne reguły dostępu, paginację i jakość parsera na realnych danych.

## A0 — stan po batchu S2

W katalogu jest 14 źródeł A0. Dla publicznie/dozwolenie dostępnych ścieżek, które wybraliśmy, mamy już adaptery m.in. dla Pracuj, OLX, Just Join IT, No Fluff Jobs, RocketJobs, ePraca, KPRM, Jooble, Kariera w Finansach, Skillshot i OfertyPracy.edu.pl.

**3 A0 pozostają bez adaptera i są świadomie na HOLD:**

| Źródło | Decyzja bieżąca |
|---|---|
| Praca.pl | HOLD — przed scraperem wymagana pozytywna weryfikacja warunków/uprawnienia do planowanego wykorzystania |
| LinkedIn Jobs | HOLD — brak obchodzenia ograniczeń LinkedIn; potrzebna dozwolona ścieżka publiczna/partnerska |
| Indeed Polska | HOLD — brak obchodzenia anty-bot/login; potrzebna dozwolona ścieżka publiczna/partnerska |

To kończy pierwszy przebieg A0 bez prób obchodzenia ograniczeń. Rollout jest teraz w **A1**.

## Batch S1 — DONE baseline

- wspólny `PublicHtmlJobSource`,
- robots check,
- listing -> detail,
- JSON-LD `JobPosting`,
- fallback CSS selectors,
- retry i request delay,
- raw `source_payload`,
- sitemap walker z resumowalnym cursorem,
- Pracuj / Skillshot / NFJ / JustJoinIT / RocketJobs / Kariera w Finansach.

## Batch S2 — DONE baseline

### Nabory KPRM

Adapter `kprm`:

- publiczny listing i szczegóły,
- robots check,
- numer ogłoszenia,
- urząd/pracodawca,
- stanowisko, miasto i data,
- pełny widoczny tekst w `source_payload`,
- kontakty rekrutacyjne zachowywane jako raw evidence, a nie jako GREEN B2B.

### OfertyPracy.edu.pl

Adapter `ofertypracyedu`:

- publiczny listing MEN/SIO i paginacja,
- publiczne szczegóły `/oferty/<id>`,
- nazwa placówki, stanowisko, miasto,
- portal ID + oficjalny numer oferty,
- publiczne kandydatury WWW placówki,
- widoczny e-mail/telefon rekrutacyjny w `source_payload`,
- brak automatycznego promowania kontaktu rekrutacyjnego do GREEN.

## Batch S3 — IN PROGRESS

### NGO.pl

Adapter `ngo` został dodany jako pierwszy nowy A1:

- publiczna kategoria `Organizacja oferuje pracę, współpracę`,
- jawna paginacja `?page=N`,
- publiczne szczegóły ogłoszeń,
- `Ogłoszeniodawca` jako źródłowa nazwa firmy/organizacji,
- źródłowa strona WWW organizacji jako kandydat do późniejszej weryfikacji,
- pełny tekst ogłoszenia zachowany w `source_payload`,
- kontakt rekrutacyjny pozostaje raw evidence i nie jest automatycznie GREEN.

### Aplikuj.pl

Adapter `aplikuj`:

- publiczny listing `/praca` oraz paginacja `/praca/strona-N`,
- publiczne szczegóły `/oferta/<id>/<slug>`,
- preferowany parser JSON-LD `JobPosting` z fallbackiem HTML,
- nazwa pracodawcy, stanowisko, miasto, data publikacji,
- jawny NIP z treści ogłoszenia, jeżeli portal go publikuje,
- URL profilu pracodawcy zachowany w `source_payload`,
- pełny widoczny tekst zachowany jako source evidence,
- robots check, retry i request delay.

### theprotocol.it

Adapter `theprotocol`:

- publiczny listing `/praca` z numerem strony w `pageNumber`,
- rozpoznawanie publicznych URL ofert `/praca/...oferta...` i `/szczegoly/praca/...oferta...`,
- preferowany JSON-LD `JobPosting`,
- fallback HTML dla nazwy firmy/lokalizacji,
- source-specific dane zachowane bez cross-source deduplikacji,
- robots check, retry i request delay.

### Bulldogjob

Adapter `bulldogjob`:

- publiczny listing `/companies/jobs`,
- publiczne strony ofert `/companies/jobs/<id>-<slug>`,
- preferowany JSON-LD `JobPosting`,
- profile firm `/companies/profiles/<id>-<slug>` jako fallback źródła nazwy firmy,
- pełny source payload bez cross-source deduplikacji,
- robots check, retry i request delay,
- kompletne pokrycie mechanizmu dalszego ładowania/paginacji pozostaje do realnego smoke i dlatego adapter jest nadal `experimental`.

### Następne A1

Priorytet mają źródła oficjalne/publiczne i server-rendered, w których można zebrać dużo danych o pracodawcy bez obchodzenia ograniczeń. Kolejny audyt obejmuje przede wszystkim portale z czytelnym publicznym listingiem oraz źródła oficjalne/agencje.

## CLI scraper-first

Lista źródeł publicznych:

```bash
agregator-scrape sources
```

Pobranie wybranych źródeł:

```bash
agregator-scrape run \
  --sources kprm,ofertypracyedu,ngo,aplikuj,theprotocol,bulldogjob \
  --pages-per-source 1 \
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

Manualny GitHub Actions workflow `.github/workflows/public-scraper-smoke.yml` wykonuje kontrolowany realny smoke publicznych adapterów bez sekretów.

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

Benchmark jakości pozostaje ważny, ale pełni rolę kontroli jakości systemu; nie jest blokadą przed rozszerzaniem publicznie/dozwolenie dostępnych scraperów.
