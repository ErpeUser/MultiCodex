"""Form choices must respect published schema composition, not guessed values."""
import unittest
from multicodex.workspace_admin_api import AdminContract, AdminAPIError


def contract(field, *, body_wrapper=False, definitions=None):
    body = {'type': 'object', 'properties': {'role': field}}
    if body_wrapper:
        body = {'allOf': [body]}
    return AdminContract({'openapi': '3.0.2', 'info': {'version': 'test'},
        'servers': [{'url': 'https://api.chatgpt.com/v1'}],
        'components': {'schemas': definitions or {}},
        'paths': {'/manage/workspaces/{workspace_id}/users/{user_id}': {
            'patch': {'requestBody': {'content': {'application/json': {'schema': body}}},
                'responses': {'204': {'description': 'Updated'}}}}}})


class ContractChoiceTests(unittest.TestCase):
    def test_enum_inside_allof_reference_is_available_to_forms(self):
        c = contract({'allOf': [{'$ref': '#/components/schemas/Role'}]},
            definitions={'Role': {'type': 'string', 'enum': ['member', 'admin']}})
        self.assertEqual(c.choices('update_user', 'role'), ('member', 'admin'))

    def test_body_allof_preserves_published_field(self):
        c = contract({'type': 'string', 'enum': ['member']}, body_wrapper=True)
        self.assertEqual(c.choices('update_user', 'role'), ('member',))

    def test_intersecting_constraints_do_not_offer_rejected_role(self):
        c = contract({'allOf': [{'enum': ['member', 'admin']}, {'enum': ['member']}]})
        self.assertEqual(c.choices('update_user', 'role'), ('member',))

    def test_read_only_field_is_not_a_writable_choice(self):
        c = contract({'enum': ['owner'], 'readOnly': True})
        self.assertEqual(c.choices('update_user', 'role'), ())

    def test_invalid_enum_values_are_not_offered(self):
        c = contract({'type': 'string', 'enum': ['member', 'admin'], 'minLength': 6})
        self.assertEqual(c.choices('update_user', 'role'), ('member',))

    def test_duplicate_enum_values_do_not_duplicate_controls(self):
        c = contract({'enum': ['member', 'member']})
        self.assertEqual(c.choices('update_user', 'role'), ('member',))

    def test_unbounded_anyof_does_not_claim_a_complete_choice_set(self):
        c = contract({'anyOf': [{'enum': ['member']}, {'type': 'string'}]})
        self.assertEqual(c.choices('update_user', 'role'), ())

    def test_finite_anyof_offers_only_valid_string_choices(self):
        c = contract({'anyOf': [{'enum': ['member']}, {'enum': ['admin']}]})
        self.assertEqual(c.choices('update_user', 'role'), ('member', 'admin'))

    def test_oneof_overlap_is_removed_by_schema_validation(self):
        c = contract({'oneOf': [{'enum': ['member', 'admin']}, {'enum': ['admin']}]})
        self.assertEqual(c.choices('update_user', 'role'), ('member',))

    def test_missing_property_has_no_invented_choices(self):
        c = contract({'enum': ['member']})
        self.assertEqual(c.choices('update_user', 'seat_type'), ())

    def test_nonstring_enum_has_no_role_choices(self):
        c = contract({'enum': ['member', 1]})
        self.assertEqual(c.choices('update_user', 'role'), ())

    def test_malformed_union_returns_redacted_contract_error(self):
        for kind in ('allOf', 'oneOf', 'anyOf'):
            with self.subTest(kind=kind), self.assertRaises(AdminAPIError):
                contract({kind: 'not-a-list'}).choices('update_user', 'role')

    def test_large_schema_traversal_is_bounded(self):
        branch = {'anyOf': [{'enum': [str(i)]} for i in range(32)]}
        with self.assertRaises(AdminAPIError):
            contract({'anyOf': [branch for _ in range(32)]}).choices('update_user', 'role')


if __name__ == '__main__':
    unittest.main()
