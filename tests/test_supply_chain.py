"""Synthetic bundles exercise inventory/gate logic, never native acceptance."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools import supply_chain as sc


class SupplyChainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / 'bundle'
        self.bundle.mkdir()
        (self.bundle / 'LICENSE').write_text('MIT fixture license')
        self.write('_internal/demo-1.0.dist-info/METADATA',
                   'Name: demo\nVersion: 1.0\nLicense-Expression: MIT\n')
        self.write('_internal/demo-1.0.dist-info/licenses/LICENSE', 'MIT fixture')
        self.write('runtime/node_modules/sample/package.json', json.dumps(
            {'name': 'sample', 'version': '2.0', 'license': 'MIT'}))
        self.write('runtime/node_modules/sample/LICENSE', 'MIT fixture')
        self.write('runtime/node_modules/sample/index.js', 'export const fixture = true;')
        self.python_lock = self.root / 'python.lock'
        self.python_lock.write_text('demo==1.0 --hash=sha256:' + 'a' * 64)
        self.node_lock = self.root / 'package-lock.json'
        self.node_lock.write_text(json.dumps({'packages': {
            'node_modules/sample': {'version': '2.0', 'license': 'MIT',
                                    'resolved': 'https://registry.npmjs.org/sample/-/sample-2.0.tgz',
                                    'integrity': 'sha512-' + 'A' * 86 + '=='}}}))

    def write(self, path, content):
        target = self.bundle / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def inventory(self):
        return sc.inventory(self.bundle, self.python_lock, self.node_lock, 'a' * 40,
                            python_version='3.12.10', node_version='22.23.5',
                            node_archive_sha256='b' * 64)

    def test_inventory_records_shipped_versions_lock_integrity_and_every_file(self):
        bom, report = self.inventory()
        components = {c['bom-ref']: c for c in bom['components']}
        self.assertEqual(bom['bomFormat'], 'CycloneDX')
        self.assertEqual(components['pkg:pypi/demo@1.0']['version'], '1.0')
        self.assertEqual(components['pkg:npm/sample@2.0']['externalReferences'][0]['url'],
                         'https://registry.npmjs.org/sample/-/sample-2.0.tgz')
        file = components['file:runtime/node_modules/sample/index.js']
        self.assertEqual(file['hashes'][0]['content'], hashlib.sha256(
            b'export const fixture = true;').hexdigest())
        self.assertEqual(report['files'], 6)

    def test_python_metadata_disagreeing_with_lock_blocks_release(self):
        self.python_lock.write_text('demo==9.0 --hash=sha256:' + 'a' * 64)
        _, report = self.inventory()
        self.assertIn('PYTHON_LOCK_MISMATCH:demo', report['blockers'])
        self.assertFalse(report['ready'])

    def test_node_bundled_package_without_independent_integrity_inherits_parent_provenance(self):
        self.write('runtime/node_modules/sample/node_modules/vendor/package.json', json.dumps(
            {'name': 'vendor', 'version': '1.0', 'license': 'MIT'}))
        self.write('runtime/node_modules/sample/node_modules/vendor/LICENSE', 'MIT fixture')
        lock = json.loads(self.node_lock.read_text())
        lock['packages']['node_modules/sample/node_modules/vendor'] = {'version': '1.0', 'inBundle': True}
        self.node_lock.write_text(json.dumps(lock))
        bom, report = self.inventory()
        vendor = next(c for c in bom['components'] if c['bom-ref'] == 'pkg:npm/vendor@1.0')
        self.assertIn({'name': 'multicodex:integrity-inherited-from',
                       'value': 'node_modules/sample'}, vendor['properties'])
        self.assertNotIn('NODE_INTEGRITY_MISSING:vendor', report['blockers'])

    def test_unknown_license_and_native_attribution_block_publication(self):
        self.write('runtime/node_modules/sample/package.json', json.dumps(
            {'name': 'sample', 'version': '2.0', 'license': 'UNKNOWN'}))
        self.write('_internal/foreign.dll', 'synthetic binary')
        _, report = self.inventory()
        self.assertIn('LICENSE_REVIEW_REQUIRED:pkg:npm/sample@2.0', report['blockers'])
        self.assertIn('NATIVE_LICENSE_REVIEW_REQUIRED:_internal/foreign.dll', report['blockers'])

    def test_added_package_missing_from_lock_is_rejected(self):
        self.write('runtime/node_modules/extra/package.json', json.dumps(
            {'name': 'extra', 'version': '1.0', 'license': 'MIT'}))
        _, report = self.inventory()
        self.assertIn('NODE_LOCK_MISMATCH:extra', report['blockers'])

    def test_missing_locked_runtime_package_is_rejected(self):
        lock = json.loads(self.node_lock.read_text())
        lock['packages']['node_modules/missing'] = {'version': '1.0', 'license': 'MIT'}
        self.node_lock.write_text(json.dumps(lock))
        _, report = self.inventory()
        self.assertIn('NODE_PACKAGE_MISSING:node_modules/missing', report['blockers'])

    def test_vendored_source_copy_is_inventoried_with_parent_archive_provenance(self):
        self.write('runtime/node_modules/sample/vendor/internal/package.json', json.dumps(
            {'name': '@fixture/internal', 'version': '1.0', 'license': 'MIT'}))
        self.write('runtime/node_modules/sample/vendor/internal/LICENSE', 'MIT fixture')
        lock = json.loads(self.node_lock.read_text())
        lock['packages']['node_modules/sample/node_modules/@fixture/internal'] = {
            'version': '1.0', 'inBundle': True}
        self.node_lock.write_text(json.dumps(lock))
        bom, _ = self.inventory()
        component = next(c for c in bom['components'] if c.get('name') == '@fixture/internal')
        self.assertEqual(component['purl'], 'pkg:npm/%40fixture/internal@1.0')

    def test_missing_license_text_blocks_even_when_spdx_is_known(self):
        (self.bundle / 'runtime/node_modules/sample/LICENSE').unlink()
        _, report = self.inventory()
        self.assertIn('LICENSE_TEXT_MISSING:pkg:npm/sample@2.0', report['blockers'])

    def test_redirected_bundle_file_rejected_without_reading_target(self):
        target = self.root / 'outside'
        target.write_text('fixture outside bundle')
        try:
            (self.bundle / 'redirect').symlink_to(target)
        except OSError:
            self.skipTest('Host does not permit symlinks')
        with self.assertRaises(sc.InventoryError):
            self.inventory()


if __name__ == '__main__':
    unittest.main()
