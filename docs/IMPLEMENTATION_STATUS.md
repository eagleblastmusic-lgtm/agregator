# Faro Employer Discovery Engine — implementation status

Aktualny zakres PR obejmuje M0–M3: enrichment kontaktów, agregację ofert, Company Resolution oraz dwuetapową weryfikację oficjalnej strony WWW.

## Gotowe baseline'y

- M0: crawler + evidence + GREEN/REVIEW/IGNORE.
- M1: OLX, Jooble, Adzuna, source registry, resumowalne runy, katalog 91 źródeł, benchmark i eksport danych.
- M2: konserwatywny Company Resolution v1, aliasy/lokalizacje, metody/confidence, ground truth, pairwise precision/recall/F1, fuzzy REVIEW bez automatycznego merge.
- M3: ranking wyników wyszukiwarki + first-party content verification z fallbackiem do kolejnych kandydatów.

## Cel najbliższego benchmarku

Próbka 1000 ofert ma dostarczyć danych do kalibracji:

- precision/recall/F1 Company Resolution,
- jakości fuzzy REVIEW,
- poprawności wyboru oficjalnej domeny,
- udziału firm z poprawnym enrichmentem,
- precision klasyfikacji GREEN/REVIEW/IGNORE,
- kosztu/czasu per źródło i per firma.

## Granice automatyzacji

- fuzzy podobieństwo nazw nie scala firm automatycznie,
- domena WWW jest mocnym sygnałem REVIEW, ale auto-merge wymaga wcześniejszej walidacji na ground truth,
- źródła partnerskie/API nie są zastępowane obchodzeniem uwierzytelniania lub zabezpieczeń,
- outreach pozostaje poza zakresem repo.
