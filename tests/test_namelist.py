import unittest

from data.namelist import NameList, NameListError
from ocr.matcher import match_player_name


class NameListTests(unittest.TestCase):
    def test_reads_team_and_position_scoped_candidates(self) -> None:
        name_list = NameList.from_dict({
            "schemaVersion": 1,
            "teams": {"湘南": {"batters": ["京極遥人"], "pitchers": ["鈴鹿雄大"]}},
        })

        self.assertEqual(name_list.team_names(), ("湘南",))
        self.assertEqual(name_list.candidates("湘南", "batters"), ("京極遥人",))
        self.assertTrue(name_list.contains_player("湘南", "投手", "鈴鹿雄大"))
        self.assertFalse(name_list.contains_player("湘南", "野手", "鈴鹿雄大"))

    def test_rejects_unknown_schema_version(self) -> None:
        with self.assertRaisesRegex(NameListError, "未対応"):
            NameList.from_dict({"schemaVersion": 3, "teams": {}})

    def test_rejects_missing_position_list(self) -> None:
        with self.assertRaisesRegex(NameListError, "pitchers"):
            NameList.from_dict({"schemaVersion": 1, "teams": {"湘南": {"batters": []}}})

    def test_v1_normalizes_to_empty_alias_maps(self) -> None:
        name_list = NameList.from_dict({
            "schemaVersion": 1,
            "teams": {"湘南": {"batters": ["天宮悠季"], "pitchers": ["天宮投手"]}},
        })

        self.assertEqual(dict(name_list.aliases("湘南", "batters")), {})
        self.assertEqual(dict(name_list.aliases("湘南", "pitchers")), {})

    def test_v2_reads_team_and_position_scoped_aliases(self) -> None:
        name_list = NameList.from_dict({
            "schemaVersion": 2,
            "teams": {
                "湘南": {
                    "batters": ["天宮悠季", "天宮凪澄"],
                    "pitchers": ["天宮投手"],
                    "aliases": {
                        "batters": {"天宮": "天宮悠季", "天宮凪": "天宮凪澄"},
                        "pitchers": {"天宮": "天宮投手"},
                    },
                },
                "東京": {
                    "batters": ["東京太郎"],
                    "pitchers": [],
                    "aliases": {"batters": {"天宮": "東京太郎"}, "pitchers": {}},
                },
            },
        })

        self.assertEqual(dict(name_list.aliases("湘南", "batters")), {"天宮": "天宮悠季", "天宮凪": "天宮凪澄"})
        self.assertEqual(dict(name_list.aliases("湘南", "pitchers")), {"天宮": "天宮投手"})
        self.assertEqual(dict(name_list.aliases("東京", "batters")), {"天宮": "東京太郎"})

        batter_match = match_player_name(
            "天宮", name_list.candidates("湘南", "batters"), name_list.aliases("湘南", "batters"),
        )
        pitcher_match = match_player_name(
            "天宮", name_list.candidates("湘南", "pitchers"), name_list.aliases("湘南", "pitchers"),
        )
        other_team_match = match_player_name(
            "天宮", name_list.candidates("東京", "batters"), name_list.aliases("東京", "batters"),
        )
        self.assertEqual(batter_match.matched_name, "天宮悠季")
        self.assertEqual(pitcher_match.matched_name, "天宮投手")
        self.assertEqual(other_team_match.matched_name, "東京太郎")

    def test_v2_allows_empty_alias_maps(self) -> None:
        name_list = NameList.from_dict({
            "schemaVersion": 2,
            "teams": {"湘南": {"batters": [], "pitchers": [], "aliases": {"batters": {}, "pitchers": {}}}},
        })

        self.assertEqual(dict(name_list.aliases("湘南", "batters")), {})

    def test_v2_rejects_alias_target_outside_its_own_roster(self) -> None:
        with self.assertRaisesRegex(NameListError, "湘南 / batters.*天宮.*存在しません"):
            NameList.from_dict({
                "schemaVersion": 2,
                "teams": {
                    "湘南": {
                        "batters": ["天宮悠季"],
                        "pitchers": ["天宮投手"],
                        "aliases": {"batters": {"天宮": "天宮投手"}, "pitchers": {}},
                    },
                },
            })

    def test_v2_requires_alias_objects(self) -> None:
        with self.assertRaisesRegex(NameListError, r"aliases\.pitchers"):
            NameList.from_dict({
                "schemaVersion": 2,
                "teams": {"湘南": {"batters": [], "pitchers": [], "aliases": {"batters": {}, "pitchers": []}}},
            })
