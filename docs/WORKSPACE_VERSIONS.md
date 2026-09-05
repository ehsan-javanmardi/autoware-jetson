# Keeping a working version while developing another

The point of this: the version that runs on the vehicle should stay runnable while the next one is
half finished. Branch switching alone does not achieve that.

## Why switching branches in one directory does not work

`build/` and `install/` are git-ignored, so **they do not switch with the branch**. Checking out a
development branch swaps the sources under an `install/` that still belongs to the other version.
`colcon build --symlink-install`, which this workspace uses, makes it worse: much of `install/` is
symlinks into `src/`, so after a checkout those links point at files whose contents just changed.
The result is a workspace that looks built and behaves like neither version, and the only way back
is a full rebuild each time you switch.

## Use a second working copy instead

```bash
git branch stable                                   # bookmark today's verified state
git worktree add ../pix_autoware_dev -b dev         # second checkout, new branch
```

`git branch stable` creates a name pointing at the current commit and changes nothing else. It
exists so that state stays findable after `main` moves on.

`git worktree add` creates a second working directory with its own checkout, here on a new `dev`
branch, and leaves this directory on its own branch untouched. A worktree is not a clone: both
directories share one `.git`, so there is no second copy of the history and a commit made in either
is immediately visible to the other. Only the working files are duplicated.

| | `pix_autoware/` | `pix_autoware_dev/` |
| --- | --- | --- |
| branch | `main` | `dev` |
| source | the version that runs on the vehicle | starts identical, diverges |
| `build/`, `install/` | already built | **empty, needs its own full build** |
| `autoware_map/` | present | present, it is tracked |

Switch between them by changing directory and sourcing that copy's overlay:

```bash
cd ../pix_autoware_dev
source /opt/ros/humble/setup.bash
source install/setup.bash
```

## What to keep in mind

- **The new worktree needs a full first build**, around 40 minutes and 4.5 GB of `build/`. That
  directory can be deleted afterwards; `install/` is what is needed to run.
- **Never source both overlays in one shell.** Whichever is sourced last wins for some packages and
  not others, which produces a mixture that matches neither tree.
- **Only run one at a time**, or give them different `ROS_DOMAIN_ID` values. Two Autoware stacks on
  the same domain share a graph: duplicate node names, and topics fed by whichever instance
  publishes. This is the same failure as leaving nodes running from a previous launch, described in
  [`sensors/OUSTER_OS2_32.md`](sensors/OUSTER_OS2_32.md).
- **Remove a worktree with git, not `rm -rf`**, so its bookkeeping goes too:

  ```bash
  git worktree remove ../pix_autoware_dev
  git worktree list                                 # what exists right now
  ```

- **Getting a fix from one into the other** is an ordinary cherry-pick or merge, since both share
  the same repository:

  ```bash
  git -C ../pix_autoware_dev cherry-pick <commit-from-main>
  ```

## Returning to the known good state

`stable` is a branch like any other, so the vehicle copy can always be put back:

```bash
git checkout stable
colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release
```

Tagging instead of branching is worth considering once a version has actually driven:
`git tag -a v1-os2-verified -m "..."` records a point that cannot move, where a branch can.
