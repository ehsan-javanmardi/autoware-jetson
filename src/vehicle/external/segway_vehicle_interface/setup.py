from glob import glob
import os

from setuptools import find_packages, setup

package_name = "segway_vehicle_interface"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.xml")),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Ehsan Javanmardi",
    maintainer_email="ehsan.jmardi@gmail.com",
    description="Autoware vehicle interface for the Segway RMP Plus 401.",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "segway_vehicle_interface = segway_vehicle_interface.node:main",
        ],
    },
)
