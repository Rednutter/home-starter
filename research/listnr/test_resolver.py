"""Offline contract tests for the isolated experiment, with synthetic media headers."""

import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import resolve_listnr as resolver


def response(station):
    return json.dumps({"data": {"station": station}}).encode(), {}, resolver.API, 200


STATION = {
    "id": "opaque-id",
    "slug": "example-station",
    "name": "Example Radio",
    "audioStreams": [{"url": "https://sa47.scastream.com.au/live/example/playlist.m3u8"}],
}


class ResolverTests(unittest.TestCase):
    def test_slug_and_canonical_identity(self):
        with patch.object(resolver, "fetch", return_value=response(STATION)) as fetch:
            result = resolver.resolve("example-station")
        self.assertEqual(result["identity"], "listnr:opaque-id")
        self.assertEqual(fetch.call_args.args[1]["variables"], {"slug": "example-station"})
        self.assertIsNone(result["expires_at"])

    def test_opaque_id_lookup_not_limited_to_uuid(self):
        data = {"data": {"stations": [STATION]}}
        with patch.object(resolver, "fetch", return_value=(json.dumps(data).encode(), {}, resolver.API, 200)) as fetch:
            result = resolver.resolve("listnr:opaque-id", True)
        self.assertEqual(result["slug"], "example-station")
        self.assertEqual(fetch.call_args.args[1]["variables"], {"ids": ["opaque-id"]})

    def test_missing_station(self):
        with patch.object(resolver, "fetch", return_value=response(None)):
            with self.assertRaisesRegex(resolver.ResolutionError, "station_not_found"):
                resolver.resolve("removed-station")

    def test_upstream_errors_never_print_response_details(self):
        raw = json.dumps({"errors": [{"message": "private upstream detail"}], "data": {"station": None}}).encode()
        with patch.object(resolver, "fetch", return_value=(raw, {}, resolver.API, 200)):
            with self.assertRaisesRegex(resolver.ResolutionError, "^catalogue_unavailable$"):
                resolver.resolve("example-station")

    def test_bad_json_and_schema(self):
        for body in [b"not JSON", b"[]", b'{"data":null}', b'{"data":{"station":{}}}']:
            with self.subTest(body=body), patch.object(resolver, "fetch", return_value=(body, {}, resolver.API, 200)):
                with self.assertRaisesRegex(resolver.ResolutionError, "catalogue_unavailable"):
                    resolver.resolve("example-station")

    def test_no_stream(self):
        with patch.object(resolver, "fetch", return_value=response({**STATION, "audioStreams": []})):
            with self.assertRaisesRegex(resolver.ResolutionError, "stream_resolution_failed"):
                resolver.resolve("example-station")

    def test_invalid_identity_does_not_request(self):
        with patch.object(resolver, "fetch") as fetch:
            with self.assertRaisesRegex(resolver.ResolutionError, "invalid_station_identity"):
                resolver.resolve('bad"slug')
            fetch.assert_not_called()

    def test_status_codes_do_not_overdiagnose_403_as_geo_or_expiry(self):
        for status, expected in [
            (401, "authentication_required"),
            (403, "access_denied"),
            (429, "rate_limited"),
            (451, "geo_restricted"),
            (503, "catalogue_unavailable"),
        ]:
            with self.subTest(status=status), patch.object(resolver, "build_opener") as opener:
                opener.return_value.open.side_effect = HTTPError(resolver.API, status, "upstream detail", {}, None)
                with self.assertRaisesRegex(resolver.ResolutionError, expected):
                    resolver.fetch(resolver.API)

    def test_master_relative_variant(self):
        text = '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=130000,CODECS="mp4a.40.2"\nchild.m3u8\n'
        variant = resolver.variants(text, "https://sa47.scastream.com.au/live/master.m3u8")[0]
        self.assertEqual(variant["url"], "https://sa47.scastream.com.au/live/child.m3u8")
        self.assertEqual(variant["attributes"]["BANDWIDTH"], "130000")

    def test_rejects_protected_playlist_even_with_a_later_none_key(self):
        text = b'#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="protected"\n#EXT-X-KEY:METHOD=NONE\n'
        with patch.object(resolver, "fetch", return_value=(text, {}, "https://sa47.scastream.com.au/test", 200)):
            with self.assertRaisesRegex(resolver.ResolutionError, "unsupported_protected_content"):
                resolver.playlist("https://sa47.scastream.com.au/test")

    def test_unreviewed_hosts_and_redirects_are_refused(self):
        for url in [
            "http://sa47.scastream.com.au/a",
            "https://example.com/a",
            "https://sa47.scastream.com.au.example.com/a",
        ]:
            with self.subTest(url=url):
                self.assertFalse(resolver.reviewed_media_url(url))
                with self.assertRaisesRegex(resolver.ResolutionError, "unreviewed_stream_host"):
                    resolver.MediaRedirects().redirect_request(None, None, 302, "", {}, url)
        with patch.object(resolver, "urlsplit") as split:
            split.return_value.scheme = "https"
            split.return_value.username = object()
            split.return_value.password = None
            split.return_value.hostname = "sa47.scastream.com.au"
            self.assertFalse(resolver.reviewed_media_url("https://sa47.scastream.com.au/a"))

    def test_audio_headers_require_two_consecutive_frames(self):
        frame = bytes([255, 241, 76, 128, 4, 31, 252]) + bytes(25)
        info = resolver.adts_audio_info(b"ID3-padding" + frame + frame)
        self.assertEqual(info["adts_core_sample_rate"], 48000)
        self.assertEqual(info["channels"], 2)
        with self.assertRaisesRegex(resolver.ResolutionError, "audio_validation_failed"):
            resolver.adts_audio_info(b"not audio" + frame)

    def test_live_validation_refreshes_same_variant_without_returning_session_url(self):
        master = "https://sa47.scastream.com.au/live/master.m3u8"
        child = "https://sa47.scastream.com.au/live/child.m3u8"
        master_text = '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=64000,CODECS="mp4a.40.5"\nchild.m3u8\n'
        old = "#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:5.0,\nold.aac\n"
        new = old.replace("old.aac", "new.aac")
        frame = bytes([255, 241, 76, 128, 4, 31, 252]) + bytes(25)
        with (
            patch.object(resolver, "playlist", side_effect=[(master_text, {}, master), (old, {}, child), (new, {}, child)]) as playlists,
            patch.object(resolver, "fetch", return_value=(frame + frame, {}, child, 200)),
            patch.object(resolver.time, "sleep"),
        ):
            result = resolver.validate({"stream_url": master})
        self.assertEqual(playlists.call_args.args, (child,))
        self.assertEqual(result["stream_url"], master)
        self.assertEqual(result["codec"], "mp4a.40.5")
        self.assertTrue(result["validation"]["live_playlist_advanced"])
        self.assertNotIn("child.m3u8", json.dumps(result))

    def test_static_or_stalled_playlist_does_not_pass_live_validation(self):
        url = "https://sa47.scastream.com.au/live/test.m3u8"
        media = "#EXTM3U\n#EXTINF:5.0,\na.aac\n"
        frame = bytes([255, 241, 76, 128, 4, 31, 252]) + bytes(25)
        with (
            patch.object(resolver, "playlist", return_value=(media, {}, url)),
            patch.object(resolver, "fetch", return_value=(frame + frame, {}, url, 200)),
            patch.object(resolver.time, "sleep"),
        ):
            with self.assertRaisesRegex(resolver.ResolutionError, "live_progress_not_observed"):
                resolver.validate({"stream_url": url})


if __name__ == "__main__":
    unittest.main()
