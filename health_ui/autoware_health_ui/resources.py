"""Locating the frontend and config in both layouts this package runs from.

Run straight out of the tree (`./run.sh`, `autoware-health`) the data sits next
to the module, at health_ui/frontend and health_ui/config. Run as an installed
ROS package (`ros2 launch`) it sits in the package share directory instead.

`__file__` is resolved with realpath first, because this workspace builds with
--symlink-install: the installed module is a symlink back to the source tree, so
the source-relative path is still the right answer there and no ament lookup is
needed.
"""

import os

PACKAGE = "autoware_health_ui"


def resource_dir(name):
    """Absolute path to a data directory shipped with this package."""
    module_dir = os.path.dirname(os.path.realpath(__file__))
    local = os.path.join(os.path.dirname(module_dir), name)
    if os.path.isdir(local):
        return local
    try:
        from ament_index_python.packages import get_package_share_directory
        shared = os.path.join(get_package_share_directory(PACKAGE), name)
        if os.path.isdir(shared):
            return shared
    except Exception:
        pass
    return local


def default_config():
    return os.path.join(resource_dir("config"), "devices.yaml")


def frontend_dir():
    return resource_dir("frontend")
