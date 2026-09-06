import os
from glob import glob

from setuptools import setup

package_name = "segway_web_ui"


def data_tree(dest, source):
    """Install a directory, preserving its layout under share/<package>/."""
    out = []
    for root, _dirs, files in os.walk(source):
        if not files:
            continue
        rel = os.path.relpath(root, source)
        target = os.path.join("share", package_name, dest,
                              "" if rel == "." else rel)
        out.append((target, [os.path.join(root, f) for f in files]))
    return out


setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.xml")),
    ] + data_tree("frontend", "frontend") + data_tree("config", "config"),
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="ehsan-javanmardi",
    maintainer_email="ehsan.jmardi@gmail.com",
    description="Read-only web dashboard for Autoware diagnostics.",
    license="Apache License 2.0",
    entry_points={
        "console_scripts": [
            "segway_web_ui = segway_web_ui.__main__:main",
        ],
    },
)
