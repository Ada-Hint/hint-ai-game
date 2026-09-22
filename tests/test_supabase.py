import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from hintgame import engine
from hintgame.storage import StorageError, SupabaseRepository


class SupabaseContractTests(unittest.TestCase):
    """Exercise the adapter's wire contract without external credentials."""

    def test_initialize_load_and_compare_swap_contract(self):
        remote = {}
        seen = []
        def respond(request, timeout):
            payload = json.loads(request.data)
            method = request.full_url.rsplit("/", 1)[-1]
            seen.append((method, payload, request.headers))
            if method == "hint_initialize":
                remote.setdefault(payload["p_id"], {"revision": 0, "document": payload["p_document"]})
                result = True
            elif method == "hint_read":
                result = remote[payload["p_id"]]
            else:
                event = remote[payload["p_id"]]
                result = event["revision"] == payload["p_revision"]
                if result:
                    event.update(revision=event["revision"] + 1, document=payload["p_document"])
            return io.BytesIO(json.dumps(result).encode())
        with patch("urllib.request.urlopen", side_effect=respond):
            repo = SupabaseRepository("https://example.supabase.co", "test-secret", "event")
            repo.mutate(lambda s: engine.join_player(s, "Cloud Player", "private-code"))
            revision, saved = repo.read()
            self.assertEqual(revision, 1)
            self.assertEqual(len(saved["players"]), 1)
            self.assertFalse(repo.compare_swap(0, saved))
            restarted = SupabaseRepository("https://example.supabase.co", "test-secret", "event")
            self.assertEqual(restarted.read(), (revision, saved))
        self.assertEqual(seen[0][0], "hint_initialize")
        self.assertEqual(seen[0][2]["Authorization"], "Bearer test-secret")

    def test_errors_never_expose_service_credentials(self):
        failure = HTTPError("https://example.supabase.co", 401, "test-secret must never appear", {}, None)
        with patch("urllib.request.urlopen", side_effect=failure):
            with self.assertRaises(StorageError) as caught:
                SupabaseRepository("https://example.supabase.co", "test-secret")
        self.assertNotIn("test-secret", str(caught.exception))

    def test_current_secret_keys_use_apikey_without_bearer(self):
        with patch("urllib.request.urlopen", return_value=io.BytesIO(b"true")) as request:
            SupabaseRepository("https://example.supabase.co", "sb_secret_test-only")
        headers = request.call_args.args[0].headers
        self.assertEqual(headers["Apikey"], "sb_secret_test-only")
        self.assertNotIn("Authorization", headers)


if __name__ == "__main__":
    unittest.main()
