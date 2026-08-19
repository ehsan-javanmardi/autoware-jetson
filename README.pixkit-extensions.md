# Pixkit Extensions for Autoware

This repository provides **additional packages and modifications** for running [Autoware](https://github.com/autowarefoundation/autoware) on the [Pixkit 2.0](https://www.pixmoving.com/pixkit) enquipped with a Velodyne VLP LiDAR (other type of lidar sensors will be supported later).  
It is designed to extend Autoware’s functionality and adapt it to Pixkit-based vehicle systems.

---

## 🚀 Overview

This repository contains:
- Custom drivers and launch files for Pixkit integration
- Modified configuration and interface nodes for Autoware
- Example setup for building a Pixkit-compatible Autoware workspace

---

## 🧩 Prerequisites

Before using this package, make sure you have:

- Ubuntu 22.04
- ROS 2 Humble
- Proper build tools (`colcon`, `vcstool`, etc.)
- Internet access for downloading dependencies

---

## 🧱 Installation Steps

### 1. Clone Autoware (release 0.45.1)

Follow the official Autoware installation guide:

```bash
git clone https://github.com/autowarefoundation/autoware.git
cd autoware
git checkout tags/0.45.1
```

Then follow the instructions as described in the [Autoware User Guide](https://autowarefoundation.github.io/autoware-documentation/main/installation/autoware/source-installation/).



After fetching the src files, go to step 2.
```bash
vcs import src < autoware.repos
```

---

### 2. Clone Pixkit extensions

Clone this repository into a separate folder:

Copy and **replace** the contents from this repository into your Autoware workspace:

```bash
cp -r your_path/Pixkit_Autoware/* your_path/autoware/
```

This will overwrite existing files as needed to enable Pixkit support.

---

### 4. Build Autoware

From the root of your Autoware workspace:

Follow the build instructions as described in the [Autoware User Guide](https://autowarefoundation.github.io/autoware-documentation/main/installation/autoware/source-installation/).

---

### 5. Run Autoware on Pixkit

After successful build, source the workspace:
```bash
source install/setup.bash
```

Modify your file path and map path in **autoware_velodyne_kashiwa.sh**

Then you can run & test Pixkit Autoware by running the .sh file.

---

## 🧠 Notes

- This repository **replaces some Autoware core packages** with Pixkit-specific modifications.  
  Make sure you are using the correct release version (`0.45.1`) before applying.
- If you wish to restore original Autoware files, simply reclone the Autoware repository and reimport its sources.

---

## 📄 License

This project follows the same license as the main [Autoware repository](https://github.com/autowarefoundation/autoware), unless otherwise stated.

---

## 🧑‍💻 Maintainer

**Pixkit Autoware Integration**  
Maintained by [tlab-wide](https://github.com/tlab-wide)  
For inquiries or issues, please open a GitHub issue in this repository.
