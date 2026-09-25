"""The syllabus: concept atlas, domain catalog, and playbook articles."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import yaml

from . import config


@dataclass(frozen=True)
class Concept:
    id: str
    name: str
    region: str
    tier: int
    summary: str
    prereqs: tuple[str, ...] = ()
    bug_patterns: tuple[str, ...] = ()
    feature_patterns: tuple[str, ...] = ()
    beacons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "region": self.region, "tier": self.tier,
            "summary": self.summary, "prereqs": list(self.prereqs),
            "bug_patterns": list(self.bug_patterns), "feature_patterns": list(self.feature_patterns),
            "beacons": list(self.beacons),
        }


@dataclass(frozen=True)
class Domain:
    id: str
    name: str
    sector: str
    flavor: str
    shapes: tuple[str, ...]
    affinities: tuple[str, ...]


@dataclass
class Curriculum:
    regions: list[dict[str, str]]
    concepts: dict[str, Concept]
    domains: dict[str, Domain]
    by_region: dict[str, list[Concept]] = field(default_factory=dict)

    def concept(self, cid: str) -> Concept:
        return self.concepts[cid]

    def region_name(self, rid: str) -> str:
        return next((r["name"] for r in self.regions if r["id"] == rid), rid)


def _tuple(v: Any) -> tuple[str, ...]:
    if not v:
        return ()
    return tuple(str(x) for x in v)


@lru_cache(maxsize=1)
def load() -> Curriculum:
    raw = yaml.safe_load((config.CONTENT_DIR / "concepts.yaml").read_text())
    concepts = {}
    for c in raw["concepts"]:
        concepts[c["id"]] = Concept(
            id=c["id"], name=c["name"], region=c["region"], tier=int(c.get("tier", 2)),
            summary=c.get("summary", ""), prereqs=_tuple(c.get("prereqs")),
            bug_patterns=_tuple(c.get("bug_patterns")), feature_patterns=_tuple(c.get("feature_patterns")),
            beacons=_tuple(c.get("beacons")),
        )
    draw = yaml.safe_load((config.CONTENT_DIR / "domains.yaml").read_text())
    domains = {
        d["id"]: Domain(
            id=d["id"], name=d["name"], sector=d.get("sector", ""), flavor=d.get("flavor", ""),
            shapes=_tuple(d.get("shapes")) or ("library",),
            affinities=tuple(a for a in _tuple(d.get("affinities")) if a in concepts),
        )
        for d in draw["domains"]
    }
    cur = Curriculum(regions=raw["regions"], concepts=concepts, domains=domains)
    for r in cur.regions:
        cur.by_region[r["id"]] = [c for c in concepts.values() if c.region == r["id"]]
    return cur


# --- playbook -------------------------------------------------------------------

_FRONT = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


@lru_cache(maxsize=1)
def playbook() -> list[dict[str, Any]]:
    articles = []
    for p in sorted((config.CONTENT_DIR / "playbook").glob("*.md")):
        text = p.read_text()
        m = _FRONT.match(text)
        meta, body = (yaml.safe_load(m.group(1)), m.group(2)) if m else ({}, text)
        articles.append({
            "slug": meta.get("slug", p.stem),
            "title": meta.get("title", p.stem),
            "summary": meta.get("summary", ""),
            "order": int(meta.get("order", 99)),
            "body": body.strip(),
        })
    return sorted(articles, key=lambda a: a["order"])
