"""Conservative client for the *published* ChatGPT workspace OpenAPI contract.

Routes and writable fields are discovered, never probed or guessed. Old contracts
expose fewer capabilities. Supplying a contract is not a permission grant: the
server remains the authority. Credentials live only for the duration of a call.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from types import MappingProxyType
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_BASE = 'https://api.chatgpt.com/v1'
CONTRACT_URL = 'https://chatgpt.com/public/admin/api-reference/openapi.json'
MAX_BYTES = 4 * 1024 * 1024


class AdminAPIError(RuntimeError):
    """Redacted error; an uncertain write must be reconciled, not repeated."""
    CODES = frozenset({'INVALID_REQUEST', 'CONTRACT_INVALID', 'UNSUPPORTED_SCHEMA',
        'UNSUPPORTED_OPERATION', 'WRITES_DISABLED', 'RESPONSE_INVALID', 'AUTH_REQUIRED',
        'PERMISSION_DENIED', 'NOT_FOUND', 'CONFLICT', 'RATE_LIMITED', 'UNAVAILABLE',
        'REDIRECT', 'BOUND_EXCEEDED'})

    def __init__(self, code='INVALID_REQUEST', *, outcome_unknown=False, retry_after=None):
        self.code = code if code in self.CODES else 'UNAVAILABLE'
        self.outcome_unknown = outcome_unknown is True
        self.retry_after = retry_after
        super().__init__('Workspace administration: ' + self.code)


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', value):
        raise AdminAPIError()
    return value


def _json(value):
    try:
        return json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(',', ':')).encode('utf-8')
    except (TypeError, ValueError, RecursionError):
        raise AdminAPIError() from None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise AdminAPIError('REDIRECT')


def _decode(response, *, bound=MAX_BYTES):
    raw = response.read(bound + 1)
    if len(raw) > bound:
        raise AdminAPIError('BOUND_EXCEEDED')
    if not raw:
        return None
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise AdminAPIError('RESPONSE_INVALID') from None


def fetch_contract():
    """Read the fixed public JSON URL without sending any user credential."""
    try:
        request = Request(CONTRACT_URL, headers={'Accept': 'application/json'})
        with build_opener(_NoRedirect()).open(request, timeout=20) as response:
            if response.status != 200:
                raise AdminAPIError('CONTRACT_INVALID')
            return AdminContract(_decode(response))
    except AdminAPIError:
        raise
    except (HTTPError, URLError, OSError, ValueError):
        raise AdminAPIError('UNAVAILABLE') from None


def _transport(method, url, key, body, timeout):
    parts = urlsplit(url)
    if (parts.scheme != 'https' or parts.netloc != 'api.chatgpt.com' or
        not parts.path.startswith('/v1/manage/workspaces/') or parts.fragment):
        raise AdminAPIError()
    headers = {'Authorization': 'Bearer ' + key, 'Accept': 'application/json'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    data = None if body is None else _json(body)
    if data is not None and len(data) > MAX_BYTES:
        raise AdminAPIError('BOUND_EXCEEDED')
    request = Request(url, data=data, headers=headers, method=method)
    with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
        return response.status, None if response.status == 204 else _decode(response)


class AdminContract:
    """Restricted OpenAPI interpreter, scoped to members and invitations only.

    Unsupported validation keywords fail closed. This is intentionally not a
    general OpenAPI implementation and never resolves remote references.
    """
    _ANNOTATIONS = {'title', 'description', 'default', 'example', 'examples',
                    'deprecated', 'readOnly', 'writeOnly', 'xml', 'externalDocs', '$id', '$schema'}
    _KEYWORDS = {'$ref', 'type', 'nullable', 'enum', 'const', 'properties', 'required',
        'additionalProperties', 'items', 'minItems', 'maxItems', 'uniqueItems',
        'minLength', 'maxLength', 'pattern', 'format', 'minimum', 'maximum',
        'exclusiveMinimum', 'exclusiveMaximum', 'multipleOf', 'minProperties',
        'maxProperties', 'oneOf', 'anyOf', 'allOf'}
    _PREFIX = '/manage/workspaces/{workspace_id}/'

    def __init__(self, document):
        if not isinstance(document, dict) or len(_json(document)) > MAX_BYTES:
            raise AdminAPIError('CONTRACT_INVALID')
        self._doc = copy.deepcopy(document)
        self.fingerprint = hashlib.sha256(json.dumps(document, sort_keys=True, allow_nan=False,
            separators=(',', ':')).encode('utf-8')).hexdigest()
        if not str(document.get('openapi', '')).startswith(('3.0.', '3.1.')):
            raise AdminAPIError('CONTRACT_INVALID')
        if document.get('servers') != [{'url': API_BASE}]:
            # Descriptive server metadata is harmless, but alternative origins,
            # variables and relative servers are not accepted.
            servers = document.get('servers')
            if (not isinstance(servers, list) or len(servers) != 1 or
                not isinstance(servers[0], dict) or servers[0].get('url') != API_BASE or
                set(servers[0]) - {'url', 'description'}):
                raise AdminAPIError('CONTRACT_INVALID')
        paths = document.get('paths')
        if not isinstance(paths, dict) or len(paths) > 5000:
            raise AdminAPIError('CONTRACT_INVALID')
        found = {}
        for path, item in self._doc['paths'].items():
            if not isinstance(path, str) or not path.startswith(self._PREFIX):
                continue
            tail = path[len(self._PREFIX):]
            group = None
            if tail == 'users':
                group = {'get': 'list_users'}
            elif re.fullmatch(r'users/\{(?:user_id|id)\}', tail):
                group = {'get': 'get_user', 'patch': 'update_user', 'post': 'update_user', 'delete': 'remove_user'}
            elif tail in {'invites', 'invitations'}:
                group = {'get': 'list_invites', 'post': 'create_invite'}
            elif re.fullmatch(r'(?:invites|invitations)/\{(?:invite_id|invitation_id|id)\}', tail):
                group = {'get': 'get_invite', 'delete': 'cancel_invite'}
            elif re.fullmatch(r'(?:invites|invitations)/\{(?:invite_id|invitation_id|id)\}/resend', tail):
                group = {'post': 'resend_invite'}
            if group is None:
                continue
            if not isinstance(item, dict) or '$ref' in item or 'servers' in item:
                raise AdminAPIError('CONTRACT_INVALID')
            for method, name in group.items():
                if method not in item:
                    continue
                spec = item[method]
                if not isinstance(spec, dict) or 'servers' in spec or name in found:
                    raise AdminAPIError('CONTRACT_INVALID')
                if not isinstance(spec.get('responses'), dict):
                    raise AdminAPIError('CONTRACT_INVALID')
                found[name] = (method.upper(), path, spec, item.get('parameters', []))
        self._operations = found
        self.operations = MappingProxyType({key: value[0] for key, value in found.items()})
        self.version = str(document.get('info', {}).get('version', 'unknown'))[:100]

    def _resolve(self, schema, depth=0):
        if depth > 32 or not isinstance(schema, dict):
            raise AdminAPIError('UNSUPPORTED_SCHEMA')
        if '$ref' not in schema:
            return schema
        ref = schema['$ref']
        if not isinstance(ref, str) or not ref.startswith('#/components/') or set(schema) - {'$ref', 'description', 'summary'}:
            raise AdminAPIError('UNSUPPORTED_SCHEMA')
        node = self._doc
        try:
            for key in ref[2:].split('/'):
                node = node[key.replace('~1', '/').replace('~0', '~')]
        except (KeyError, TypeError):
            raise AdminAPIError('UNSUPPORTED_SCHEMA') from None
        return self._resolve(node, depth + 1)

    def _validate(self, value, schema, depth=0, *, direction='request'):
        if depth > 32:
            raise AdminAPIError('UNSUPPORTED_SCHEMA')
        schema = self._resolve(schema)
        if (direction == 'request' and schema.get('readOnly') is True or
            direction == 'response' and schema.get('writeOnly') is True):
            raise AdminAPIError()
        if any(k not in self._KEYWORDS | self._ANNOTATIONS and not k.startswith('x-') for k in schema):
            raise AdminAPIError('UNSUPPORTED_SCHEMA')
        if value is None and schema.get('nullable') is True:
            return
        for union, count in (('oneOf', 1), ('anyOf', None), ('allOf', 'all')):
            if union not in schema:
                continue
            variants = schema[union]
            if not isinstance(variants, list) or not 1 <= len(variants) <= 32:
                raise AdminAPIError('UNSUPPORTED_SCHEMA')
            good = 0
            for sub in variants:
                try:
                    self._validate(value, sub, depth + 1, direction=direction)
                    good += 1
                except AdminAPIError as exc:
                    if exc.code != 'INVALID_REQUEST':
                        raise
            if (count == 1 and good != 1) or (count is None and good == 0) or (count == 'all' and good != len(variants)):
                raise AdminAPIError()
        kinds = schema.get('type')
        if isinstance(kinds, str):
            kinds = [kinds]
        checks = {'object': type(value) is dict, 'array': type(value) is list,
            'string': type(value) is str, 'integer': type(value) is int,
            'number': type(value) in (int, float) and math.isfinite(value),
            'boolean': type(value) is bool, 'null': value is None}
        if kinds is not None:
            if not isinstance(kinds, list) or any(k not in checks for k in kinds):
                raise AdminAPIError('UNSUPPORTED_SCHEMA')
            if not any(checks[k] for k in kinds):
                raise AdminAPIError()
        if 'enum' in schema and not any(type(value) is type(x) and value == x for x in schema['enum']):
            raise AdminAPIError()
        if 'const' in schema and (type(value) is not type(schema['const']) or value != schema['const']):
            raise AdminAPIError()
        if type(value) is dict:
            props = schema.get('properties', {})
            required = schema.get('required', [])
            if not isinstance(props, dict) or not isinstance(required, list) or not all(isinstance(k, str) for k in required):
                raise AdminAPIError('UNSUPPORTED_SCHEMA')
            if any(k not in value for k in required):
                raise AdminAPIError()
            if len(value) < schema.get('minProperties', 0) or len(value) > schema.get('maxProperties', 1000):
                raise AdminAPIError()
            for key, item in value.items():
                if not isinstance(key, str):
                    raise AdminAPIError()
                if key in props:
                    self._validate(item, props[key], depth + 1, direction=direction)
                else:
                    additional = schema.get('additionalProperties', True)
                    if additional is False:
                        raise AdminAPIError()
                    if isinstance(additional, dict):
                        self._validate(item, additional, depth + 1, direction=direction)
        elif type(value) is list:
            if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', 10000):
                raise AdminAPIError()
            if schema.get('uniqueItems') and len({_json(x) for x in value}) != len(value):
                raise AdminAPIError()
            for item in value:
                self._validate(item, schema.get('items', {}), depth + 1, direction=direction)
        elif type(value) is str:
            if len(value) < schema.get('minLength', 0) or len(value) > schema.get('maxLength', 65536) or re.search(r'[\x00-\x1f\x7f]', value):
                raise AdminAPIError()
            if 'pattern' in schema:
                pattern = schema['pattern']
                if not isinstance(pattern, str) or len(pattern) > 256 or len(value) > 2048:
                    raise AdminAPIError('UNSUPPORTED_SCHEMA')
                # Exclude nested/extended constructs that can cause catastrophic
                # backtracking when processing a remote contract.
                if re.search(r'\([^)]*[+*{][^)]*\)[+*{]|\\[1-9]|\(\?', pattern):
                    raise AdminAPIError('UNSUPPORTED_SCHEMA')
                try:
                    if re.search(pattern, value) is None:
                        raise AdminAPIError()
                except re.error:
                    raise AdminAPIError('UNSUPPORTED_SCHEMA') from None
            form = schema.get('format')
            if form == 'email':
                if len(value) > 320 or re.fullmatch(r'[^\s@]+@[^\s@]+', value) is None:
                    raise AdminAPIError()
            elif form in ('date-time', 'date'):
                from datetime import datetime, date
                try:
                    (datetime.fromisoformat if form == 'date-time' else date.fromisoformat)(value.replace('Z', '+00:00'))
                except ValueError:
                    raise AdminAPIError() from None
            elif form not in (None, 'uuid'):
                raise AdminAPIError('UNSUPPORTED_SCHEMA')
            elif form == 'uuid':
                import uuid
                try:
                    uuid.UUID(value)
                except ValueError:
                    raise AdminAPIError() from None
        elif type(value) in (int, float):
            if not math.isfinite(value):
                raise AdminAPIError()
            if value < schema.get('minimum', -math.inf) or value > schema.get('maximum', math.inf):
                raise AdminAPIError()
            for name, bound, cmp in (('exclusiveMinimum', 'minimum', lambda a, b: a <= b),
                                      ('exclusiveMaximum', 'maximum', lambda a, b: a >= b)):
                v = schema.get(name, False)
                threshold = schema.get(bound) if v is True else v
                if v is not False and threshold is not None and cmp(value, threshold):
                    raise AdminAPIError()
            if 'multipleOf' in schema:
                from decimal import Decimal
                divisor = Decimal(str(schema['multipleOf']))
                if divisor <= 0 or Decimal(str(value)) % divisor != 0:
                    raise AdminAPIError()

    def body_schema(self, operation):
        try:
            spec = self._operations[operation][2]
        except KeyError:
            raise AdminAPIError('UNSUPPORTED_OPERATION') from None
        body = spec.get('requestBody')
        if body is None:
            return None
        body = self._resolve(body)
        schema = body.get('content', {}).get('application/json', {}).get('schema')
        if not isinstance(schema, dict):
            raise AdminAPIError('UNSUPPORTED_SCHEMA')
        return copy.deepcopy(self._resolve(schema))

    def choices(self, operation, field):
        schema = self.body_schema(operation) or {}
        prop = self._resolve(schema.get('properties', {}).get(field, {}))
        values = prop.get('enum', [])
        return tuple(values) if all(isinstance(v, str) for v in values) else ()

    def request(self, operation, workspace_id, *, target=None, body=None, query=None):
        if operation not in self._operations:
            raise AdminAPIError('UNSUPPORTED_OPERATION')
        method, path, spec, path_params = self._operations[operation]
        path = path.replace('{workspace_id}', _identifier(workspace_id))
        remaining = re.findall(r'\{([^}]+)\}', path)
        if remaining:
            path = path.replace('{' + remaining[0] + '}', _identifier(target))
        elif target is not None:
            raise AdminAPIError()
        if '{' in path or '}' in path:
            raise AdminAPIError('CONTRACT_INVALID')
        parameters = {}
        for item in list(path_params) + list(spec.get('parameters', [])):
            p = self._resolve(item)
            if p.get('in') == 'query':
                if p.get('style', 'form') != 'form' or 'content' in p:
                    raise AdminAPIError('UNSUPPORTED_SCHEMA')
                parameters[p['name']] = p
            elif p.get('in') == 'path':
                value = workspace_id if p.get('name') == 'workspace_id' else target
                self._validate(value, p.get('schema', {}))
            elif p.get('required'):
                raise AdminAPIError('UNSUPPORTED_SCHEMA')
        query = {} if query is None else query
        if not isinstance(query, dict) or set(query) - set(parameters):
            raise AdminAPIError()
        for name, p in parameters.items():
            if name in query:
                if isinstance(query[name], (list, dict)):
                    raise AdminAPIError('UNSUPPORTED_SCHEMA')
                self._validate(query[name], p.get('schema', {}))
            elif p.get('required'):
                raise AdminAPIError()
        body_schema = self.body_schema(operation)
        if body is not None:
            if body_schema is None or method == 'GET' or not isinstance(body, dict) or not body:
                raise AdminAPIError()
            self._validate(body, body_schema)
        elif body_schema is not None and self._resolve(spec['requestBody']).get('required'):
            raise AdminAPIError()
        if operation == 'update_user' and not body:
            raise AdminAPIError()
        query_string = urlencode({k: str(v).lower() if type(v) is bool else v for k, v in query.items()})
        return method, API_BASE + path + ('?' + query_string if query_string else ''), copy.deepcopy(body)

    def validate_response(self, operation, status, value):
        responses = self._operations[operation][2]['responses']
        response = responses.get(str(status))
        if response is None or type(status) is not int or not 200 <= status < 300:
            raise AdminAPIError('RESPONSE_INVALID')
        response = self._resolve(response)
        if status == 204:
            return None
        schema = response.get('content', {}).get('application/json', {}).get('schema')
        if not isinstance(schema, dict):
            raise AdminAPIError('RESPONSE_INVALID')
        try:
            self._validate(value, schema, direction='response')
        except AdminAPIError:
            raise AdminAPIError('RESPONSE_INVALID') from None
        return value


class AdminAPI:
    def __init__(self, contract, transport=_transport, *, timeout=15):
        if not isinstance(contract, AdminContract) or type(timeout) not in (int, float) or not 1 <= timeout <= 30:
            raise AdminAPIError()
        self.contract, self.transport, self.timeout = contract, transport, timeout

    def call(self, operation, workspace_id, key, *, target=None, body=None, query=None, allow_write=False):
        if not isinstance(key, str) or re.fullmatch(r'[\x21-\x7e]{1,2048}', key) is None:
            raise AdminAPIError()
        method, url, payload = self.contract.request(operation, workspace_id, target=target, body=body, query=query)
        write = method != 'GET'
        if write and allow_write is not True:
            raise AdminAPIError('WRITES_DISABLED')
        try:
            status, value = self.transport(method, url, key, payload, self.timeout)
            return self.contract.validate_response(operation, status, value)
        except HTTPError as exc:
            code = {401: 'AUTH_REQUIRED', 403: 'PERMISSION_DENIED', 404: 'NOT_FOUND',
                    409: 'CONFLICT', 429: 'RATE_LIMITED'}.get(exc.code, 'UNAVAILABLE')
            raw_retry = (exc.headers or {}).get('Retry-After', '')
            retry = min(3600, int(raw_retry)) if str(raw_retry).isdigit() else None
            raise AdminAPIError(code, outcome_unknown=write and exc.code >= 500, retry_after=retry) from None
        except AdminAPIError as exc:
            # A server may have performed a write before returning an invalid
            # success body or redirect. Never replay it without reconciliation.
            raise AdminAPIError(exc.code, outcome_unknown=write,
                                retry_after=exc.retry_after) from None
        except (URLError, OSError, ValueError, TypeError, RecursionError):
            raise AdminAPIError('UNAVAILABLE', outcome_unknown=write) from None
