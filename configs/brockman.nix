{ config, pkgs, ... }:
{
  services.nginx.virtualHosts = {
    "brockman.news" = {
      locations."/api".proxyPass = "http://127.0.0.1:7777/";
      locations."= /brockman.json" = {
        root = "/var/lib/brockman/";
      };
      extraConfig = ''
        add_header 'Access-Control-Allow-Origin' '*';
        add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
      '';
    };
  };
  systemd.tmpfiles.rules = [
    "d /run/irc-api 1750 brockman nginx -"
  ];

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
