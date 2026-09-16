# Faro — live source verification — 2026-09-16

## Zakres

Ten dokument zapisuje wynik kontrolowanej weryfikacji 10 adapterów, które nie należały do wcześniejszego zestawu 9 źródeł zweryfikowanych produkcyjnie.

Zasada bezpieczeństwa pozostaje niezmienna: Faro nie obchodzi logowania, CAPTCHA, paywalli, `robots.txt`, odpowiedzi 403, anty-botów ani innych kontroli dostępu.

## Wynik

| Źródło | Adapter | Wynik live | Oferty widziane | Decyzja |
|---|---|---|---:|---|
| Nabory KPRM | `kprm` | sukces | 20 | zweryfikowane live |
| Randstad Polska | `randstad` | sukces | 30 | zweryfikowane live |
| Pracuj.pl | `pracuj` | 403 na używanej publicznej sitemap | 0 | HOLD — brak obchodzenia blokady |
| OLX Praca | `olx` | 403 na używanym publicznym endpointzie | 0 | HOLD — brak obchodzenia blokady |
| theprotocol.it | `theprotocol` | `robots.txt` blokuje używaną ścieżkę listingu | 0 | HOLD — respektujemy robots |
| Bulldogjob | `bulldogjob` | 403 na używanej ścieżce publicznej | 0 | HOLD — brak obchodzenia blokady; wymagana dozwolona ścieżka |
| ePraca / CBOP | `epraca` | brak `EPRACA_PARTNER` | — | adapter gotowy, live test wymaga dostępu partnerskiego |
| Jooble Polska | `jooble` | brak `JOOBLE_API_KEY` | — | adapter gotowy, live test wymaga klucza API |
| Careerjet Polska | `careerjet` | brak wymaganych danych API | — | adapter gotowy, live test wymaga danych partnerskich |
| Adzuna Polska | `adzuna` | brak `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | — | adapter gotowy, live test wymaga danych API |

## Wpływ na aplikację

Domyślny zestaw Etapu 1 obejmuje teraz 11 źródeł: wcześniejsze 9 oraz `kprm` i `randstad`.

Cztery źródła HOLD pozostają widoczne w GUI, ale są domyślnie wyłączone. Użytkownik może je jawnie zaznaczyć do diagnostyki, jednak system nie próbuje omijać aktualnych ograniczeń dostępu.

Cztery adaptery partnerskie/API również pozostają widoczne. Jeżeli wymagane dane dostępowe nie są skonfigurowane, backend pomija je z jawnym statusem `missing_required_environment` zamiast udawać udany live run.

## Dwa niezależne etapy

### Etap 1 — scraping ofert

- pobiera oferty z wybranych źródeł,
- zachowuje surowe obserwacje i provenance,
- tworzy/uzupełnia bazę SQLite,
- nie crawluje stron firm,
- nie wyszukuje maili,
- nie generuje końcowego Excela kontaktowego.

### Etap 2 — wyszukiwanie kontaktów

- używa istniejącej bazy SQLite z Etapu 1,
- nie pobiera nowych ofert,
- weryfikuje oficjalne strony firm,
- crawluje first-party WWW,
- wyszukuje i klasyfikuje kanały biznesowe jako `GREEN`, `REVIEW`, `IGNORE`,
- opcjonalnie używa Brave Search jako fallbacku do znalezienia oficjalnej strony firmy,
- generuje końcowy XLSX tylko z kwalifikowanymi kontaktami zgodnie z regułami eksportu.

## Automatyczna kontrola

Workflow `Verify Candidate Sources` ponownie próbuje wszystkie źródła objęte tą weryfikacją. Gate wymaga, aby źródła awansowane do zweryfikowanych (`kprm`, `randstad`) nadal zwracały realne oferty. Źródła HOLD są raportowane, ale ich spodziewana blokada dostępu nie powoduje fałszywego błędu całego gate'u. Skonfigurowane adaptery partnerskie muszą przejść live test; brak samych poświadczeń jest raportowany oddzielnie.
