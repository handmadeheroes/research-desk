from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

Text = Annotated[str, Field(max_length=2000)]
Label = Annotated[str, Field(min_length=1, max_length=200)]
Tags = Annotated[list[Annotated[str, Field(min_length=1, max_length=80)]], Field(max_length=40)]
NonNegative = Annotated[float, Field(ge=0, le=1e12)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Login(Model):
    password: str = Field(min_length=1, max_length=500)


class QuoteKey(Model):
    key: str = Field(min_length=12, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")


class DocumentInput(Model):
    title: Label
    content: str = Field(min_length=1, max_length=2000000)
    kind: Literal["article", "email", "transcript", "document", "chatgpt", "note"] = "note"
    source_name: Label = "Research note"
    url: str = Field(default="", max_length=3000)
    published_at: str | None = Field(default=None, max_length=100)
    tags: Tags = []
    tickers: Tags = []
    summary: str | None = Field(default=None, max_length=5000)
    ai_generated: bool = False
    external_id: str | None = Field(default=None, max_length=500)

    @field_validator("url")
    @classmethod
    def url_protocol(cls, value):
        if value and urlsplit(value).scheme not in ("http", "https"):
            raise ValueError("Source URL must use HTTP or HTTPS")
        return value


class DocumentPatch(Model):
    title: Label | None = None
    summary: str | None = Field(default=None, max_length=5000)
    tags: Tags | None = None
    tickers: Tags | None = None
    archived: bool | None = None


class Stock(Model):
    symbol: str = Field(pattern=r"^[A-Za-z0-9.^_-]{1,20}$")
    quote_symbol: str = Field(pattern=r"^[A-Za-z0-9.^_-]{1,30}$")
    exchange: str = Field(default="US", max_length=40)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    category: Literal["holding", "watchlist"] = "watchlist"
    shares: NonNegative = 0
    average_cost: NonNegative | None = None
    notes: Text = ""


class ManualPrice(Model):
    price: Annotated[float, Field(gt=0, le=1e9)]
    previous_price: Annotated[float, Field(gt=0, le=1e9)] | None = None
    as_of: str = Field(max_length=100)

    @field_validator("as_of")
    @classmethod
    def valid_time(cls, value):
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value


class Task(Model):
    title: Label
    due_at: str = Field(max_length=100)
    done: bool = False
    notes: Text = ""
    document_id: str | None = Field(default=None, max_length=80)

    @field_validator("due_at")
    @classmethod
    def valid_time(cls, value):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Task time must include a time zone")
        return parsed.isoformat()


class Source(Model):
    name: Label
    kind: Literal["rss", "web", "email", "manual"]
    url: str = Field(default="", max_length=3000)
    topics: Tags = []
    enabled: bool = True

    @field_validator("url")
    @classmethod
    def url_protocol(cls, value):
        if value and urlsplit(value).scheme not in ("http", "https"):
            raise ValueError("Use an HTTP or HTTPS source URL")
        return value


class ImportRequest(Model):
    upload_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    selected_ids: list[str] | None = Field(default=None, max_length=20000)
    include_files: bool = True


class UrlImport(Model):
    url: str = Field(min_length=8, max_length=3000)
    source_name: str = Field(default="", max_length=200)
    title: str = Field(default="", max_length=200)


class Digest(Model):
    day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    title: Label = "Morning brief"
    content: str = Field(min_length=1, max_length=2000000)
    document_ids: list[str] = Field(min_length=1, max_length=200)


class LayoutItem(Model):
    id: Literal["digest", "portfolio", "calendar", "library", "activity", "upload"]
    x: int = Field(ge=0, le=11)
    y: int = Field(ge=0, le=1000)
    w: int = Field(ge=2, le=12)
    h: int = Field(ge=2, le=30)


class Preferences(Model):
    timezone: str = Field(max_length=100)
    digest_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    profile: str = Field(max_length=30000)
    dot_url: str = Field(default="https://chatgpt.com/", max_length=1000)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (KeyError, ValueError) as exc:
            raise ValueError("Choose a valid IANA timezone, such as Asia/Kuala_Lumpur") from exc
        return value

    @field_validator("dot_url")
    @classmethod
    def valid_dot_url(cls, value):
        p = urlsplit(value)
        if p.scheme != "https" or p.hostname != "chatgpt.com" or p.username or p.password:
            raise ValueError("Copy your dot link from https://chatgpt.com")
        return value
