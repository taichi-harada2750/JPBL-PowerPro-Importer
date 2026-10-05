"""Validation for internal games and their exported GameJSON representation."""

from __future__ import annotations

from dataclasses import fields
from typing import Any

from app.models import BatterStats, InternalGame, PitcherStats, PlayerRecord
from data.namelist import NameList


BATTER_ADD_KEYS = (
    "試合", "打数", "得点", "安打", "二塁打", "三塁打", "本塁打", "打点", "三振", "四死球",
    "犠打", "盗塁", "併殺", "失策", "犠飛", "入力試合日", "備考",
)
PITCHER_ADD_KEYS = (
    "登板", "先発", "勝利", "敗戦", "H", "S", "投球回", "投球回分数", "球数", "打者",
    "被安打", "奪三振", "四死球", "失点", "自責点", "暴投", "被本塁打", "QS", "HQS",
    "完投", "完封", "無四球", "敬遠数", "入力試合日", "備考",
)


class ValidationError(ValueError):
    """One or more user-correctable validation failures."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def validate_internal_game(game: InternalGame, name_list: NameList) -> list[str]:
    errors: list[str] = []
    if not isinstance(game.game_id, str) or not game.game_id.strip():
        errors.append("gameIdは空にできません")
    if not isinstance(game.game_date, str) or not game.game_date.strip():
        errors.append("入力試合日は空にできません")
    if game.away_team not in name_list.teams:
        errors.append(f"先攻球団がNameListに存在しません: {game.away_team}")
    if game.home_team not in name_list.teams:
        errors.append(f"後攻球団がNameListに存在しません: {game.home_team}")

    for index, player in enumerate(game.players, start=1):
        errors.extend(_validate_player(index, player, name_list))
    return errors


def require_valid_internal_game(game: InternalGame, name_list: NameList) -> None:
    errors = validate_internal_game(game, name_list)
    if errors:
        raise ValidationError(errors)


def _validate_player(index: int, player: PlayerRecord, name_list: NameList) -> list[str]:
    prefix = f"players[{index}]"
    errors: list[str] = []
    name = player.name
    if player.team not in name_list.teams:
        errors.append(f"{prefix}: teamがNameListに存在しません: {player.team}")
    if player.position not in ("野手", "投手"):
        errors.append(f"{prefix}: positionは野手または投手である必要があります")
        return errors
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{prefix}: NameListから正式選手名を選択してください")
    elif (
        player.team in name_list.teams
        and not player.recognition.manually_added_name
        and not name_list.contains_player(player.team, player.position, name)
    ):
        errors.append(f"{prefix}: {name}は{player.team}の{player.position}候補に存在しません")

    expected_type = BatterStats if player.position == "野手" else PitcherStats
    if not isinstance(player.stats, expected_type):
        errors.append(f"{prefix}: positionとstatsの型が一致しません")
        return errors
    if not isinstance(player.remarks, str):
        errors.append(f"{prefix}: 備考は文字列である必要があります")
    for stat in fields(player.stats):
        value = getattr(player.stats, stat.name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"{prefix}: {stat.name}は0以上の整数である必要があります")
    if isinstance(player.stats, PitcherStats) and player.stats.inning_fraction not in (0, 1, 2):
        errors.append(f"{prefix}: 投球回分数は0、1、2のいずれかである必要があります")
    if isinstance(player.stats, PitcherStats):
        for field_name in ("appearances", "starts", "wins", "losses", "holds", "saves", "complete_games", "shutouts", "no_walk_games"):
            if getattr(player.stats, field_name) not in (0, 1):
                errors.append(f"{prefix}: {field_name}は0または1である必要があります")
    return errors


def validate_gamejson(
    document: Any,
    name_list: NameList,
    *,
    manually_added_players: set[tuple[str, str, str]] | None = None,
) -> list[str]:
    """Validate a completed external GameJSON v1 document."""

    errors: list[str] = []
    manually_added_players = manually_added_players or set()
    if not isinstance(document, dict):
        return ["GameJSONのルートはオブジェクトである必要があります"]
    if set(document) != {"gameId", "players"}:
        errors.append("GameJSONのルートキーはgameIdとplayersだけである必要があります")
    if not isinstance(document.get("gameId"), str) or not document.get("gameId", "").strip():
        errors.append("gameIdは空にできません")
    players = document.get("players")
    if not isinstance(players, list):
        return errors + ["playersは配列である必要があります"]

    for index, player in enumerate(players, start=1):
        prefix = f"players[{index}]"
        if not isinstance(player, dict):
            errors.append(f"{prefix}はオブジェクトである必要があります")
            continue
        if set(player) != {"name", "team", "position", "adds"}:
            errors.append(f"{prefix}にはname、team、position、addsだけを指定してください")
            continue
        name, team, position, adds = (player.get(key) for key in ("name", "team", "position", "adds"))
        if not isinstance(team, str) or team not in name_list.teams:
            errors.append(f"{prefix}: teamがNameListに存在しません")
        if position not in ("野手", "投手"):
            errors.append(f"{prefix}: positionは野手または投手である必要があります")
            continue
        manual_name = isinstance(name, str) and isinstance(team, str) and (team, position, name) in manually_added_players
        if not isinstance(name, str) or not isinstance(team, str) or (not manual_name and not name_list.contains_player(team, position, name)):
            errors.append(f"{prefix}: nameはteam内の正式{position}名である必要があります")
        expected_keys = BATTER_ADD_KEYS if position == "野手" else PITCHER_ADD_KEYS
        if not isinstance(adds, dict) or set(adds) != set(expected_keys):
            errors.append(f"{prefix}: addsのキーが{position}仕様と一致しません")
            continue
        for key in expected_keys:
            value = adds[key]
            if key == "入力試合日":
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{prefix}: 入力試合日は空でない文字列である必要があります")
            elif key == "備考":
                if not isinstance(value, str):
                    errors.append(f"{prefix}: 備考は文字列である必要があります")
            elif not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"{prefix}: {key}は0以上の整数である必要があります")
        if position == "投手" and adds["投球回分数"] not in (0, 1, 2):
            errors.append(f"{prefix}: 投球回分数は0、1、2のいずれかである必要があります")
    return errors
