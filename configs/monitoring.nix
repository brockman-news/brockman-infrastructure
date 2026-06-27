{ pkgs, config, ... }:
{
  services.prometheus = {
    enable = true;
    port = 9001;
    exporters = {
      node = {
        enable = true;
        openFirewall = true;
        enabledCollectors = [
          "conntrack"
          "diskstats"
          "entropy"
          "filefd"
          "filesystem"
          "loadavg"
          "mdadm"
          "meminfo"
          "netdev"
          "netstat"
          "stat"
          "time"
          "vmstat"
          "systemd"
          "logind"
          "interrupts"
          "ksmd"
        ];
        port = 9002;
      };
    };
  };

  services.alloy = {
    enable = true;
    extraFlags = [
      "--server.http.listen-addr=127.0.0.1:28183"
      "--storage.path=/var/lib/alloy"
    ];
  };

  environment.etc."alloy/config.alloy".text = ''
    loki.write "default" {
      endpoint {
        url = "http://${
          if config.networking.hostName == "makanek"
          then "127.0.0.1"
          else "makanek.r"
        }:3100/loki/api/v1/push"
      }
    }

    loki.relabel "journal" {
      forward_to = []
      rule {
        source_labels = ["__journal__systemd_unit"]
        target_label  = "unit"
      }
    }

    loki.source.journal "read" {
      forward_to    = [loki.write.default.receiver]
      max_age       = "12h"
      relabel_rules = loki.relabel.journal.rules
      labels        = {
        job  = "systemd-journal",
        host = "${config.networking.hostName}",
      }
    }
  '';
}
