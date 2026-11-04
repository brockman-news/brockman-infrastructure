{ config, pkgs, lib, inputs, ... }:
let
  operDir = "/var/lib/brockman-oper";
in
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
  systemd.services.brockman.serviceConfig.LoadCredential = [ "oper-password:${operDir}/password" ];
  systemd.services.brockman.requires = [ "brockman-oper-password.service" ];
  systemd.services.brockman.after = [ "brockman-oper-password.service" ];
  # ~1.3 GB with 41k feeds in a local test; if that ever runs away, kill brockman (Restart=always) instead of swapping the host
  systemd.services.brockman.serviceConfig.MemoryMax = "6G";
  # systemd.services.brockman.environment.BROCKMAN_LOG_LEVEL = "DEBUG";

  services.brockman = {
    enable = true;
    config = {
      irc.host = "localhost";
      irc.oper = {
        name = "brockman";
        passwordFile = "/run/credentials/brockman.service/oper-password";
      };
      # one IRC connection for all bots: the controller relays every item as NICK/rss
      # (ergo requires a relaymsg separator in relayed nicks)
      relaySuffix = "/rss";
      # spread the first fetch of every feed after a restart (it only records existing items, posting starts one tick later)
      maxStartDelay = 300;
      channel = "#all";
      controller = {
        nick = "brockman";
        extraChannels = [ "#all" ];
      };
      statePath = "/var/lib/brockman/brockman.json";
      bots = {};
    };
  };

  # brockman relays through RELAYMSG, which needs the relaymsg oper capability; nofakelag lets it keep up with every feed
  services.ergochat.settings = {
    server.relaymsg = {
      enabled = true;
      separators = "/";
      available-to-chanops = false;
    };
    oper-classes.relay = {
      title = "Relay";
      capabilities = [ "relaymsg" "nofakelag" ];
    };
    # the password hash is merged in at runtime (see ergochat below), so it stays on the machine
    opers.brockman = {
      class = "relay";
      hidden = true;
    };
  };

  # password and hash are generated on the machine; neither is in git or the nix store
  systemd.services.brockman-oper-password = {
    description = "Generate brockman's ergo OPER password";
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      UMask = "0077";
      StateDirectory = "brockman-oper";
    };
    path = [ pkgs.coreutils pkgs.mkpasswd ];
    script = ''
      if [ ! -s ${operDir}/password ]; then
        head -c 32 /dev/urandom | base64 -w0 | tr -d '/+=' > ${operDir}/password.tmp
        mv ${operDir}/password.tmp ${operDir}/password
        rm -f ${operDir}/hash
      fi
      if [ ! -s ${operDir}/hash ]; then
        mkpasswd -m bcrypt -R 10 --stdin < ${operDir}/password > ${operDir}/hash.tmp
        mv ${operDir}/hash.tmp ${operDir}/hash
      fi
    '';
  };

  # ergo 2.17 neither reads oper passwords from a file nor applies ERGO__OPERS__* environment overrides, so it runs from a
  # copy of /etc/ergo.yaml with the hash merged in. A rehash would reread that stale copy: config changes restart ergo instead
  # of reloading it, which disconnects every client.
  systemd.services.ergochat = {
    requires = [ "brockman-oper-password.service" ];
    after = [ "brockman-oper-password.service" ];
    reloadTriggers = lib.mkForce [ ];
    restartTriggers = [ config.services.ergochat.configFile ];
    serviceConfig = {
      RuntimeDirectory = "ergochat";
      RuntimeDirectoryMode = "0700";
      # "+": as root, to read the root-only hash; the result is handed to the dynamic user
      ExecStartPre = "+${pkgs.writeShellScript "ergochat-merge-oper" ''
        set -euo pipefail
        umask 077
        HASH=$(< ${operDir}/hash) ${lib.getExe pkgs.yq-go} '.opers.brockman.password = strenv(HASH)' /etc/ergo.yaml > /run/ergochat/ergo.yaml
        chown --reference=/run/ergochat /run/ergochat/ergo.yaml
      ''}";
      ExecStart = lib.mkForce "${pkgs.ergochat}/bin/ergo run --conf /run/ergochat/ergo.yaml";
    };
  };
}
