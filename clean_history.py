#!/usr/bin/env python3
"""Rewrite git history to remove sensitive strings."""
import os
import subprocess
import tempfile

REPO = "/mnt/d/app/practice/pythonProject/yide"
REPLACEMENTS = {
    "wxabca86f6f8d49d0b": "YOUR_WECHAT_APPID",
    "e8f8c1fea7ac16f8dc33b8257269ea36": "YOUR_WECHAT_SECRET",
    "npg_PmG1s5UlhHqd": "YOUR_DB_PASSWORD",
}

os.chdir(REPO)

# Get all commits in reverse chronological order
result = subprocess.run(
    ["git", "log", "--all", "--reverse", "--format=%H %P", "--topo-order"],
    capture_output=True, text=True, check=True
)

commits = []
for line in result.stdout.strip().split("\n"):
    if not line.strip():
        continue
    parts = line.strip().split()
    sha = parts[0]
    parents = parts[1:] if len(parts) > 1 else []
    commits.append((sha, parents))

print(f"Found {len(commits)} commits to process")

# Process each commit
sha_map = {}
for sha, parents in commits:
    # Get the tree of this commit
    tree = subprocess.run(
        ["git", "rev-parse", f"{sha}^{{tree}}"],
        capture_output=True, text=True, check=True
    ).stdout.strip()

    # Checkout the commit to a temp index
    # Use git cat-file to get files, filter, recreate tree
    new_tree = tree

    # Check if settings.py or project.config.json exists in this commit
    files_to_check = []
    for f in ["yide/yide/settings.py", "yide_xcx/project.config.json"]:
        r = subprocess.run(
            ["git", "ls-tree", "-r", sha, f],
            capture_output=True, text=True
        )
        if r.stdout.strip():
            files_to_check.append(f)

    if files_to_check:
        with tempfile.TemporaryDirectory() as tmpdir:
            for f in files_to_check:
                subprocess.run(
                    ["git", "show", f"{sha}:{f}"],
                    capture_output=True, text=True, check=True
                )
                # Read content
                content_result = subprocess.run(
                    ["git", "show", f"{sha}:{f}"],
                    capture_output=True, text=True, check=True
                )
                content = content_result.stdout

                # Apply replacements
                for old, new in REPLACEMENTS.items():
                    content = content.replace(old, new)

                # Write to temp file
                os.makedirs(os.path.join(tmpdir, os.path.dirname(f)), exist_ok=True)
                with open(os.path.join(tmpdir, f), "w", newline="\n") as fh:
                    fh.write(content)

            # Update tree in git
            for f in files_to_check:
                os.chdir(tmpdir)
                subprocess.run(["git", "add", f], check=True)

            os.chdir(REPO)
            env = os.environ.copy()
            env["GIT_INDEX_FILE"] = os.path.join(tmpdir, ".git_index")
            subprocess.run(["git", "read-tree", tree], env=env, check=True)

            for f in files_to_check:
                subprocess.run(
                    ["git", "update-index", "--add", "--replace", os.path.join(tmpdir, f)],
                    env=env, check=True
                )

            new_tree = subprocess.run(
                ["git", "write-tree"],
                capture_output=True, text=True, check=True, env=env
            ).stdout.strip()

    # Map parent SHAs
    new_parents = [sha_map.get(p, p) for p in parents]

    # Create new commit
    commit_msg = subprocess.run(
        ["git", "log", "--format=%B", "-n", "1", sha],
        capture_output=True, text=True, check=True
    ).stdout.strip()

    env = os.environ.copy()
    for var in ["GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"]:
        val = subprocess.run(
            ["git", "log", "--format=%" + (var[4:].lower() if var.startswith("GIT_AUTHOR") else var[9:].lower()), "-n", "1", sha],
            capture_output=True, text=True, check=True
        ).stdout.strip()
        env[var] = val

    author_date = subprocess.run(
        ["git", "log", "--format=%aD", "-n", "1", sha],
        capture_output=True, text=True, check=True
    ).stdout.strip()

    committer_date = subprocess.run(
        ["git", "log", "--format=%cD", "-n", "1", sha],
        capture_output=True, text=True, check=True
    ).stdout.strip()

    args = ["git", "commit-tree", new_tree]
    for p in new_parents:
        args.extend(["-p", p])

    result = subprocess.run(
        args,
        input=commit_msg.encode(),
        capture_output=True, check=True, env=env
    )
    new_sha = result.stdout.decode().strip()
    sha_map[sha] = new_sha

    print(f"  {sha[:8]} -> {new_sha[:8]}", end="")
    if new_sha != sha:
        print(" (modified)")
    else:
        print(" (unchanged)")

print("\nDone processing commits")

# Update refs
branch_result = subprocess.run(
    ["git", "for-each-ref", "--format=%(refname)", "refs/heads"],
    capture_output=True, text=True, check=True
)
for ref in branch_result.stdout.strip().split("\n"):
    if not ref:
        continue
    branch_name = ref.replace("refs/heads/", "")
    # Find the tip commit
    tip = subprocess.run(
        ["git", "rev-parse", ref],
        capture_output=True, text=True, check=True
    ).stdout.strip()
    if tip in sha_map:
        subprocess.run(["git", "update-ref", ref, sha_map[tip]], check=True)
        print(f"Updated {branch_name} to {sha_map[tip][:8]}")

print("\nHistory rewrite complete!")
print("Run: git push origin --force --all")
