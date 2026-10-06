"""Export validated internal data to the minimal external GameJSON v1 format."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models import BatterStats, InternalGame, PitcherStats, PlayerRecord
from data.namelist import NameList
from data.validators import require_valid_internal_game, validate_gamejson


def calculate_qs_hqs(innings: int, inning_fraction: int, earned_runs: int) -> tuple[int, int]:
    """Return (QS, HQS) based on total outs, never a decimal innings value."""

    if not all(isinstance(value, int) and not isinstance(value, bool) for value in (innings, inning_fraction, earned_runs)):
        raise ValueError("投球回、投球回分数、自責点は整数である必要があります")
    if innings < 0 or earned_runs < 0 or inning_fraction not in (0, 1, 2):
        raise ValueError("投球回は0以上、投球回分数は0～2、自責点は0以上である必要があります")
    outs = innings * 3 + inning_fraction
    qs = int(outs >= 18 and earned_runs <= 3)
    hqs = int(outs >= 21 and earned_runs <= 2)
    return qs, hqs


class GameJsonExporter:
    """Single mapping point from internal models to GAS-compatible GameJSON."""

    def export(self, game: InternalGame, name_list: NameList) -> dict[str, Any]:
        require_valid_internal_game(game, name_list)
        document = {
            "gameId": game.game_id,
            "players": [self._export_player(player, game.game_date) for player in game.players],
        }
        manually_added_players = {
            (player.team, player.position, player.name)
            for player in game.players
            if player.recognition.manually_added_name and isinstance(player.name, str)
        }
        errors = validate_gamejson(document, name_list, manually_added_players=manually_added_players)
        if errors:  # Defensive: mapping bugs must never emit a malformed file.
            raise RuntimeError("Exporter generated invalid GameJSON: " + "; ".join(errors))
        return document

    def export_to_file(self, game: InternalGame, name_list: NameList, output_path: str | Path) -> None:
        document = self.export(game, name_list)
        with Path(output_path).open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")

    @staticmethod
    def _export_player(player: PlayerRecord, game_date: str) -> dict[str, Any]:
        return {
            "name": player.name,
            "team": player.team,
            "position": player.position,
            "adds": (
                GameJsonExporter._batter_adds(player.stats, game_date, player.remarks)
                if player.position == "野手"
                else GameJsonExporter._pitcher_adds(player.stats, game_date, player.remarks)
            ),
        }

    @staticmethod
    def _batter_adds(stats: BatterStats, game_date: str, remarks: str) -> dict[str, int | str]:
        return {
            "試合": 1,
            "打数": stats.at_bats,
            "得点": stats.runs,
            "安打": stats.hits,
            "二塁打": stats.doubles,
            "三塁打": stats.triples,
            "本塁打": stats.home_runs,
            "打点": stats.rbi,
            "三振": stats.strikeouts,
            "四死球": stats.walks_hbp,
            "犠打": stats.sacrifices,
            "盗塁": stats.steals,
            "併殺": stats.double_plays,
            "失策": stats.errors,
            "犠飛": stats.sac_flies,
            "入力試合日": game_date,
            "備考": remarks,
        }

    @staticmethod
    def _pitcher_adds(stats: PitcherStats, game_date: str, remarks: str) -> dict[str, int | str]:
        calculated_qs, calculated_hqs = calculate_qs_hqs(stats.innings, stats.inning_fraction, stats.earned_runs)
        qs = calculated_qs if stats.qs is None else stats.qs
        hqs = calculated_hqs if stats.hqs is None else stats.hqs
        return {
            "登板": 1,
            "先発": stats.starts,
            "勝利": stats.wins,
            "敗戦": stats.losses,
            "H": stats.holds,
            "S": stats.saves,
            "投球回": stats.innings,
            "投球回分数": stats.inning_fraction,
            "球数": stats.pitches,
            "打者": stats.batters_faced,
            "被安打": stats.hits_allowed,
            "奪三振": stats.strikeouts,
            "四死球": stats.walks_hbp,
            "失点": stats.runs,
            "自責点": stats.earned_runs,
            "暴投": stats.wild_pitches,
            "被本塁打": stats.home_runs_allowed,
            "QS": qs,
            "HQS": hqs,
            "完投": stats.complete_games,
            "完封": stats.shutouts,
            "無四球": stats.no_walk_games,
            "敬遠数": stats.intentional_walks,
            "入力試合日": game_date,
            "備考": remarks,
        }
