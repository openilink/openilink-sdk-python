import unittest
import pysilk
from openilink import Client
from openilink.types import VoiceItem, CDNMedia


class TestUtils(unittest.TestCase):

    def test_silk_decoder(self):
        encrypt_query_param = "eklCZEdBMzAwTWhOWDdwSkJWdl96a3R6RUpVNV9vbWF5OTlzUmpuVlRWdkdtNWpXaVphQ0hpRS1tODFTMjg1RWlYaE5jRm5Fc3NnVHVyNFJDVFBxNmp0RGtHNWZ3U3JIY3JfZmFVVUc3ZTJVZzJRc1ZjLWJNRnF3V0FqY3R2bnZEdlhNTGp5dG9iR2ZPTmVnekpqWmhtbEJyZWIzVlpYalpOQnJpWVlKNl81Zy1JRmtPbHd5ZjRHVDhUd3dWU0FyYklkdEJsb1k1TUhXcEY4ZEk4LVRVWUE5R3YzT0FRNVQ3Z0JHb3RyeEZueWJDdjRfcEpwT2lQSGhHWnlRdWJQeDh5VFgycUlBWnRQRUtGUTlYWmg4dXVLMWJydnpCMjljcE5hS1JVSUdCQWxjN1Z5U2FRUGZmdWh5dWhycVB2YS01U0pFY2tmamZJb0lyYTVfQXo5enBSMHZEVHBVZVBkMDlPRXA1SWxDdFNKNElYZUZtMXM0MHNkNmhncWd5dEx0dml2dmxpZXE4VUNDNWZKajVVY0tZSjZzcW9zaFJVaWNkWlNLdVRXQ0tMY2laM0N0ZFBUZHQwbUtyUnNzNHdycVhLdFM3NGU3VTVtcDV3M3JTdUpVNDZwX0pFaDdyaHcwb2IzTHZUQW9QNU5iTlBFQ2htd19mUWVRVTBwQmZKNWJJYTBUWTNvPQ=="
        aes_key = "ZTk1NDllYzVmNDIxZmY4Y2EzMzE5ZmIwZTE1MDI0NDc="
        voice_item = VoiceItem(
            media=CDNMedia(
                encrypt_query_param=encrypt_query_param,
                aes_key=aes_key,
                encrypt_type=0
            ),
            encode_type=4,
            bits_per_sample=16,
            sample_rate=16000,
            playtime=2902,
            text="都是都基本上"
        )
        client = Client(
            silk_decoder=pysilk.decode
        )
        client.download_voice(voice_item)