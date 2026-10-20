{ config, pkgs, inputs, ... }:
{
  imports = [ inputs.brockman.nixosModules.default ];

  services.nginx.virtualHosts = {
    "brockman.news" = {
      locations."= /brockman.json" = {
        root = "/var/lib/brockman/";
      };
      extraConfig = ''
        add_header 'Access-Control-Allow-Origin' '*';
        add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
      '';
    };
  };
  # the brockman module creates /var/lib/brockman with homeMode 770; nginx serves brockman.json from there (used by brockman-site bots.html)
  users.users.${config.services.nginx.user}.extraGroups = [ "brockman" ];

  environment.systemPackages = [
    pkgs.brockman-linkrot
  ];

  services.restic.backups.brockman.paths = [ "/var/lib/brockman" ];

  systemd.services.brockman.bindsTo = [ "ergochat.service" ];
  systemd.services.brockman.serviceConfig.LimitNOFILE = config.services.ergochat.openFilesLimit;
  # systemd.services.brockman.environment.BROCKMAN_LOG_LEVEL = "DEBUG";

  services.brockman = {
    enable = true;
    config = {
      irc.host = "localhost";
      channel = "#all";
      controller = {
        nick = "brockman";
        extraChannels = [ "#all" ];
      };
      statePath = "/var/lib/brockman/brockman.json";
      bots = {};
    };
  };
}
