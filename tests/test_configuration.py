import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(name, app):
    spec = importlib.util.spec_from_file_location(name, ROOT / app / 'bootstrap.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CPA = load('cpa_bootstrap', 'cliproxyapi')
KEEPER = load('keeper_bootstrap', 'cpa-usage-keeper')


class ConfigurationTests(unittest.TestCase):
    def test_cpa_preserves_providers_but_enforces_auth_and_listener(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data / 'options.json').write_text(json.dumps({'api_keys': ['c' * 32], 'management_key': 'm' * 32}))
            (data / 'config.yaml').write_text(yaml.safe_dump({'api-keys': {'codex': [{'name': 'saved'}]}, 'server': {'port': 9999}, 'access': {'api-keys': []}}))
            config = yaml.safe_load(CPA.configure(data, data / 'absent.yaml').read_text())
            self.assertEqual(config['api-keys']['codex'][0]['name'], 'saved')
            self.assertEqual(config['server']['port'], 8317)
            self.assertEqual(config['access']['api-keys'], ['c' * 32])
            self.assertTrue(config['observability']['usage']['usage-statistics-enabled'])
            self.assertEqual(config['oauth']['auth-dir'], str(data / 'auth'))

    def test_cpa_refuses_missing_or_shared_credentials(self):
        for options in ({}, {'api_keys': ['c' * 32], 'management_key': 'c' * 32}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                data = Path(directory)
                (data / 'options.json').write_text(json.dumps(options))
                with self.assertRaises(ValueError):
                    CPA.configure(data, data / 'absent.yaml')

    def test_management_ui_seeds_once_then_preserves_additions_and_revocations(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            options = {'api_key_source': 'management_ui', 'api_keys': ['c' * 32], 'management_key': 'm' * 32}
            (data / 'options.json').write_text(json.dumps(options))
            target = CPA.configure(data, data / 'absent.yaml')
            config = yaml.safe_load(target.read_text())
            self.assertEqual(config['access']['api-keys'], ['c' * 32])
            config['access']['api-keys'] = ['n' * 32]
            config['access']['other-setting'] = True
            target.write_text(yaml.safe_dump(config))
            # Revoking the original key in the UI must not reintroduce it from HA.
            config = yaml.safe_load(CPA.configure(data, data / 'absent.yaml').read_text())
            self.assertEqual(config['access']['api-keys'], ['n' * 32])
            self.assertTrue(config['access']['other-setting'])
            options['api_keys'] = []
            (data / 'options.json').write_text(json.dumps(options))
            self.assertEqual(yaml.safe_load(CPA.configure(data, data / 'absent.yaml').read_text())['access']['api-keys'], ['n' * 32])

    def test_management_ui_rejects_invalid_saved_keys_without_restoring_ha_keys(self):
        for keys in ([], None, 'c' * 32, ['short'], [7], ['m' * 32]):
            with self.subTest(keys=keys), tempfile.TemporaryDirectory() as directory:
                data = Path(directory)
                (data / 'options.json').write_text(json.dumps({'api_key_source': 'management_ui', 'api_keys': ['c' * 32], 'management_key': 'm' * 32}))
                target = data / 'config.yaml'
                target.write_text(yaml.safe_dump({'access': {'api-keys': keys}}))
                before = target.read_bytes()
                with self.assertRaises(ValueError):
                    CPA.configure(data, data / 'absent.yaml')
                self.assertEqual(target.read_bytes(), before)

    def test_home_assistant_mode_recovers_saved_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data / 'options.json').write_text(json.dumps({'api_key_source': 'home_assistant', 'api_keys': ['c' * 32], 'management_key': 'm' * 32}))
            (data / 'config.yaml').write_text(yaml.safe_dump({'access': {'api-keys': []}}))
            self.assertEqual(yaml.safe_load(CPA.configure(data, data / 'absent.yaml').read_text())['access']['api-keys'], ['c' * 32])

    def test_cpa_rejects_unknown_source_and_malformed_access(self):
        for source, access in (('unknown', {}), ('management_ui', [])):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as directory:
                data = Path(directory)
                (data / 'options.json').write_text(json.dumps({'api_key_source': source, 'api_keys': ['c' * 32], 'management_key': 'm' * 32}))
                (data / 'config.yaml').write_text(yaml.safe_dump({'access': access}))
                with self.assertRaises(ValueError):
                    CPA.configure(data, data / 'absent.yaml')

    def test_provider_file_cannot_override_security(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data / 'options.json').write_text(json.dumps({'api_keys': ['c' * 32], 'management_key': 'm' * 32}))
            providers = data / 'providers.yaml'
            providers.write_text('management: {secret-key: bypass}')
            with self.assertRaises(ValueError):
                CPA.configure(data, providers)

    def test_keeper_refuses_invalid_urls_and_missing_password(self):
        for url in ('', 'file:///tmp/config', 'http://cpa:8317/v1', 'http://cpa:8317?x=1', 'http://user:password@cpa:8317'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                KEEPER.environment({'cpa_base_url': url, 'management_key': 'm' * 32, 'login_password': 'p' * 32})
        with self.assertRaises(ValueError):
            KEEPER.environment({'cpa_base_url': 'http://cpa:8317', 'management_key': 'm' * 32})

    def test_keeper_enforces_auth_and_persistent_storage(self):
        env = KEEPER.environment({'cpa_base_url': 'http://cpa:8317/', 'management_key': 'm' * 32, 'login_password': 'p' * 32})
        self.assertEqual(env['CPA_BASE_URL'], 'http://cpa:8317')
        self.assertEqual(env['AUTH_ENABLED'], 'true')
        self.assertEqual(env['WORK_DIR'], '/data')
        self.assertEqual(env['TLS_SKIP_VERIFY'], 'false')

    def test_manifests_have_matching_options_and_schema(self):
        for app in ('cliproxyapi', 'cpa-usage-keeper'):
            config = yaml.safe_load((ROOT / app / 'config.yaml').read_text())
            self.assertEqual(set(config['options']), set(config['schema']))
            self.assertEqual(set(config['arch']), {'aarch64', 'amd64'})
            self.assertEqual(config['backup'], 'cold')
            self.assertFalse(config.get('host_network', False))
            self.assertNotIn('privileged', config)
            self.assertNotIn('hassio_api', config)


if __name__ == '__main__':
    unittest.main()
