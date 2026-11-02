# Brockman's Infrastructure
- to deploy, run `nix run --inputs-from . clan-core#clan-cli -- machines update brockman`
- every day at 00:00 UTC the `update` workflow runs `nix flake update`, builds the system and pushes the new `flake.lock` to `master` if the build succeeded
- the machine auto-upgrades nightly (02:00 UTC) from `master` of this repo
