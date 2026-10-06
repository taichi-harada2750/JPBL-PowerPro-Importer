import unittest
import json
from tempfile import TemporaryDirectory
from pathlib import Path

from app.models import BatterStats, InternalGame, PitcherStats, PlayerRecord, RecognitionInfo
from data.gamejson_exporter import GameJsonExporter, calculate_qs_hqs
from data.namelist import NameList
from data.validators import ValidationError, validate_gamejson


def sample_name_list() -> NameList:
    return NameList.from_dict({
        "schemaVersion": 1,
        "teams": {
            "湘南": {"batters": ["京極遥人"], "pitchers": ["鈴鹿雄大"]},
            "北海道": {"batters": ["川村行典"], "pitchers": ["朴陶恒"]},
        },
    })


class ExporterTests(unittest.TestCase):
    def test_exports_exactly_specified_external_shape(self) -> None:
        game = InternalGame(
            game_id="2026-08-21-湘南-北海道-01",
            game_date="8/21",
            away_team="湘南",
            home_team="北海道",
            players=[
                PlayerRecord(
                    team="湘南",
                    position="野手",
                    recognition=RecognitionInfo(ocr_text="京極遥人", matched_name="京極遥人", confidence=99),
                    stats=BatterStats(at_bats=4, runs=1, hits=2, doubles=1, rbi=1),
                    remarks="雨天",
                ),
                PlayerRecord(
                    team="北海道",
                    position="投手",
                    recognition=RecognitionInfo(ocr_text="朴陶恒", matched_name="朴陶恒", confidence=98),
                    stats=PitcherStats(innings=7, inning_fraction=0, earned_runs=2, pitches=90, batters_faced=25),
                    remarks="救援陣",
                ),
            ],
        )

        document = GameJsonExporter().export(game, sample_name_list())

        self.assertEqual(set(document), {"gameId", "players"})
        self.assertEqual(document["players"][0]["adds"]["試合"], 1)
        self.assertEqual(document["players"][0]["adds"]["打数"], 4)
        self.assertEqual(document["players"][0]["adds"]["備考"], "雨天")
        self.assertNotIn("ocrText", document["players"][0])
        self.assertEqual(document["players"][1]["adds"]["登板"], 1)
        self.assertEqual(document["players"][1]["adds"]["QS"], 1)
        self.assertEqual(document["players"][1]["adds"]["HQS"], 1)
        self.assertEqual(document["players"][1]["adds"]["備考"], "救援陣")
        self.assertEqual(validate_gamejson(document, sample_name_list()), [])

    def test_refuses_name_not_in_the_team_position_roster(self) -> None:
        game = InternalGame(
            game_id="game-1", game_date="8/21", away_team="湘南", home_team="北海道",
            players=[PlayerRecord(
                team="湘南", position="野手",
                recognition=RecognitionInfo(matched_name="鈴鹿雄大"), stats=BatterStats(),
            )],
        )

        with self.assertRaises(ValidationError):
            GameJsonExporter().export(game, sample_name_list())

    def test_exports_a_manually_added_name_without_mutating_namelist(self) -> None:
        game = InternalGame(
            game_id="game-manual-name", game_date="8/21", away_team="湘南", home_team="湘南",
            players=[PlayerRecord(
                team="湘南", position="野手",
                recognition=RecognitionInfo(matched_name="新加入選手", manually_added_name=True),
                stats=BatterStats(at_bats=1),
            )],
        )

        document = GameJsonExporter().export(game, sample_name_list())

        self.assertEqual(document["players"][0]["name"], "新加入選手")
        self.assertNotIn("新加入選手", sample_name_list().get_batters("湘南"))

    def test_qs_and_hqs_use_outs(self) -> None:
        self.assertEqual(calculate_qs_hqs(5, 2, 0), (0, 0))
        self.assertEqual(calculate_qs_hqs(6, 0, 3), (1, 0))
        self.assertEqual(calculate_qs_hqs(7, 0, 2), (1, 1))
        self.assertEqual(calculate_qs_hqs(6, 2, 2), (1, 0))

    def test_exports_manually_reviewed_qs_and_hqs(self) -> None:
        game = InternalGame(
            game_id="game-reviewed-qs", game_date="8/21", away_team="湘南", home_team="北海道",
            players=[PlayerRecord(
                team="湘南", position="投手", recognition=RecognitionInfo(matched_name="鈴鹿雄大"),
                stats=PitcherStats(innings=7, earned_runs=2, qs=0, hqs=0),
            )],
        )

        adds = GameJsonExporter().export(game, sample_name_list())["players"][0]["adds"]

        self.assertEqual(adds["QS"], 0)
        self.assertEqual(adds["HQS"], 0)

    def test_rejects_invalid_inning_fraction(self) -> None:
        game = InternalGame(
            game_id="game-2", game_date="8/21", away_team="湘南", home_team="北海道",
            players=[PlayerRecord(
                team="湘南", position="投手",
                recognition=RecognitionInfo(matched_name="鈴鹿雄大"),
                stats=PitcherStats(inning_fraction=3),
            )],
        )
        with self.assertRaises(ValidationError):
            GameJsonExporter().export(game, sample_name_list())

    def test_writes_utf8_per_player_remarks(self) -> None:
        game = InternalGame(
            game_id="20261004-001", game_date="8/21", away_team="湘南", home_team="北海道",
            players=[
                PlayerRecord("湘南", "野手", RecognitionInfo(matched_name="京極遥人"), BatterStats(), "野手メモ"),
                PlayerRecord("北海道", "投手", RecognitionInfo(matched_name="朴陶恒"), PitcherStats(), "投手メモ"),
            ],
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "JPBL_Game_20261004-001.json"
            GameJsonExporter().export_to_file(game, sample_name_list(), path)
            text = path.read_text(encoding="utf-8")
            document = json.loads(text)

        self.assertIn("野手メモ", text)
        self.assertEqual([player["adds"]["備考"] for player in document["players"]], ["野手メモ", "投手メモ"])
