"""Provider-independent prompts.

Every provider adapter uses the same texts so that eval results compare models, not prompts.
"""

from importlib.resources import files

from foto2word.application.ports import UnderstandingContext
from foto2word.domain.document import Document


def _read(name: str) -> str:
    resource = files("foto2word.infrastructure.providers") / "prompts" / name
    return resource.read_text(encoding="utf-8")


class Prompts:
    def __init__(
        self,
        understand: str = "understand.v1.md",
        review: str = "review.v1.md",
        edit: str = "edit.v1.md",
        fill: str = "fill.v1.md",
    ) -> None:
        self._understand = _read(understand)
        self._review = _read(review)
        self._edit = _read(edit)
        self._fill = _read(fill)
        self.fill_version = fill.removesuffix(".md")
        self.understand_version = understand.removesuffix(".md")
        self.review_version = review.removesuffix(".md")
        self.edit_version = edit.removesuffix(".md")

    def understand_system(self, context: UnderstandingContext) -> str:
        catalog = "\n".join(f"- `{t.id}` — {t.title}: {t.hints}" for t in context.catalog)
        return self._understand.replace("{catalog}", catalog)

    def review_system(self) -> str:
        return self._review

    def edit_system(self) -> str:
        return self._edit

    def fill_system(self) -> str:
        return self._fill

    @staticmethod
    def fill_instruction(sample: list[str]) -> str:
        lines = "\n".join(f"- {text}" for text in sample)
        return f"Образец формы, все тексты:\n{lines}\n\nВерни замены по схеме."

    @staticmethod
    def edit_instruction(document: Document, request: str) -> str:
        return (
            "Модель документа (JSON):\n"
            f"{document.model_dump_json(exclude_none=True)}\n\n"
            f"Просьба пользователя: {request}"
        )

    @staticmethod
    def photo_label(number: int, total: int) -> str:
        return f"Оригинал, фото {number} из {total}:"

    @staticmethod
    def rendered_label(number: int, total: int) -> str:
        return f"Собранный документ, страница {number} из {total}:"

    @staticmethod
    def understand_instruction(context: UnderstandingContext) -> str:
        text = "Опиши документ на фотографиях по схеме."
        if context.document_type_hint:
            text += f" Пользователь подтвердил тип документа: `{context.document_type_hint}`."
        return text

    @staticmethod
    def review_instruction(document: Document) -> str:
        return (
            "Текущая модель документа (JSON):\n"
            f"{document.model_dump_json(exclude_none=True)}\n\n"
            "Сравни собранный документ с оригиналом и верни патчи по схеме."
        )
