"""Catalog of document types the system knows about."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DocumentType:
    id: str
    title: str
    hints: str
    """Short description that helps a model recognise the type."""


OTHER = DocumentType("other", "Другой документ", "Не подходит ни под один тип из каталога.")

DEFAULT_CATALOG: tuple[DocumentType, ...] = (
    DocumentType(
        "act", "Акт", "Акт осмотра, испытания, приёмки, выполненных работ; комиссия, подписи."
    ),
    DocumentType(
        "application",
        "Заявление / заявка",
        "Обращение к руководителю организации: шапка «Кому/От кого», "
        "слово «Заявление» или «Заявка», просьба.",
    ),
    DocumentType("contract", "Договор", "Стороны, предмет, права и обязанности, реквизиты сторон."),
    DocumentType("power_of_attorney", "Доверенность", "Доверитель, поверенный, полномочия, срок."),
    DocumentType("certificate", "Справка", "Подтверждение факта, выдана по месту требования."),
    DocumentType(
        "protocol",
        "Протокол",
        "Протокол собрания/заседания: присутствовали, повестка, слушали, решили.",
    ),
    DocumentType(
        "order", "Приказ / распоряжение", "Приказываю, номер и дата приказа, ответственные."
    ),
    DocumentType(
        "letter", "Деловое письмо", "Письмо организации: адресат, исходящий номер, обращение."
    ),
    DocumentType(
        "academic", "Учебная работа", "Реферат, курсовая, отчёт по практике, титульный лист."
    ),
    OTHER,
)
