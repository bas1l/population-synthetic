import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import IO, Any


@dataclass
class LLMInteractionEntry:
    category: str
    method: str
    step: str
    prompt: str
    raw_response: str
    parsed_value: Any = None
    error: str | None = None
    attempt: int = 1
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    # Correlation key for exact joining against the shared run log (parallel runs).
    # ``None`` for legacy entries and single-run callers that don't set it.
    persona_id: str | None = None
    call_index: int | None = None


class LLMInteractionCollector:
    """Collects LLM interaction entries and writes each one to disk immediately as JSONL."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._file: IO[str] | None = None
        self._count = 0

    def _ensure_open(self) -> None:
        if self._file is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(self._path, "w", encoding="utf-8")

    def record(self, entry: LLMInteractionEntry) -> None:
        self._ensure_open()
        self._file.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        self._file.flush()
        self._count += 1

    @property
    def count(self) -> int:
        return self._count

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def __del__(self) -> None:
        self.close()
