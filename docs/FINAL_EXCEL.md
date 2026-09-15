# Faro — finalna baza firm w Excelu

## Zasada danych

Warstwa wejściowa i warstwa wyjściowa mają różne zasady.

### 1. Warstwa surowa — bez deduplikacji ofert między portalami

Każdy rekord odczytany z każdego portalu pracy pozostaje zachowany jako osobna obserwacja źródłowa.

Ta sama firma i nawet ta sama oferta mogą wystąpić wielokrotnie, ponieważ różne portale mogą zawierać różne informacje: nazwę firmy, adres, NIP/REGON, WWW, opis, telefon, dodatkowe dane pracodawcy itd.

Źródłowych rekordów nie usuwamy i nie zastępujemy tylko dlatego, że wyglądają na tę samą ofertę.

### 2. Warstwa finalna — jedna firma = jeden wiersz

Po zebraniu i wzbogaceniu danych powstaje osobny widok biznesowy do Excela.

Do finalnego arkusza trafiają tylko firmy, dla których system wykrył co najmniej jeden kanał `GREEN`, czyli publiczny i kontekstowo istotny sygnał współpracy/partnerstwa/ofert handlowych wraz z zachowanym dowodem.

Jedna firma występuje w tym arkuszu tylko raz. Informacje z wielu ofert i portali są agregowane na poziomie firmy, ale surowe rekordy źródłowe pozostają zachowane osobno w bazie.

## Eksport

Po instalacji:

```bash
agregator-export export \
  --db agregator.sqlite3 \
  --output export/faro_firmy_kontakt.xlsx
```

Jeżeli rozszerzenie nie zostanie podane, exporter doda `.xlsx`.

## Arkusz `Firmy kontakt`

Kolumny obejmują m.in.:

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

Jeżeli firma ma kilka kanałów GREEN, jeden najbardziej pewny kanał jest prezentowany jako kontakt główny, a wszystkie pozostałe pozostają w kolumnie `Wszystkie kontakty GREEN`.

## Ważne rozróżnienie

`GREEN` jest kwalifikacją systemu opartą na publicznym kontekście strony firmy, np. `propozycje współpracy`, `kontakt dla partnerów`, `oferty handlowe`, `zostań partnerem`.

Nie jest to automatyczne stwierdzenie zgody prawnej na dowolną formę marketingu. Dlatego Excel zachowuje URL i tekst dowodu, aby przed kontaktem można było ocenić konkretny kanał i kontekst.

## Docelowy pipeline

```text
wszystkie poznane portale pracy
        |
        v
scraper każdego dostępnego źródła
        |
        v
zachowaj każdy rekord źródłowy osobno
        |
        v
powiąż rekordy z firmami bez kasowania źródeł
        |
        v
zbierz NIP / REGON / WWW / adres / inne wskazówki
        |
        v
ustal oficjalną stronę firmy
        |
        v
crawl strony firmy
        |
        v
wykryj kanały współpracy
        |
        v
GREEN / REVIEW / IGNORE + evidence
        |
        v
finalny Excel: jedna firma = jeden wiersz, tylko firmy z GREEN
```
