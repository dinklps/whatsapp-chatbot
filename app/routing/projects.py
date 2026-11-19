"""Project -> person-in-charge routing table, loaded from config/projects.json."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel


def wa_link(number: str) -> str:
    digits = re.sub(r"\D", "", number)
    return f"https://wa.me/{digits}"


class Staff(BaseModel):
    name: str
    whatsapp: str
    email: str = ""
    office: str = ""

    @property
    def wa_link(self) -> str:
        return wa_link(self.whatsapp)


class Project(BaseModel):
    key: str
    name: str
    aliases: list[str] = []
    location: str = ""
    pic: str
    hod: str | None = None


class RoutingFile(BaseModel):
    staff: dict[str, Staff]
    default_pic: str
    default_hod: str
    projects: list[Project]


@dataclass
class Route:
    staff: Staff
    role: str  # "pic" | "hod" | "duty"
    pic: Staff  # the file's PIC, even when routed to the HOD


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


class RoutingTable:
    def __init__(self, data: RoutingFile):
        self.data = data
        self._by_key = {p.key: p for p in data.projects}
        self._by_name: dict[str, Project] = {}
        for p in data.projects:
            for label in [p.name, p.key, *p.aliases]:
                self._by_name[_norm(label)] = p
        for ref in [data.default_pic, data.default_hod]:
            if ref not in data.staff:
                raise ValueError(f"projects.json: unknown staff id '{ref}'")
        for p in data.projects:
            for ref in [p.pic, p.hod]:
                if ref is not None and ref not in data.staff:
                    raise ValueError(f"projects.json: project '{p.key}' refers to unknown staff id '{ref}'")

    @classmethod
    def load(cls, path: Path) -> "RoutingTable":
        return cls(RoutingFile.model_validate(json.loads(path.read_text(encoding="utf-8"))))

    @property
    def projects(self) -> list[Project]:
        return self.data.projects

    def get(self, key: str | None) -> Project | None:
        return self._by_key.get(key) if key else None

    def match(self, text: str | None) -> Project | None:
        """Exact (normalised) match on name, key or alias. Fuzzy matching is the model's job."""
        return self._by_name.get(_norm(text)) if text else None

    def route(self, project_key: str | None, reason_category: str | None) -> Route:
        project = self.get(project_key)
        staff = self.data.staff
        if project is None:
            duty = staff[self.data.default_pic]
            if reason_category == "complaint":
                return Route(staff=staff[self.data.default_hod], role="hod", pic=duty)
            return Route(staff=duty, role="duty", pic=duty)
        pic = staff[project.pic]
        if reason_category == "complaint":
            # A complaint may be about the PIC, so it goes to the head of department.
            return Route(staff=staff[project.hod or self.data.default_hod], role="hod", pic=pic)
        return Route(staff=pic, role="pic", pic=pic)
