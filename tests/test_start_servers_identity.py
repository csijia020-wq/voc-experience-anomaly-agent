import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import start_servers


class StartServerIdentityTest(unittest.TestCase):
    def test_expected_openapi_matches_project(self):
        openapi = {
            "info": {"title": start_servers.PROJECT_TITLE},
            "paths": {"/api/chat/stream": {"post": {}}},
        }
        self.assertTrue(start_servers._openapi_matches_project(openapi))

    def test_other_openapi_does_not_match_project(self):
        openapi = {
            "info": {"title": "CSV Data Cleaning Agent"},
            "paths": {"/health": {"get": {}}},
        }
        self.assertFalse(start_servers._openapi_matches_project(openapi))


if __name__ == "__main__":
    unittest.main()
