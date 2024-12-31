{
  networking.firewall.allowedTCPPorts = [6667];

  services.ergochat.enable = true;
  services.ergochat.openFilesLimit = 16384;
  services.ergochat.settings = {
    limits.nicklen = 100;
    limits.identlen = 100;
    history.enabled = false;
  };
}
