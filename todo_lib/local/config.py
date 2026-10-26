"""Complete INI validation and explicit, redacted credential resolution."""
import configparser
from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
import re
import shlex
from .safety import LocalError, check_paths, read_bytes, regular, atomic_write

SOLARIZED = dict(base01='#586e75', base1='#93a1a1', red='#dc322f',
                 green='#859900', yellow='#b58900', blue='#268bd2',
                 magenta='#d33682', cyan='#2aa198')


class ConfigError(LocalError):
    pass


class ConfigState(Enum):
    MISSING = 'missing'
    EMPTY = 'empty'
    POPULATED = 'populated'


def command_argv(value, field_name='pager'):
    """Parse direct argv only; no shell evaluation or executable lookup."""
    if not isinstance(value, str) or '\0' in value:
        raise ConfigError(f'{field_name}: invalid command')
    if not value.strip():
        return ()
    try:
        argv = tuple(shlex.split(value))
    except ValueError:
        raise ConfigError(f'{field_name}: malformed quoting') from None
    if not argv or not argv[0]:
        raise ConfigError(f'{field_name}: empty executable')
    return argv


@dataclass(frozen=True)
class Credentials:
    _token: str = field(repr=False)
    source: str

    def token(self):
        """Explicit transport-only access; never pass to subprocess argv."""
        return self._token

    def redact(self, value):
        text = str(value)
        text = re.sub(r'''(?i)(authorization["']?\s*[:=]\s*)[^\r\n]+''', r'\1[REDACTED]', text)
        return text.replace(self._token, '[REDACTED]') if self._token else text


@dataclass(frozen=True)
class Configuration:
    project: str
    default_sections: tuple[str, ...]
    hidden_from_now: tuple[str, ...]
    warn_limited_history: bool = True
    colors: dict = field(default_factory=lambda: dict(SOLARIZED))
    pager: tuple[str, ...] = ()
    _token: str = field(default='', repr=False, compare=False)

    def resolve_credentials(self, environ=None):
        """Resolve once per command; retain this result for all requests."""
        env = os.environ if environ is None else environ
        token = env.get('TODOIST_TOKEN', '')
        if token:
            return Credentials(token, 'environment')
        if self._token:
            return Credentials(self._token, 'configuration')
        raise ConfigError('missing personal token; configure todoist.token or TODOIST_TOKEN')


def resolve_credentials(config=None, environ=None, *, wizard_token=None):
    """Missing/empty-config wizard may supply hidden input, never an env copy."""
    env = os.environ if environ is None else environ
    if env.get('TODOIST_TOKEN', ''):
        return Credentials(env['TODOIST_TOKEN'], 'environment')
    if config is not None:
        return config.resolve_credentials(env)
    if wizard_token:
        return Credentials(wizard_token, 'wizard')
    raise ConfigError('missing personal token; run todo init')


def _names(value, name, *, empty=False):
    if empty and not value.strip():
        return ()
    names = tuple(part.strip() for part in value.split(','))
    if any(not part for part in names) or len({p.casefold() for p in names}) != len(names):
        raise ConfigError(f'main.{name}: empty or duplicate list element')
    return names


def parse_config(content):
    """Unknown keys/sections ignored; recognized errors never echo input."""
    parser = configparser.ConfigParser(interpolation=None)
    # DEFAULT inheritance is not part of the recognized schema.
    parser.default_section = '__unsupported_defaults__'
    try:
        text = content.decode('utf-8') if isinstance(content, bytes) else content
        parser.read_string(text)
        parser._defaults.clear()
    except (configparser.Error, UnicodeError, TypeError):
        raise ConfigError('config: malformed INI') from None
    for key in ('project', 'default_sections', 'hidden_from_now'):
        if not parser.has_option('main', key):
            raise ConfigError(f'config: missing required main.{key}')
    project = parser.get('main', 'project').strip()
    if not project or '\0' in project:
        raise ConfigError('main.project: nonempty name required')
    sections = _names(parser.get('main', 'default_sections'), 'default_sections')
    hidden = _names(parser.get('main', 'hidden_from_now'), 'hidden_from_now', empty=True)
    if any('\0' in n for n in sections + hidden):
        raise ConfigError('main: invalid name')
    warning = parser.get('report', 'warn_limited_history', fallback='true').strip().lower()
    if warning not in ('true', 'false'):
        raise ConfigError('report.warn_limited_history: expected true/false')
    colors = dict(SOLARIZED)
    for slot in colors:
        value = parser.get('colors', slot, fallback=colors[slot]).strip()
        if re.fullmatch(r'#[0-9a-fA-F]{6}', value) is None:
            raise ConfigError(f'colors.{slot}: expected #RRGGBB')
        colors[slot] = value
    return Configuration(project, sections, hidden, warning == 'true', colors,
                         command_argv(parser.get('main', 'pager', fallback='')),
                         parser.get('todoist', 'token', fallback='').strip())


def inspect_config(root=None):
    """Distinguish absent, exactly zero-byte, and populated config safely."""
    root = Path.home() / '.todo' if root is None else Path(root)
    check_paths(root, missing_directory=True)
    info = regular(root / 'config', missing=True)
    return ConfigState.MISSING if info is None else (ConfigState.EMPTY if info.st_size == 0 else ConfigState.POPULATED)


def load_config(root=None):
    root = Path.home() / '.todo' if root is None else Path(root)
    state = inspect_config(root)
    if state != ConfigState.POPULATED:
        raise ConfigError(f'config is {state.value}; run todo init')
    return parse_config(read_bytes(root / 'config'))


def write_config(root, content):
    """Publish a fully validated INI candidate; wizard controls confirmation."""
    check_paths(root)
    atomic_write(Path(root) / 'config', content, parse_config)
