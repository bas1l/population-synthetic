import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class LLMInteractionEntry:
    category: str
    method: str
    step: str
    prompt: str
    raw_response: str
    parsed_value: Any = None
    attempt: int = 1
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class LLMInteractionCollector:

    def __init__(self) -> None:
        self._entries: list[LLMInteractionEntry] = []

    def record(self, entry: LLMInteractionEntry) -> None:
        self._entries.append(entry)

    @property
    def entries(self) -> list[LLMInteractionEntry]:
        return self._entries

    def flush(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                [asdict(e) for e in self._entries],
                f,
                indent=2,
                ensure_ascii=False,
            )
