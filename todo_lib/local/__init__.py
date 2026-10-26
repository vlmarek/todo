"""Protected local APIs for CLI/init/sync/report workflows.

Writers acquire exclusive_lock(operation, root) before reading coordinated state
and retain it through publication. Offline readers use load_consistent_state.
Configuration loading checks all relevant paths before reading credentials.
T11 alone confirms wizard repair; T15 alone authorizes post-finalization pruning.
All storage is offline; current-cache deletion and cursor setting never prune.
"""
from .safety import (LocalError, check_paths, create_directory, atomic_write,
                     wizard_mode_repairs, repair_wizard_modes)
from .config import (ConfigError, ConfigState, Configuration, Credentials,
                     inspect_config, load_config, parse_config, write_config,
                     resolve_credentials, command_argv, SOLARIZED)
from .locking import LockBusy, exclusive_lock
from .history import (History, Coverage, empty_history, validate_history,
                      merge_history, prune_history)
from .store import (Binding, LocalState, Candidates, StateStore,
                    load_consistent_state, prepare_candidates,
                    validate_candidates, publish_snapshot, write_cursor)

__all__ = [name for name in globals() if not name.startswith('_')]
