"""Test the packaging against Home Assistant Marketplace's installer."""

import json
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

from awesomeversion import AwesomeVersion
from homeassistant.components.marketplace.repositories.integration import (
    IntegrationRepository,
)
from homeassistant.const import __version__
from homeassistant.core import HomeAssistant

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path("custom_components/entity_proxy")
VERSION = "v" + json.loads((ROOT / PACKAGE / "manifest.json").read_text())["version"]


class TestMarketplace(unittest.IsolatedAsyncioTestCase):
    async def test_marketplace_extracts_and_validates_the_integration(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        hass = HomeAssistant(tmp.name)
        self.addAsyncCleanup(hass.async_stop)
        files = [ROOT / "hacs.json", *sorted((ROOT / PACKAGE).rglob("*"))]
        contents = {
            path.relative_to(ROOT).as_posix(): path.read_bytes()
            for path in files
            if path.is_file() and "__pycache__" not in path.parts
        }
        archive_data = BytesIO()
        with ZipFile(archive_data, "w", compression=ZIP_DEFLATED) as archive:
            for name, data in contents.items():
                archive.writestr(f"ha-entity-proxy-{VERSION}/{name}", data)

        async def download(url, **kwargs):
            url = str(url)
            for name in ("hacs.json", f"{PACKAGE}/manifest.json"):
                if url.endswith(f"/{name}"):
                    return contents[name]
            return archive_data.getvalue()

        marketplace = SimpleNamespace(
            core=SimpleNamespace(config_path=tmp.name),
            hass=hass,
            version=AwesomeVersion(__version__),
            async_download_file=download,
        )
        repo = IntegrationRepository(marketplace, "example/ha-entity-proxy")
        install = await repo._async_prepare_catalog_install(VERSION, commit=False)
        self.assertTrue(repo.try_resolve_content())
        self.assertEqual(repo.data.domain, "entity_proxy")
        self.assertTrue(repo.data.config_flow)
        await install()
        await repo.async_check_written_content()

        installed = Path(tmp.name)
        for name, data in contents.items():
            if name.startswith(f"{PACKAGE}/"):
                self.assertEqual((installed / name).read_bytes(), data)
        self.assertFalse((installed / "hacs.json").exists())
