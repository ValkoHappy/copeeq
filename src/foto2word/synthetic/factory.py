"""Random but realistic Russian documents with known ground truth."""

import random
from collections.abc import Callable

from foto2word.domain.document import (
    Alignment,
    Block,
    Correction,
    Document,
    DocumentTypeGuess,
    ExtractedField,
    FieldKind,
    HeadingBlock,
    LabeledLineBlock,
    ListItemBlock,
    ParagraphBlock,
    RequisitesBlock,
    Run,
    SignatureLineBlock,
    SpacerBlock,
    SpacerSize,
    Suggestion,
    TableBlock,
    TableCell,
    TableRow,
    TwoColumnLineBlock,
)
from foto2word.domain.validation import MONTHS_GENITIVE, complete_inn12

SURNAMES = (
    "Иванов",
    "Петров",
    "Смирнов",
    "Кузнецов",
    "Попов",
    "Соколов",
    "Лебедев",
    "Козлов",
    "Новиков",
    "Морозов",
    "Волков",
    "Павлов",
    "Семёнов",
    "Голубев",
    "Виноградов",
    "Богданов",
)
FIRST_NAMES = ("Алексей", "Иван", "Сергей", "Дмитрий", "Андрей", "Николай", "Михаил", "Павел")
PATRONYMICS = ("Иванович", "Петрович", "Сергеевич", "Андреевич", "Николаевич", "Васильевич")
TOWNS = ("г. Архангельск", "г. Вологда", "п. Уемский", "г. Северодвинск", "г. Котлас", "г. Онега")
STREETS = ("ул. Ленина", "ул. Заводская", "пр. Ломоносова", "ул. Садовая", "ул. Мира", "ул. Победы")
ORGS = (
    'ООО "Теплосеть"',
    'АО "Водоканал"',
    'ООО "УК Северная"',
    'МУП "Горэлектросеть"',
    'ООО "Энергосбыт Поморья"',
)
ACT_SUBJECTS = (
    "гидравлического испытания трубопроводов системы отопления",
    "осмотра узла учёта тепловой энергии",
    "приёмки выполненных работ по замене запорной арматуры",
    "проверки готовности к отопительному периоду",
)
TYPO_PROBABILITY = 0.4
SIGNED_PROBABILITY = 0.8
TYPO_WORDS = ("испытания", "трубопроводов", "оборудования", "отопительному", "помещения")


class _Ids:
    def __init__(self) -> None:
        self._n = 0

    def __call__(self) -> str:
        self._n += 1
        return f"b{self._n}"


class DocumentFactory:
    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self._templates: tuple[Callable[[], Document], ...] = (
            self.act,
            self.application,
            self.measurement_protocol,
        )

    def create(self) -> Document:
        return self._rng.choice(self._templates)()

    # --- random values ------------------------------------------------------------------------

    def _person_short(self) -> str:
        first, patronymic = self._rng.choice(FIRST_NAMES), self._rng.choice(PATRONYMICS)
        return f"{self._rng.choice(SURNAMES)} {first[0]}.{patronymic[0]}."

    def _date_text(self, year: int) -> str:
        return f"«{self._rng.randint(1, 28)}» {self._rng.choice(MONTHS_GENITIVE)} {year} г."

    def _address(self) -> str:
        town, street = self._rng.choice(TOWNS), self._rng.choice(STREETS)
        return f"{town}, {street}, д. {self._rng.randint(1, 120)}"

    def _inn(self) -> str:
        return complete_inn12("29" + "".join(str(self._rng.randint(0, 9)) for _ in range(8)))

    def _typo(self, text: str) -> tuple[str, Suggestion | None]:
        """With some probability double a letter in one word and record it as a known typo."""
        words = [w for w in TYPO_WORDS if f" {w}" in text]
        if not words or self._rng.random() > TYPO_PROBABILITY:
            return text, None
        word = self._rng.choice(words)
        cut = self._rng.randint(2, len(word) - 2)
        broken = word[:cut] + word[cut] + word[cut:]
        return text.replace(f" {word}", f" {broken}", 1), Suggestion(
            block_id="", text=broken, proposal=word, reason="Опечатка: удвоенная буква"
        )

    # --- templates ----------------------------------------------------------------------------

    def act(self) -> Document:
        ids = _Ids()
        year = self._rng.randint(2023, 2027)
        place, date = self._rng.choice(TOWNS), self._date_text(year)
        chair, member = self._person_short(), self._person_short()
        subject = self._rng.choice(ACT_SUBJECTS)
        pressure = f"{self._rng.randint(4, 16)} кгс/см"
        minutes = f"{self._rng.choice((10, 15, 30))} мин"
        body, typo = self._typo(
            "Комиссия провела осмотр и испытания оборудования помещения "
            f"по адресу: {self._address()}."
        )
        blocks: list[Block] = [
            HeadingBlock(id=ids(), runs=(Run(text="АКТ"),)),
            HeadingBlock(id=ids(), level=2, runs=(Run(text=f"{subject} на {year} год"),)),
            TwoColumnLineBlock(id=ids(), left=place, right=date),
            SpacerBlock(id=ids(), size=SpacerSize.SMALL),
            ParagraphBlock(id=ids(), align=Alignment.LEFT, runs=(Run(text="Комиссия в составе:"),)),
            LabeledLineBlock(id=ids(), label="Председатель комиссии:", value=chair),
            LabeledLineBlock(id=ids(), label="Член комиссии:", value=member),
            ParagraphBlock(id=ids(), runs=(Run(text=body),)),
            ListItemBlock(
                id=ids(),
                marker="1.",
                runs=(
                    Run(text=f"Давление поднято до {pressure}"),
                    Run(text="2", superscript=True),
                    Run(text="."),
                ),
            ),
            ListItemBlock(
                id=ids(),
                marker="2.",
                runs=(Run(text=f"По истечении {minutes} падение давления не обнаружено."),),
            ),
            ListItemBlock(id=ids(), marker="3.", runs=(Run(text="Дефекты не выявлены."),)),
            SpacerBlock(id=ids(), size=SpacerSize.LARGE),
            SignatureLineBlock(
                id=ids(),
                label="Председатель комиссии",
                name=chair,
                has_signature_mark=self._rng.random() < SIGNED_PROBABILITY,
            ),
            SignatureLineBlock(
                id=ids(),
                label="Член комиссии",
                name=member,
                has_signature_mark=self._rng.random() < SIGNED_PROBABILITY,
            ),
        ]
        corrections = self._pick_corrections(
            [
                ("b2", f"{year} год", f"{year + 1} год"),
                ("b3", date, self._date_text(year + 1)),
                ("b9", pressure, f"{self._rng.randint(4, 16)} кгс/см"),
            ]
        )
        fields = [
            ExtractedField(kind=FieldKind.DATE, value=date, block_id="b3"),
            ExtractedField(kind=FieldKind.PERSON_NAME, value=chair, block_id="b6"),
            ExtractedField(kind=FieldKind.PERSON_NAME, value=member, block_id="b7"),
        ]
        return self._document(
            "act",
            title=f"Акт {subject}",
            blocks=blocks,
            corrections=corrections,
            fields=fields,
            typo=typo,
            typo_block="b8",
        )

    def application(self) -> Document:
        ids = _Ids()
        year = self._rng.randint(2024, 2027)
        surname, first, patronymic = (
            self._rng.choice(SURNAMES),
            self._rng.choice(FIRST_NAMES),
            self._rng.choice(PATRONYMICS),
        )
        inn, phone = self._inn(), "89" + "".join(str(self._rng.randint(0, 9)) for _ in range(9))
        address = self._address()
        word = self._rng.choice(("Заявление", "Заявка"))
        body, typo = self._typo(
            f"Прошу заключить договор теплоснабжения на {year} год "
            "для нежилого помещения по адресу: "
            f"{address}."
        )
        blocks: list[Block] = [
            RequisitesBlock(
                id=ids(),
                lines=(
                    "Генеральному директору",
                    self._rng.choice(ORGS),
                    self._person_short(),
                    f"от {surname}а {first[0]}.{patronymic[0]}.",
                    f"ИНН {inn}",
                    f"тел: {phone}",
                ),
            ),
            SpacerBlock(id=ids(), size=SpacerSize.LARGE),
            HeadingBlock(id=ids(), runs=(Run(text=word),)),
            ParagraphBlock(id=ids(), runs=(Run(text=body),)),
            SpacerBlock(id=ids(), size=SpacerSize.MEDIUM),
            TwoColumnLineBlock(
                id=ids(),
                left=self._date_text(year - 1),
                right=f"{surname} {first[0]}.{patronymic[0]}.",
            ),
        ]
        corrections = self._pick_corrections([("b4", f"на {year} год", f"на {year + 1} год")])
        fields = [
            ExtractedField(kind=FieldKind.INN, value=inn, block_id="b1"),
            ExtractedField(kind=FieldKind.PHONE, value=phone, block_id="b1"),
            ExtractedField(kind=FieldKind.ADDRESS, value=address, block_id="b4"),
        ]
        return self._document(
            "application",
            title=f"{word} на заключение договора",
            blocks=blocks,
            corrections=corrections,
            fields=fields,
            typo=typo,
            typo_block="b4",
        )

    def measurement_protocol(self) -> Document:
        ids = _Ids()
        year = self._rng.randint(2023, 2027)
        date = self._date_text(year)
        params = (
            ("Давление в подающем трубопроводе", "кгс/см2"),
            ("Температура теплоносителя", "°C"),
            ("Расход теплоносителя", "м3/ч"),
            ("Давление в обратном трубопроводе", "кгс/см2"),
        )
        rows = [
            TableRow(
                cells=tuple(
                    TableCell(runs=(Run(text=t),))
                    for t in ("№", "Показатель", "Значение", "Ед. изм.")
                )
            )
        ]
        values = []
        for number, (name, unit) in enumerate(params[: self._rng.randint(3, 4)], start=1):
            value = f"{self._rng.uniform(1, 95):.1f}".replace(".", ",")
            values.append(value)
            rows.append(
                TableRow(
                    cells=tuple(
                        TableCell(runs=(Run(text=t),)) for t in (str(number), name, value, unit)
                    )
                )
            )
        engineer = self._person_short()
        blocks: list[Block] = [
            HeadingBlock(id=ids(), runs=(Run(text="ПРОТОКОЛ ИЗМЕРЕНИЙ"),)),
            TwoColumnLineBlock(id=ids(), left=self._rng.choice(TOWNS), right=date),
            ParagraphBlock(id=ids(), runs=(Run(text=f"Объект: {self._address()}."),)),
            TableBlock(id=ids(), header_rows=1, rows=tuple(rows), column_widths=(1, 7, 3, 3)),
            SignatureLineBlock(
                id=ids(),
                label="Инженер",
                name=engineer,
                has_signature_mark=self._rng.random() < SIGNED_PROBABILITY,
            ),
        ]
        target = self._rng.choice(values)
        new_value = f"{self._rng.uniform(1, 95):.1f}".replace(".", ",")
        corrections = self._pick_corrections(
            [("b4", target, new_value), ("b2", date, self._date_text(year))]
        )
        fields = [
            ExtractedField(kind=FieldKind.DATE, value=date, block_id="b2"),
            ExtractedField(kind=FieldKind.PERSON_NAME, value=engineer, block_id="b5"),
        ]
        fields += [ExtractedField(kind=FieldKind.NUMBER, value=v, block_id="b4") for v in values]
        return self._document(
            "protocol",
            title="Протокол измерений",
            blocks=blocks,
            corrections=corrections,
            fields=fields,
            typo=None,
            typo_block="",
        )

    # --- assembly -----------------------------------------------------------------------------

    def _pick_corrections(self, options: list[tuple[str, str, str]]) -> list[Correction]:
        count = self._rng.choice((0, 1, 1, 2))
        chosen = self._rng.sample(options, min(count, len(options)))
        return [
            Correction(id=f"c{i}", block_id=block_id, before=before, after=after)
            for i, (block_id, before, after) in enumerate(chosen, start=1)
            if before != after
        ]

    @staticmethod
    def _document(
        type_id: str,
        *,
        title: str,
        blocks: list[Block],
        corrections: list[Correction],
        fields: list[ExtractedField],
        typo: Suggestion | None,
        typo_block: str,
    ) -> Document:
        suggestions = (typo.model_copy(update={"block_id": typo_block}),) if typo else ()
        return Document(
            document_type=DocumentTypeGuess(id=type_id, title=title, confidence=1.0),
            blocks=tuple(blocks),
            corrections=tuple(corrections),
            fields=tuple(fields),
            suggestions=suggestions,
        )
