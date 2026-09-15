# Faro — blind ground-truth labeling CLI

Ten workflow służy wyłącznie do ręcznego oznaczania plików `labels/*_truth.csv` wygenerowanych przez kontrolowany benchmark.

Najważniejsza zasada metodologiczna: **primary labeling pozostaje blind**. Komendy poniżej nie czytają `labels/prediction_reference/` i nie mają opcji „zaakceptuj predykcję”. Predykcje służą dopiero do adjudication i analizy błędów po zapisaniu niezależnej etykiety.

## Typy labelingu

Dozwolone `--kind`:

```text
company_resolution
website_resolution
contact_classification
```

## Pobranie następnego nieoznaczonego rekordu

```bash
agregator-benchmark label-next \
  --label-dir benchmark/run/labels \
  --kind company_resolution
```

Komenda zwraca JSON z:

```text
kind
complete
next.row_number
next.label_field
next.row
```

`row_number` jest 1-based względem wierszy danych CSV, bez nagłówka. Gdy plik jest kompletny, `complete=true` i `next=null`.

## Company Resolution

Etykieta `truth_company_id` jest ręcznym identyfikatorem grupy tożsamości firmy. Oferty należące do tej samej rzeczywistej firmy muszą dostać ten sam truth ID.

Przykład:

```bash
agregator-benchmark label-set \
  --label-dir benchmark/run/labels \
  --kind company_resolution \
  --row 17 \
  --value company-truth-0042
```

CLI nie podpowiada `predicted_company_id`, ponieważ mogłoby to wprowadzić confirmation bias.

## Website Resolution

Dla firmy z potwierdzoną oficjalną stroną podaj domenę albo URL. Wartość jest normalizowana do hosta bez `www.`.

```bash
agregator-benchmark label-set \
  --label-dir benchmark/run/labels \
  --kind website_resolution \
  --row 31 \
  --value https://www.example.pl/kontakt
```

Zapisana etykieta:

```text
example.pl
```

Jeśli po ręcznej weryfikacji firma nie ma oficjalnej strony WWW:

```bash
agregator-benchmark label-set \
  --label-dir benchmark/run/labels \
  --kind website_resolution \
  --row 32 \
  --value __none__
```

## Contact Classification

Dozwolone decyzje:

```text
green
review
ignore
```

Przykład:

```bash
agregator-benchmark label-set \
  --label-dir benchmark/run/labels \
  --kind contact_classification \
  --row 12 \
  --value green \
  --purpose business_partnership
```

`--purpose` jest opcjonalne, ale jeśli jest podane, musi być jednym z typów `ChannelPurpose` używanych przez silnik, np. `business_partnership`, `sales`, `supplier`, `franchise`, `generic`, `recruitment`, `support`, `privacy`, `negative`.

## Wykluczenie rekordu

Jeżeli na podstawie dostępnego evidence nie da się ustalić wiarygodnego ground truth, rekord można jawnie wykluczyć z scoringu:

```bash
agregator-benchmark label-set \
  --label-dir benchmark/run/labels \
  --kind website_resolution \
  --row 44 \
  --exclude
```

W CSV zostanie zapisane:

```text
__exclude__
```

Wykluczenie jest liczone przez `status` jako zakończony, ale audytowalny rekord i nie trafia do ewaluacji jakości.

## Ochrona przed przypadkowym nadpisaniem

Domyślnie `label-set` odmawia zmiany już oznaczonego wiersza. Świadoma korekta wymaga:

```bash
--overwrite
```

Przykład:

```bash
agregator-benchmark label-set \
  --label-dir benchmark/run/labels \
  --kind contact_classification \
  --row 12 \
  --value review \
  --overwrite
```

## Kontrola postępu

```bash
agregator-benchmark status \
  --label-dir benchmark/run/labels
```

W trybie skryptowym:

```bash
agregator-benchmark status \
  --label-dir benchmark/run/labels \
  --strict
```

`--strict` zwraca kod `2`, dopóki wszystkie trzy pliki nie są kompletne.

## Ewaluacja po labelingu

Po kompletnym primary labeling:

```bash
agregator-benchmark evaluate \
  --db benchmark/benchmark.sqlite3 \
  --label-dir benchmark/run/labels \
  --fail-on-error
```

Dopiero po zapisaniu niezależnych etykiet można otworzyć `labels/prediction_reference/` do adjudication, analizy FP/FN i kalibracji reguł.
