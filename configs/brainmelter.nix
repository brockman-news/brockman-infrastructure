{ inputs, pkgs, lib, ... }:
let
  hostname = "brainmelter.brockman.news";
  port = 8080;
  brainmelter-web = inputs.brainmelter.packages.${pkgs.stdenv.hostPlatform.system}.web;
in {
  services.nginx.virtualHosts.${hostname} = {
    forceSSL = true;
    enableACME = true;
    locations."/" = {
      proxyPass = "http://127.0.0.1:${toString port}";
      # the page receives headlines over /ws
      proxyWebsockets = true;
    };
  };

  systemd.services.brainmelter-web = {
    description = "brainmelter: brockman.news headlines in thousands of voices";
    wantedBy = [ "multi-user.target" ];
    wants = [ "ergochat.service" ];
    after = [ "network.target" "ergochat.service" ];
    serviceConfig = {
      ExecStart = lib.escapeShellArgs [
        (lib.getExe brainmelter-web)
        "--host" "127.0.0.1"
        "--port" (toString port)
        # follow #all on the local ergochat instead of going out and back in through the public listener
        "--irc-host" "127.0.0.1"
        "--irc-port" "6667"
        # headlines.jsonl keeps each feed's learned language, and therefore its voice, across restarts
        "--state" "/var/lib/brainmelter/headlines.jsonl"
      ];
      DynamicUser = true;
      StateDirectory = "brainmelter";
      Restart = "on-failure";
      RestartSec = 5;
    };
  };
}
