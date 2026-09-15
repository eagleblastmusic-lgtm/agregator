# Faro — blind ground-truth labeling CLI

Ten workflow służy wyłącznie do ręcznego oznaczania plików `labels/*_truth.csv` wygenerowanych przez kontrolowany benchmark oraz późniejszego, jawnie oddzielonego adjudication.

Najważniejsza zasada metodologiczna: **primary labeling pozostaje blind**. `label-next` i `label-set` nie czytają `labels/prediction_reference/` i nie mają opcji „zaakceptuj predykcję”. Predykcja może zostać pokazana przez osobną komendę `label-reference` dopiero po zapisaniu niezależnej etykiety danego wiersza.

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

`__exclude__` nie powinno być przekazywane przez `--value`; CLI wymaga jawnego `--exclude`. Dla kontaktów `--exclude` nie może być łączone z `--purpose`.

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

## Adjudication — pokazanie predykcji dopiero po truth

Po zapisaniu niezależnej etykiety konkretnego wiersza można jawnie pobrać odpowiadający rekord z `prediction_reference/`:

```bash
agregator-benchmark label-reference \
  --label-dir benchmark/run/labels \
  --kind company_resolution \
  --row 17
```

Komenda zwraca m.in.:

```text
kind
row_number
truth_value
truth_purpose
reference_path
prediction
```

Jeżeli `truth_*` dla wskazanego wiersza jest jeszcze puste, dostęp jest blokowany. Dzięki temu normalny przebieg pozostaje:

```text
blind evidence
    -> niezależna etykieta truth
    -> zapis do *_truth.csv
    -> dopiero wtedy label-reference
    -> adjudication / analiza błędu
```

`label-reference` dodatkowo porównuje stabilne pola identyfikujące rekord pomiędzy primary CSV a prediction-reference. Dla Company Resolution są to `source + source_id`, dla Website Resolution `company_id`, a dla Contact Classification `contact_id`. Jeżeli pliki zostały niezależnie przestawione lub rozjechały się, komenda odmawia pokazania predykcji zamiast po cichu zwrócić niewłaściwy rekord.

`label-reference` nie zmienia etykiety i nie kopiuje predykcji do truth. Ewentualna korekta po adjudication nadal wymaga osobnego `label-set --overwrite`.

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

Predykcje należy wykorzystywać do adjudication, analizy FP/FN i kalibracji reguł dopiero po zapisaniu niezależnych etykiet primary.
