from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from slum.alerts.config import ChannelConfig
from slum.alerts import router


class FakeChannel:
    def __init__(self):
        self.send = AsyncMock()


class FakeClient:
    def __init__(self):
        self.channels = {}
        self.latency = 0.0

    def get_channel(self, channel_id):
        return self.channels.get(int(channel_id))

    async def fetch_channel(self, channel_id):
        return self.channels.get(int(channel_id))


class RouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._original_client = router.CLIENT
        original_config = router.get_channel_config()
        self._original_config = ChannelConfig(original_config.as_dict(), original_config.path)
        self.tempdir = tempfile.TemporaryDirectory()
        path = Path(self.tempdir.name) / "channels.yml"
        config = ChannelConfig(
            {
                "day_trade_alerts": 111,
                "swing_alerts": 222,
                "leaps_alerts": 333,
                "long_term_alerts": 444,
                "news_feed": 555,
                "ops_logs": None,
            },
            path,
        )
        self.client = FakeClient()
        router.configure(self.client, config)
        self.day_channel = FakeChannel()
        self.news_channel = FakeChannel()
        self.client.channels[111] = self.day_channel
        self.client.channels[555] = self.news_channel

    async def asyncTearDown(self) -> None:
        router.configure(self._original_client, self._original_config)
        self.tempdir.cleanup()

    async def test_day_alert_routes_to_day_channel(self) -> None:
        await router.route_alert({"type": "day", "content": "Alert"})
        self.day_channel.send.assert_awaited_once_with("Alert", embed=None)
        self.news_channel.send.assert_not_called()

    async def test_news_alert_routes_to_news_channel(self) -> None:
        await router.route_alert({"type": "news", "content": "News!"})
        self.news_channel.send.assert_awaited_once_with("News!", embed=None)
        self.day_channel.send.assert_not_called()

    async def test_invalid_alert_type_raises(self) -> None:
        with self.assertRaises(ValueError):
            await router.route_alert({"type": "unknown", "content": ""})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

