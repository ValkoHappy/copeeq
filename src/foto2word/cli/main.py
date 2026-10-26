"""Command line interface of foto2word (`f2w --help`)."""

import io
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from foto2word.application.convert import ConversionOptions, ConversionResult
from foto2word.composition import (
    build_converter,
    build_image_loader,
    build_vision_model,
    build_web_app,
)
from foto2word.domain.corrections import accept_all, reject_all
from foto2word.domain.document import Document
from foto2word.domain.errors import Foto2WordError
from foto2word.domain.patches import DocumentPatcher
from foto2word.domain.profile import RenderMode
from foto2word.evaluation.cases import PHOTO_SUFFIXES, load_cases
from foto2word.evaluation.report import EvalReport
from foto2word.evaluation.runner import (
    EvalRunner,
    LivePredictor,
    Predictor,
    Pricing,
    SavedPredictor,
)
from foto2word.infrastructure.config import ProviderName, Settings
from foto2word.infrastructure.profiles.yaml_repository import (
    YamlProfileRepository,
    builtin_profiles_dir,
)
from foto2word.infrastructure.raster.fonts import FontSet
from foto2word.synthetic.generator import SyntheticCaseGenerator

app = typer.Typer(no_args_is_help=True, help="Фото бумажного документа -> аккуратный Word.")


@app.callback()
def _console() -> None:
    """Never crash on a legacy console encoding (e.g. cp1251 on Windows)."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="replace")


ModeOption = Annotated[
    RenderMode, typer.Option("--mode", help="faithful — как на фото, standard — по стандарту")
]
ProfileOption = Annotated[
    str | None, typer.Option("--profile", help="Профиль оформления (по умолчанию — по типу)")
]
ProviderOption = Annotated[
    ProviderName | None, typer.Option(help="openai | anthropic | compatible")
]
CorrectionsOption = Annotated[
    bool, typer.Option("--corrections/--no-corrections", help="Применить правки от руки")
]


@app.command()
def convert(
    photos: Annotated[list[Path], typer.Argument(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("-o", "--output")],
    mode: ModeOption = RenderMode.FAITHFUL,
    profile: ProfileOption = None,
    corrections: CorrectionsOption = True,
    review: Annotated[
        bool, typer.Option("--review/--no-review", help="Самопроверка: сравнить результат с фото")
    ] = False,
    provider: ProviderOption = None,
    save_model: Annotated[
        Path | None, typer.Option(help="Сохранить распознанную модель документа (JSON)")
    ] = None,
) -> None:
    """Распознать фото и собрать документ Word."""
    settings = Settings()
    with _reported_errors():
        pages = build_image_loader(settings).load_all(photos)
        converter = build_converter(settings, provider)
        if review and not converter.can_review:
            typer.secho(
                "Самопроверка недоступна: нет Word или LibreOffice для превью.", fg="yellow"
            )
        result = converter.execute(pages, _options(mode, profile, corrections, review=review))
    _write(output, result.output)
    if save_model:
        _write_json(save_model, result.understood)
    _print_summary(result, output)


@app.command()
def render(
    model: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("-o", "--output")],
    mode: ModeOption = RenderMode.FAITHFUL,
    profile: ProfileOption = None,
    corrections: CorrectionsOption = True,
) -> None:
    """Собрать Word из сохранённой модели документа (без обращения к нейросети)."""
    with _reported_errors():
        document = Document.model_validate_json(model.read_text(encoding="utf-8"))
        result = build_converter(Settings()).rerender(
            document, _options(mode, profile, corrections)
        )
    _write(output, result.output)
    _print_summary(result, output)


@app.command("eval")
def run_eval(
    cases: Annotated[Path, typer.Option(help="Папка с кейсами")] = Path("evals/cases"),
    out: Annotated[Path | None, typer.Option(help="Куда сохранить отчёт и ответы")] = None,
    provider: ProviderOption = None,
    predictions: Annotated[
        Path | None, typer.Option(help="Пересчитать метрики по сохранённым ответам, без нейросети")
    ] = None,
    price_in: Annotated[float | None, typer.Option(help="$ за 1M входных токенов")] = None,
    price_out: Annotated[float | None, typer.Option(help="$ за 1M выходных токенов")] = None,
) -> None:
    """Прогнать эталонный набор и посчитать метрики качества."""
    settings = Settings()
    run_dir = out or Path("evals/runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
    predictor: Predictor = (
        SavedPredictor(predictions)
        if predictions
        else LivePredictor(build_vision_model(settings, provider), build_image_loader(settings))
    )
    with _reported_errors():
        results = EvalRunner(predictor, run_dir / "predictions").run(load_cases(cases))
    pricing = (
        Pricing(price_in, price_out) if price_in is not None and price_out is not None else None
    )
    report = EvalReport(tuple(results), pricing)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.md").write_text(report.to_markdown(), encoding="utf-8")
    (run_dir / "report.json").write_text(report.to_json(), encoding="utf-8")
    typer.echo(report.to_markdown())
    typer.secho(f"Отчёт: {run_dir}", fg=typer.colors.GREEN)


@app.command()
def synth(
    count: Annotated[int, typer.Option(help="Сколько кейсов сгенерировать")] = 20,
    out: Annotated[Path, typer.Option(help="Папка для кейсов")] = Path("evals/synthetic"),
    seed: Annotated[int, typer.Option(help="Зерно случайности (воспроизводимость)")] = 1,
) -> None:
    """Сгенерировать синтетические фото документов с известным правильным ответом."""
    with _reported_errors():
        generator = SyntheticCaseGenerator(
            FontSet.discover(), YamlProfileRepository(builtin_profiles_dir()), seed
        )
        cases = generator.generate(count, out)
    with_edits = sum(1 for case in cases if case.corrections)
    typer.secho(f"Готово: {len(cases)} кейсов в {out}, с правками: {with_edits}", fg="green")


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Адрес")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Порт")] = 8000,
) -> None:
    """Запустить веб-сервис (страница загрузки фото и API)."""
    import uvicorn  # noqa: PLC0415 - only needed for this command

    typer.secho(f"Откройте http://{host}:{port}", fg="green")
    uvicorn.run(build_web_app(Settings()), host=host, port=port)


@app.command()
def edit(
    model: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    request: Annotated[str, typer.Argument(help="Что изменить, обычными словами")],
    output: Annotated[Path, typer.Option("-o", "--output", help="Новая модель документа (JSON)")],
    provider: ProviderOption = None,
) -> None:
    """Изменить сохранённую модель документа просьбой на естественном языке."""
    document = Document.model_validate_json(model.read_text(encoding="utf-8"))
    with _reported_errors():
        reviewed = build_vision_model(Settings(), provider).edit(document, request)
    outcome = DocumentPatcher().apply(document, reviewed.result)
    _write_json(output, outcome.document)
    for patch in outcome.applied:
        typer.echo(f"  [~] {patch.op.value} {patch.target_id}: {patch.reason}")
    if not outcome.applied:
        typer.secho("Изменений нет: модель не нашла, что поменять.", fg="yellow")
    typer.secho(f"Готово: {output}", fg="green")


@app.command()
def batch(
    folder: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    out: Annotated[Path, typer.Option(help="Папка для готовых документов")] = Path("out/batch"),
    mode: ModeOption = RenderMode.FAITHFUL,
    review: Annotated[bool, typer.Option("--review/--no-review")] = False,
    provider: ProviderOption = None,
) -> None:
    """Пакетная обработка: каждая подпапка (или каждое фото в корне) — отдельный документ."""
    settings = Settings()
    loader = build_image_loader(settings)
    converter = build_converter(settings, provider)
    jobs = _batch_jobs(folder)
    if not jobs:
        typer.secho("Фото не найдены.", fg="yellow")
        raise typer.Exit(code=1)
    failures = 0
    for name, photos in jobs:
        try:
            result = converter.execute(
                loader.load_all(photos), _options(mode, None, True, review=review)
            )
        except Foto2WordError as error:
            failures += 1
            typer.secho(f"  [x] {name}: {error}", fg="red")
            continue
        _write(out / f"{name}.docx", result.output)
        _write_json(out / f"{name}.docmodel.json", result.understood)
        flags = len(result.verification.flags)
        typer.echo(f"  [+] {name}: {result.understood.document_type.title} · проверить: {flags}")
    typer.secho(f"Готово: {len(jobs) - failures} из {len(jobs)} в {out}", fg="green")
    if failures:
        raise typer.Exit(code=1)


def _batch_jobs(folder: Path) -> list[tuple[str, list[Path]]]:
    def photos_in(directory: Path) -> list[Path]:
        return sorted(p for p in directory.iterdir() if p.suffix.lower() in PHOTO_SUFFIXES)

    jobs = [(d.name, photos_in(d)) for d in sorted(folder.iterdir()) if d.is_dir()]
    jobs += [(p.stem, [p]) for p in photos_in(folder)]
    return [(name, photos) for name, photos in jobs if photos]


@app.command()
def schema() -> None:
    """Напечатать JSON-схему модели документа."""
    typer.echo(json.dumps(Document.model_json_schema(), ensure_ascii=False, indent=2))


def _options(
    mode: RenderMode, profile: str | None, corrections: bool, *, review: bool = False
) -> ConversionOptions:
    return ConversionOptions(
        mode=mode,
        profile_id=profile,
        decide_correction=accept_all if corrections else reject_all,
        review=review,
    )


@contextmanager
def _reported_errors() -> Iterator[None]:
    try:
        yield
    except Foto2WordError as error:
        typer.secho(f"Ошибка: {error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from error


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _write_json(path: Path, document: Document) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document.model_dump_json(indent=2), encoding="utf-8")


def _print_summary(result: ConversionResult, output: Path) -> None:
    doc = result.understood
    typer.echo(f"Тип: {doc.document_type.title} ({doc.document_type.confidence:.0%})")
    typer.echo(f"Профиль: {result.profile.id} · блоков: {len(doc.blocks)}")
    for correction in result.corrections.applied:
        typer.echo(f"  [+] правка: «{correction.before}» -> «{correction.after}»")
    for correction in result.corrections.rejected:
        typer.echo(f"  [-] отклонена: «{correction.before}» -> «{correction.after}»")
    for correction in result.corrections.failed:
        typer.secho(
            f"  [!] не применена (фрагмент не найден): «{correction.before}»",
            fg=typer.colors.YELLOW,
        )
    for suggestion in doc.suggestions:
        typer.echo(f"  [?] возможно ошибка: «{suggestion.text}» -> «{suggestion.proposal}»")
    if doc.fields:
        typer.echo("Сверьте с оригиналом:")
        for field in doc.fields:
            typer.echo(f"  · {field.kind.value}: {field.value}")
    if result.review is not None:
        applied = [p for r in result.review.rounds for p in r.applied]
        typer.echo(f"Самопроверка: раундов {len(result.review.rounds)}, исправлений {len(applied)}")
        for patch in applied:
            typer.echo(f"  [~] {patch.op.value} {patch.target_id}: {patch.reason}")
    if result.verification.flags:
        typer.secho("Проверьте особо:", fg=typer.colors.YELLOW)
        for flag in result.verification.flags:
            value = f" «{flag.value}»" if flag.value else ""
            typer.echo(f"  [!] {flag.block_id}: {flag.message}{value}")
    if result.provenance:
        p = result.provenance
        typer.echo(f"Модель: {p.provider}/{p.model} · промпт {p.prompt_version}")
    typer.secho(f"Готово: {output}", fg=typer.colors.GREEN)
