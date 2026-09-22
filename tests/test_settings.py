import unittest
from unittest.mock import patch

from hintgame.settings import load_settings


class CloudSettingsTests(unittest.TestCase):
    def settings(self, values):
        return patch("hintgame.settings.setting", side_effect=lambda name, default="": values.get(name, default))

    def test_cloud_refuses_local_storage_without_creating_a_password(self):
        with patch.dict("os.environ", {"HINT_CLOUD_DEPLOYMENT": "1"}), self.settings({}), patch("hintgame.settings.local_password") as password:
            with self.assertRaisesRegex(ValueError, "persistent storage"):
                load_settings()
            password.assert_not_called()

    def test_cloud_needs_shareable_links_and_accepts_current_key(self):
        values = {"STORAGE_BACKEND": "supabase", "HOST_PASSWORD": "test-only-password", "EVENT_CODE": "TEST", "SUPABASE_SECRET_KEY": "sb_secret_test-only"}
        with patch.dict("os.environ", {"HINT_CLOUD_DEPLOYMENT": "1"}), self.settings(values):
            with self.assertRaisesRegex(ValueError, "PUBLIC_BASE_URL"):
                load_settings()
            values["PUBLIC_BASE_URL"] = "https://example.streamlit.app/"
            settings = load_settings()
            self.assertEqual(settings.public_url, "https://example.streamlit.app")
            self.assertEqual(settings.supabase_key, "sb_secret_test-only")
