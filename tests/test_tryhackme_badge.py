import unittest
import xml.etree.ElementTree as ET
import io
import json
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.update_tryhackme_badge import API_URL, badge_asset_path, fetch_profile, render_badge, replace_badge_reference


PROFILE = {
    "username": "pinggu0x",
    "level": 9,
    "totalPoints": 10666,
    "completedRoomsNumber": 124,
    "badgesNumber": 15,
    "streak": 97,
    "rank": 105917,
    "topPercentage": 4,
    "leagueTier": "gold",
    "isPrivateProfile": False,
}


class TryHackMeBadgeTests(unittest.TestCase):
    @patch("scripts.update_tryhackme_badge.urlopen")
    def test_direct_fetch_does_not_use_reader(self, open_url):
        open_url.return_value = io.BytesIO(json.dumps({"status": "success", "data": PROFILE}).encode())
        self.assertEqual(fetch_profile(), PROFILE)
        self.assertEqual(open_url.call_count, 1)

    @patch("scripts.update_tryhackme_badge.time.time_ns", return_value=123)
    @patch("scripts.update_tryhackme_badge.urlopen")
    def test_challenge_uses_uncached_reader_for_same_public_url(self, open_url, _clock):
        target = f"{API_URL}&_=123"
        envelope = {"code": 200, "data": {"url": target, "httpStatus": 200,
                    "content": json.dumps({"status": "success", "data": PROFILE})}}
        open_url.side_effect = [HTTPError(target, 429, "challenge", {}, None),
                                io.BytesIO(json.dumps(envelope).encode())]
        self.assertEqual(fetch_profile(), PROFILE)
        reader = open_url.call_args.args[0]
        self.assertEqual(reader.full_url, f"https://r.jina.ai/{target}")
        self.assertEqual(reader.get_header("X-no-cache"), "true")
        self.assertEqual(reader.get_header("X-engine"), "browser")
        self.assertEqual(reader.get_header("X-wait-for-selector"), "pre")

    @patch("scripts.update_tryhackme_badge.urlopen")
    def test_reader_rejects_wrong_source_and_failed_upstream(self, open_url):
        for result in ({"url": "https://example.com", "httpStatus": 200, "content": "{}"},
                       {"url": f"{API_URL}&_=123", "httpStatus": 429, "content": "{}"}):
            with self.subTest(result=result), patch("scripts.update_tryhackme_badge.time.time_ns", return_value=123):
                open_url.side_effect = [HTTPError(API_URL, 429, "challenge", {}, None),
                                        io.BytesIO(json.dumps({"code": 200, "data": result}).encode())]
                with self.assertRaises(ValueError):
                    fetch_profile()

    @patch("scripts.update_tryhackme_badge.urlopen")
    def test_other_http_errors_do_not_trigger_reader(self, open_url):
        open_url.side_effect = HTTPError(API_URL, 503, "unavailable", {}, None)
        with self.assertRaises(HTTPError):
            fetch_profile()
        self.assertEqual(open_url.call_count, 1)

    def test_badge_filename_changes_with_svg_content(self):
        first = badge_asset_path("<svg>first</svg>")
        second = badge_asset_path("<svg>second</svg>")

        self.assertRegex(first, r"^assets/tryhackme-profile-[0-9a-f]{12}\.svg$")
        self.assertNotEqual(first, second)

    def test_readme_badge_reference_uses_new_content_path(self):
        readme = '<img src="assets/tryhackme-profile.svg" alt="TryHackMe">'

        updated, old_path = replace_badge_reference(readme, "assets/tryhackme-profile-abcdef123456.svg")

        self.assertEqual(old_path, "assets/tryhackme-profile.svg")
        self.assertIn('src="assets/tryhackme-profile-abcdef123456.svg"', updated)

    def test_renders_profile_metrics_as_valid_svg(self):
        svg = render_badge(PROFILE)
        root = ET.fromstring(svg)

        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        ns = "{http://www.w3.org/2000/svg}"
        headline = root.find(f".//{ns}text[@class='name']")
        level_card = root.find(f".//{ns}g[@transform='translate(28 133)']")
        self.assertEqual(headline.text, "pinggu0x")
        self.assertEqual(
            [node.text for node in level_card.findall(f"{ns}text")],
            ["LEVEL", "Mage", "0x9"],
        )

        for value in (
            "124",
            "10,666",
            "15",
            "97 DAYS",
            "TOP 4%",
            "RANK #105,917",
        ):
            self.assertIn(value, svg)

    def test_level_title_and_hex_code_follow_api_level(self):
        for level, title, code in ((10, "Wizard", "0xA"), (21, "Grandmaster", "0x15")):
            with self.subTest(level=level):
                root = ET.fromstring(render_badge(dict(PROFILE, level=level)))
                ns = "{http://www.w3.org/2000/svg}"
                level_card = root.find(f".//{ns}g[@transform='translate(28 133)']")

                self.assertEqual(
                    [node.text for node in level_card.findall(f"{ns}text")],
                    ["LEVEL", title, code],
                )

    def test_rejects_malformed_public_metrics(self):
        profile = dict(PROFILE, totalPoints="10666<script>")

        with self.assertRaises(ValueError):
            render_badge(profile)

    def test_unranked_profile_renders_without_rank(self):
        profile = dict(PROFILE, rank=None, topPercentage=None)

        svg = render_badge(profile)

        self.assertIn("UNRANKED", svg)


if __name__ == "__main__":
    unittest.main()
