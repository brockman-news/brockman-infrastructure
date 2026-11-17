{
  lib,
  pkgs,
  ...
}:
let
  repo = "brockman-news/brockman-infrastructure";
  # master's head as seen by the check; the upgrade is pinned to it
  revFile = "/run/nixos-upgrade/rev";
  # last master commit an upgrade was started for
  triedFile = "/var/lib/nixos-upgrade/rev";

  newCommit = pkgs.writeShellApplication {
    name = "autoupgrade-new-commit";
    runtimeInputs = [
      pkgs.gitMinimal
      pkgs.coreutils
    ];
    text = ''
      rev=$(git ls-remote https://github.com/${repo} refs/heads/master | cut -f1)
      if [ -z "$rev" ]; then
        echo "autoupgrade: git ls-remote failed"
        exit 1
      fi
      if [ "$rev" = "$(cat ${triedFile} 2>/dev/null)" ]; then
        exit 1
      fi
      echo "$rev" >${revFile}
    '';
  };
in
{
  system.autoUpgrade = {
    enable = true;
    # expanded by the nixos-upgrade script, which uses it unquoted
    flake = "github:${repo}/$(cat ${revFile})";
    flags = [ "--print-build-logs" ];
    dates = "*:0/5";
    randomizedDelaySec = "0";
  };

  systemd.services.nixos-upgrade.serviceConfig = {
    RuntimeDirectory = "nixos-upgrade";
    StateDirectory = "nixos-upgrade";
    ExecCondition = lib.getExe newCommit;
    ExecStartPre = "${pkgs.coreutils}/bin/cp ${revFile} ${triedFile}";
  };
}
