{ inputs, config, pkgs, lib, ... }: let
  sshKeys = {
    lassulus = ''ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDIb3uuMqE/xSJ7WL/XpJ6QOj4aSmh0Ga+GtmJl3CDvljGuIeGCKh7YAoqZAi051k5j6ZWowDrcWYHIOU+h0eZCesgCf+CvunlXeUz6XShVMjyZo87f2JPs2Hpb+u/ieLx4wGQvo/Zw89pOly/vqpaX9ZwyIR+U81IAVrHIhqmrTitp+2FwggtaY4FtD6WIyf1hPtrrDecX8iDhnHHuGhATr8etMLwdwQ2kIBx5BBgCoiuW7wXnLUBBVYeO3II957XP/yU82c+DjSVJtejODmRAM/3rk+B7pdF5ShRVVFyB6JJR+Qd1g8iSH+2QXLUy3NM2LN5u5p2oTjUOzoEPWZo7lykZzmIWd/5hjTW9YiHC+A8xsCxQqs87D9HK9hLA6udZ6CGkq4hG/6wFwNjSMnv30IcHZzx6IBihNGbrisrJhLxEiKWpMKYgeemhIirefXA6UxVfiwHg3gJ8BlEBsj0tl/HVARifR2y336YINEn8AsHGhwrPTBFOnBTmfA/VnP1NlWHzXCfVimP6YVvdoGCCnAwvFuJ+ZuxmZ3UzBb2TenZZOzwzV0sUzZk0D1CaSBFJUU3oZNOkDIM6z5lIZgzsyKwb38S8Vs3HYE+Dqpkfsl4yeU5ldc6DwrlVwuSIa4vVus4eWD3gDGFrx98yaqOx17pc4CC9KXk/2TjtJY5xmQ=='';
    kmein = ''ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDyTnGhFq0Q+vghNhrqNrAyY+CsN7nNz8bPfiwIwNpjk'';
  };
  resticPasswordFile = pkgs.writeText "restic-password" "hackme";
in {
  imports = [
    ./hardware-configuration.nix
    ./networking.nix # generated at runtime by nixos-infect
    ../../configs/brockman.nix
    ../../configs/thelounge.nix
    ../../configs/go-shortener.nix
    ../../configs/rss-bridge.nix
    ../../configs/ergochat.nix
    ../../configs/admin-essentials.nix
    ../../configs/monitoring.nix
    ../../configs/brockman-site.nix
    ../../configs/brockman-api.nix
  ];

  networking.hostName = "brockman";
  networking.domain = "news";
  clan.core.networking.targetHost = "${config.networking.hostName}.${config.networking.domain}";
  networking.defaultGateway.interface = "eth0";

  boot.tmp.cleanOnBoot = true;
  zramSwap.enable = true;

  nix = {
    package = pkgs.nixVersions.stable;
    extraOptions = "experimental-features = nix-command flakes";
    nixPath = ["nixpkgs=${inputs.nixpkgs}"];
  };

  services.restic.backups.brockman = {
    repository = "/backup";
    passwordFile = toString resticPasswordFile;
    initialize = true;
  };
  services.openssh.enable = true;

  users.users.root.openssh.authorizedKeys.keys = lib.attrValues sshKeys;

  system.stateVersion = "23.11";
}
