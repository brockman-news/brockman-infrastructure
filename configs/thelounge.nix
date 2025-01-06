{ config, pkgs, ...  }:
{
  services.thelounge = {
    enable = true;
    port = 5079;
    public = true;
    plugins = [
      pkgs.nodePackages.thelounge-theme-monokai-console
    ];
    extraConfig = {
      host = "127.0.0.1";
      theme = "thelounge-theme-monokai-console";
      disableMediaPreview = true;
      fileUpload.enable = false;
      defaults = {
        name = "brockman.news";
        host = "brockman.news";
        port = 6667;
        nick = "webirc_%%%";
        realname = "web IRC user";
        tls = false;
        join = "#all";
      };
      messageStorage = [];
      maxHistory = 1000;
      leaveMessage = "brockman.news web IRC";
      lockNetwork = true;
      storagePolicy = {
        enabled = true;
        maxAgeDays = 1;
        deletionPolicy = "everything";
      };
    };
  };

  services.nginx.virtualHosts = {
    thelounge = {
      forceSSL = true;
      enableACME = true;
      locations."/".proxyPass = "http://127.0.0.1:${toString config.services.thelounge.port}/";
      serverAliases = [
        "webirc.brockman.news"
      ];
    };
  };
}
