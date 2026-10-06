import tempfile
import unittest
from pathlib import Path

from app.settings import (
    load_last_namelist_path,
    load_next_game_id_serial,
    load_user_name,
    save_last_namelist_path,
    save_next_game_id_serial,
    save_user_name,
)


class SettingsTests(unittest.TestCase):
    def test_persists_and_restores_last_namelist_path_in_qsettings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_path = Path(temporary_directory) / "settings.json"
            name_list_path = Path(r"D:\名簿\JPBL_NameList.json")

            save_last_namelist_path(name_list_path, settings_path)

            self.assertEqual(load_last_namelist_path(settings_path), name_list_path)

    def test_missing_or_invalid_settings_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_path = Path(temporary_directory) / "settings.json"

            self.assertIsNone(load_last_namelist_path(settings_path))
            # A missing QSettings key is ignored; malformed values also fall
            # back to the default without stopping the application.
            self.assertIsNone(load_last_namelist_path(settings_path))

    def test_user_name_and_namelist_path_preserve_each_other(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_path = Path(temporary_directory) / "settings.json"
            name_list_path = Path(r"D:\名簿\JPBL_NameList.json")

            save_user_name("ABC", settings_path)
            save_last_namelist_path(name_list_path, settings_path)

            self.assertEqual(load_user_name(settings_path), "ABC")
            self.assertEqual(load_last_namelist_path(settings_path), name_list_path)

    def test_game_id_serial_is_persistent_per_prefix_and_never_regresses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_path = Path(temporary_directory) / "settings.json"
            prefix = "ABC-BT-20261005"

            self.assertEqual(load_next_game_id_serial(prefix, settings_path), 1)
            save_next_game_id_serial(prefix, 2, settings_path)
            save_next_game_id_serial(prefix, 1, settings_path)

            self.assertEqual(load_next_game_id_serial(prefix, settings_path), 2)
            self.assertEqual(load_next_game_id_serial("ABC-BT-20261006", settings_path), 1)
