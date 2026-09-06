from glob import glob
import os
from setuptools import find_packages, setup

package_name = "autoware_web_control"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.xml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Ehsan Javanmardi",
    maintainer_email="ehsan.jmardi@gmail.com",
    description="Write paths for the web UI.",
    license="Apache-2.0",
    entry_points={"console_scripts": [
        "autoware_web_control = autoware_web_control.__main__:main",
    ]},
)
