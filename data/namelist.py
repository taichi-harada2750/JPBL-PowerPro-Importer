"""Versioned NameList loading and team-scoped player candidate access."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping


class NameListError(ValueError):
    """Raised when a NameList cannot safely be used."""


PlayerKind = Literal["batters", "pitchers"]


@dataclass(frozen=True, slots=True)
class TeamRoster:
    batters: tuple[str, ...]
    pitchers: tuple[str, ...]
    aliases_batters: Mapping[str, str]
    aliases_pitchers: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class NameList:
    schema_version: int
    generated_at: str | None
    source: str | None
    teams: dict[str, TeamRoster]

    SUPPORTED_SCHEMA_VERSIONS = (1, 2)

    @classmethod
    def from_file(cls, path: str | Path) -> "NameList":
        file_path = Path(path)
        try:
            with file_path.open("r", encoding="utf-8-sig") as stream:
                document = json.load(stream)
        except OSError as error:
            raise NameListError(f"NameListを読み込めません: {file_path}") from error
        except json.JSONDecodeError as error:
            raise NameListError(f"NameListが有効なJSONではありません: {error.msg}") from error
        return cls.from_dict(document)

    @classmethod
    def from_dict(cls, document: Any) -> "NameList":
        if not isinstance(document, dict):
            raise NameListError("NameListのルートはオブジェクトである必要があります")

        # Files produced before schemaVersion was introduced are interpreted as
        # v1, as are explicit schemaVersion: 1 files.
        schema_version = document.get("schemaVersion", 1)
        if (
            not isinstance(schema_version, int)
            or isinstance(schema_version, bool)
            or schema_version not in cls.SUPPORTED_SCHEMA_VERSIONS
        ):
            raise NameListError(
                f"未対応のNameList schemaVersionです: {schema_version!r} "
                f"(対応版: {', '.join(map(str, cls.SUPPORTED_SCHEMA_VERSIONS))})"
            )

        raw_teams = document.get("teams")
        if not isinstance(raw_teams, dict) or not raw_teams:
            raise NameListError("NameListには1球団以上のteamsが必要です")

        teams: dict[str, TeamRoster] = {}
        for team_name, raw_roster in raw_teams.items():
            if not isinstance(team_name, str) or not team_name.strip():
                raise NameListError("球団名は空でない文字列である必要があります")
            if not isinstance(raw_roster, dict):
                raise NameListError(f"{team_name}の名簿はオブジェクトである必要があります")
            batters = cls._read_names(team_name, "batters", raw_roster.get("batters"))
            pitchers = cls._read_names(team_name, "pitchers", raw_roster.get("pitchers"))
            aliases_batters: Mapping[str, str] = MappingProxyType({})
            aliases_pitchers: Mapping[str, str] = MappingProxyType({})
            if schema_version == 2:
                raw_aliases = raw_roster.get("aliases")
                if not isinstance(raw_aliases, dict):
                    raise NameListError(f"{team_name}.aliasesはオブジェクトである必要があります")
                aliases_batters = cls._read_aliases(team_name, "batters", raw_aliases.get("batters"), batters)
                aliases_pitchers = cls._read_aliases(team_name, "pitchers", raw_aliases.get("pitchers"), pitchers)
            teams[team_name] = TeamRoster(
                batters=batters,
                pitchers=pitchers,
                aliases_batters=aliases_batters,
                aliases_pitchers=aliases_pitchers,
            )

        return cls(
            schema_version=schema_version,
            generated_at=cls._optional_string(document, "generatedAt"),
            source=cls._optional_string(document, "source"),
            teams=teams,
        )

    @staticmethod
    def _optional_string(document: dict[str, Any], key: str) -> str | None:
        value = document.get(key)
        if value is not None and not isinstance(value, str):
            raise NameListError(f"{key}は文字列である必要があります")
        return value

    @staticmethod
    def _read_names(team_name: str, kind: PlayerKind, value: Any) -> tuple[str, ...]:
        if not isinstance(value, list):
            raise NameListError(f"{team_name}.{kind}は配列である必要があります")
        if any(not isinstance(name, str) or not name.strip() for name in value):
            raise NameListError(f"{team_name}.{kind}には空でない文字列の選手名だけを指定してください")
        if len(set(value)) != len(value):
            raise NameListError(f"{team_name}.{kind}に重複した選手名があります")
        return tuple(value)

    @staticmethod
    def _read_aliases(
        team_name: str,
        kind: PlayerKind,
        value: Any,
        official_names: tuple[str, ...],
    ) -> Mapping[str, str]:
        if not isinstance(value, dict):
            raise NameListError(f"{team_name}.aliases.{kind}はオブジェクトである必要があります")
        aliases: dict[str, str] = {}
        for alias, official_name in value.items():
            if not isinstance(alias, str) or not alias.strip():
                raise NameListError(f"{team_name}.aliases.{kind}のaliasは空でない文字列である必要があります")
            if not isinstance(official_name, str) or not official_name.strip():
                raise NameListError(
                    f"{team_name} / {kind}: Alias「{alias}」の変換先は空でない文字列である必要があります"
                )
            if official_name not in official_names:
                raise NameListError(
                    f"{team_name} / {kind}: Alias「{alias}」の変換先「{official_name}」は正式名一覧に存在しません"
                )
            aliases[alias] = official_name
        return MappingProxyType(aliases)

    def team_names(self) -> tuple[str, ...]:
        return tuple(self.teams.keys())

    def candidates(self, team: str, kind: PlayerKind) -> tuple[str, ...]:
        try:
            roster = self.teams[team]
        except KeyError as error:
            raise NameListError(f"NameListに球団が存在しません: {team}") from error
        if kind == "batters":
            return roster.batters
        if kind == "pitchers":
            return roster.pitchers
        raise NameListError(f"未対応の選手種別です: {kind}")

    def aliases(self, team: str, kind: PlayerKind) -> Mapping[str, str]:
        """Return aliases scoped to the selected team and player kind."""
        try:
            roster = self.teams[team]
        except KeyError as error:
            raise NameListError(f"NameListに球団が存在しません: {team}") from error
        if kind == "batters":
            return roster.aliases_batters
        if kind == "pitchers":
            return roster.aliases_pitchers
        raise NameListError(f"未対応の選手種別です: {kind}")

    def get_batters(self, team: str) -> tuple[str, ...]:
        """Return only official batter names for the selected team."""
        return self.candidates(team, "batters")

    def get_pitchers(self, team: str) -> tuple[str, ...]:
        """Return only official pitcher names for the selected team."""
        return self.candidates(team, "pitchers")

    def contains_player(self, team: str, position: str, name: str) -> bool:
        if position == "野手":
            return name in self.candidates(team, "batters")
        if position == "投手":
            return name in self.candidates(team, "pitchers")
        return False
