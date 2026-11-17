# Brockman's Infrastructure
- to deploy, run `nix run --inputs-from . clan-core#clan-cli -- machines update brockman`
- every day at 00:00 UTC the `update` workflow runs `nix flake update`, builds the system and pushes the new `flake.lock` to `master` if the build succeeded
- the machine checks `master` every 5 minutes (`git ls-remote`) and switches to every new commit, so a merged PR is live within minutes; PRs need a green CI build before they can be merged
