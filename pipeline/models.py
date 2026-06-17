"""데이터 모델 (설계 §11). Meta=구조·출처·관계, Content=의미. 모델이 곧 XML/JSONL 직렬화의 단일 진실."""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ─────────────────────────── Enum / 기하 / 출처 (§11.1) ───────────────────────────
class ContentType(str, Enum):
    TEXT = "text"
    TABLE_ROW = "table-row"
    TABLE_NOTE = "table-note"
    LIST_ITEM = "list-item"
    PROCEDURE_STEP = "procedure-step"
    INFOGRAPHIC = "infographic"
    SCREENSHOT = "screenshot"
    FLOWCHART = "flowchart"
    FLOWCHART_EDGE = "flowchart-edge"
    GRAPH = "graph"
    WARNING = "warning"
    FOOTNOTE = "footnote"
    REFERENCE = "reference"


class ExtractMethod(str, Enum):
    PDF_TEXT = "pdf_text"
    OCR = "ocr"
    LAYOUT_ANALYSIS = "layout_analysis"


class BBox(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(ge=1)
    x0: float
    y0: float
    x1: float
    y1: float  # PDF point, 좌상단 원점


class SourceLocation(BaseModel):
    """검색 결과 하나로 원문 위치를 복원하기 위한 자기완결 출처(장·절·항 포함)."""
    model_config = ConfigDict(extra="forbid")
    file_name: str
    document_id: str
    page_no: int | None = None
    page_range: tuple[int, int] | None = None
    bbox: BBox | None = None
    extract_method: ExtractMethod
    heading_path: list[str] = Field(default_factory=list)
    locator: str | None = None
    dpi: int | None = None
    asset_id: str | None = None
    char_range: tuple[int, int] | None = None
    table_id: str | None = None
    figure_id: str | None = None
    transform: list[float] | None = None

    @model_validator(mode="after")
    def _locatable(self):
        if self.bbox is None and self.char_range is None:
            raise ValueError("bbox 또는 char_range 중 하나는 필수(위치 복원 보장)")
        return self


# ─────────────────────────── Meta (구조·출처·관계만) (§11.2) ───────────────────────────
_VISUAL = {
    ContentType.INFOGRAPHIC,
    ContentType.SCREENSHOT,
    ContentType.FLOWCHART,
    ContentType.FLOWCHART_EDGE,
    ContentType.GRAPH,
}


class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: str
    document_id: str
    file_name: str
    page_no: int | None = Field(default=None, ge=1)
    page_range: tuple[int, int] | None = None
    content_type: ContentType
    chapter: str | None = None
    section: str | None = None
    subsection: str | None = None
    item: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    table_id: str | None = None
    figure_id: str | None = None
    extract_method: ExtractMethod
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BBox | None = None
    parent_chunk_id: str | None = None
    previous_chunk_id: str | None = None
    next_chunk_id: str | None = None
    related_chunk_ids: list[str] = Field(default_factory=list)
    source_location: SourceLocation
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistency(self):
        if self.page_no is None and not self.page_range:
            raise ValueError("page_no 또는 page_range 중 하나는 필수")
        if self.extract_method in (ExtractMethod.PDF_TEXT, ExtractMethod.LAYOUT_ANALYSIS):
            if self.bbox is None and self.source_location.char_range is None:
                raise ValueError("pdf_text/layout 청크는 bbox 또는 char_range 필수")
        if self.content_type in (ContentType.TABLE_ROW, ContentType.TABLE_NOTE) and not self.table_id:
            raise ValueError(f"{self.content_type.value}는 table_id 필수")
        if self.content_type in _VISUAL and not self.figure_id:
            raise ValueError(f"{self.content_type.value}는 figure_id 필수")
        return self


# ─────────────────────────── Content (타입별 변형) (§11.3) ───────────────────────────
class TextContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["text"] = "text"
    text: str


class ListItemContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["list-item"] = "list-item"
    marker: str | None = None
    text: str


class Col(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    value: str


class TableRowContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["table-row"] = "table-row"
    cols: list[Col]
    section_path: list[str] = Field(default_factory=list)
    embedding_text: str  # 표 Record 필수


class TableNoteContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["table-note"] = "table-note"
    text: str


class Branch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on: str
    target_step_id: str | None = None


class ProcedureStepContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["procedure-step"] = "procedure-step"
    step_no: int | None = None
    step_label: str | None = None
    actions: list[str] = Field(default_factory=list)
    detail: str | None = None
    branches: list[Branch] = Field(default_factory=list)
    ocr_text: str | None = None


class FlowchartNodeContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["flowchart"] = "flowchart"
    node_id: str
    node_type: str | None = None
    label: str
    semantics: str


class FlowchartEdgeContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["flowchart-edge"] = "flowchart-edge"
    from_node: str
    to_node: str
    condition: str | None = None
    relation: str


class GraphContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["graph"] = "graph"
    notation: str = "mermaid"
    mermaid: str
    summary: str


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verb: str
    target: str
    value: str | None = None
    state: str | None = None


class Emphasis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str
    meaning: str


class ScreenshotContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["screenshot"] = "screenshot"
    screen_name: str | None = None
    purpose: str
    actions: list[Action] = Field(default_factory=list)
    emphasis: list[Emphasis] = Field(default_factory=list)
    ocr_text: str | None = None


class DataPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    value: str


class InfographicContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["infographic"] = "infographic"
    info_kind: str | None = None
    summary: str
    reading: str | None = None
    data_points: list[DataPoint] = Field(default_factory=list)
    ocr_text: str | None = None


class WarningContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["warning"] = "warning"
    level: str | None = None
    text: str


class FootnoteContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["footnote"] = "footnote"
    ref_marker: str | None = None
    text: str


class ReferenceContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["reference"] = "reference"
    text: str
    target_hint: str | None = None


Content = Annotated[
    Union[
        TextContent, ListItemContent, TableRowContent, TableNoteContent,
        ProcedureStepContent, FlowchartNodeContent, FlowchartEdgeContent, GraphContent,
        ScreenshotContent, InfographicContent, WarningContent, FootnoteContent, ReferenceContent,
    ],
    Field(discriminator="kind"),
]


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meta: Meta
    content: Content

    @model_validator(mode="after")
    def _type_alignment(self):
        if self.content.kind != self.meta.content_type.value:
            raise ValueError(
                f"content_type({self.meta.content_type.value}) != content.kind({self.content.kind})"
            )
        return self
